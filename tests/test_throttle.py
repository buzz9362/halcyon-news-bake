"""Sep 26 2026 (BK): the gTTS 429 circuit breaker, fair newest-first order and re-voice yield.

Run from the repo root:  python -m pytest tests -q
No network: R2, the worker feeds and gTTS are in-memory fakes, and a whole pass runs
through bake.main(). Positive control: BAKE_PY=<old bake.py> runs the same tests against
another copy of bake.py (the Sep 26 BK report lists what fails on the old code).
"""
import contextlib
import datetime
import importlib.util
import io
import json
import os
import re
import time
import unittest
from unittest import mock

from botocore.exceptions import ClientError
from gtts.tts import gTTSError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_bake():
    for k, v in (("R2_ACCESS_KEY_ID", "x"), ("R2_SECRET_ACCESS_KEY", "x"), ("R2_ENDPOINT_URL", "https://example.invalid")):
        os.environ.setdefault(k, v)
    path = os.environ.get("BAKE_PY") or os.path.join(ROOT, "bake.py")
    spec = importlib.util.spec_from_file_location("bake_bk", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


os.chdir(ROOT)
bake = _load_bake()

OLD_MP3 = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
MSG_429 = "429 (Too Many Requests) from TTS API. Probable cause: Unknown"
STORY_RE = re.compile(r"Story (\S+) ")


class FakeS3:
    def __init__(self):
        self.objs = {}   # key -> (body, LastModified)

    def head_object(self, Bucket, Key):
        if Key not in self.objs:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {"LastModified": self.objs[Key][1]}

    def get_object(self, Bucket, Key):
        if Key not in self.objs:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": io.BytesIO(self.objs[Key][0])}

    def put_object(self, Bucket, Key, Body, **kw):
        self.objs[Key] = (Body, datetime.datetime.now(datetime.timezone.utc))

    def manifest(self, name):
        if f"{name}.json" not in self.objs:
            return None
        return json.loads(self.objs[f"{name}.json"][0].decode("utf-8"))["items"]


class FakeRequests:
    def __init__(self, feeds):
        self.feeds = feeds

    def get(self, url, timeout=None):
        items = self.feeds[url]
        r = mock.Mock()
        r.raise_for_status.return_value = None
        r.json.return_value = {"items": [dict(a) for a in items]}
        return r


class FakeTTS:
    """Succeeds for the first `ok` calls, then answers 429 the way gTTS does for `bad`
    calls (None = for the rest of the pass), then succeeds again."""

    def __init__(self, ok, bad=None):
        self.ok, self.bad, self.calls = ok, bad, []

    def __call__(self, text, lang, tld):
        self.calls.append(STORY_RE.search(text).group(1))
        n = len(self.calls)
        if n > self.ok and (self.bad is None or n <= self.ok + self.bad):
            raise gTTSError(MSG_429)
        return b"mp3"


def story(sid, age_min):
    return {"id": sid, "title": f"Story {sid} has a headline long enough to be voiced",
            "summary": "A summary line.", "source": "Wire",
            "publishedAtMs": int(time.time() * 1000) - age_min * 60 * 1000}


class World:
    """names -> feeds of `old` stories already in R2 (old MP3s) and `fresh` new ones. Fresh
    story k of manifest X is 'X-f<k>', k=0 the NEWEST; the feed lists them OLDEST first so
    newest-first must come from the baker, not the feed."""

    def __init__(self, names, fresh=3, old=5, old_age_min=None):
        self.s3 = FakeS3()
        self.manifests, feeds = [], {}
        for n in names:
            age = (old_age_min or {}).get(n, 600)
            olds = [story(f"{n}-o{k}", age + k) for k in range(old)]
            fresh_items = [story(f"{n}-f{k}", 5 + k) for k in range(fresh)]
            for a in olds:
                self.s3.objs[bake.article_key(a["id"])] = (b"old", OLD_MP3)
            feeds[f"https://t/{n}"] = list(reversed(fresh_items)) + olds
            self.manifests.append({"manifest": n, "feed_url": f"https://t/{n}", "lang": "en",
                                   "tld": "us", "phonetics": n})
        self.requests = FakeRequests(feeds)

    def run(self, tts, revoice_apps=()):
        bake._STARVED.clear()
        bake._retext_cut.clear()
        out = io.StringIO()
        with mock.patch.object(bake, "s3", self.s3), \
                mock.patch.object(bake, "requests", self.requests), \
                mock.patch.object(bake, "synth_to_mp3", tts), \
                mock.patch.object(bake, "_sleep", lambda s: None, create=True), \
                mock.patch.object(bake, "MANIFESTS", self.manifests), \
                mock.patch.object(bake, "FORCE_APP", ""), \
                mock.patch.object(bake, "RETEXT_APPS", set(revoice_apps)), \
                mock.patch.object(bake, "retext_targeted", return_value={}), \
                mock.patch.object(bake, "SOUNDICA_FM_COMPONENTS", {}), \
                contextlib.redirect_stdout(out):
            rc = bake.main()
        starved = list(bake._STARVED)
        bake._STARVED.clear()
        return rc, out.getvalue(), starved

    def assert_manifests_confirmed(self, test):
        for m in self.manifests:
            for a in self.s3.manifest(m["manifest"]) or []:
                test.assertIn(bake.article_key(a["id"]), self.s3.objs, f"{a['id']} listed without an MP3")


class Breaker(unittest.TestCase):
    def test_breaker_stops_every_synth_after_three_429s_in_a_row(self):
        # Sep 25 run: 540-690 synth requests per throttled pass. Here: 2 successes, then
        # 429 forever; 3 manifests x 10 fresh stories and re-voice candidates.
        w = World(["zza_en", "zzb_en", "zzc_en"], fresh=10)
        tts = FakeTTS(ok=2)
        rc, out, _ = w.run(tts, revoice_apps={"zza", "zzb", "zzc"})
        # 2 successes + story 3 (429, one retry, 429) + story 4 (429 -> open) = 5 calls.
        self.assertEqual(5, len(tts.calls), tts.calls)
        self.assertEqual(1, out.count("breaker OPEN"))
        # The manifests are still written, with the confirmed stories only.
        for m in w.manifests:
            self.assertIsNotNone(w.s3.manifest(m["manifest"]))
        w.assert_manifests_confirmed(self)

    def test_a_single_429_backs_off_and_retries_once(self):
        w = World(["zza_en"], fresh=2)
        tts = FakeTTS(ok=0, bad=1)
        w.run(tts)
        self.assertEqual(["zza_en-f0", "zza_en-f0", "zza_en-f1"], tts.calls)
        ids = {a["id"] for a in w.s3.manifest("zza_en")}
        self.assertIn("zza_en-f0", ids)   # the retry landed it

    def test_is_throttle_reads_the_status_and_the_message(self):
        rsp = mock.Mock(status_code=429)
        self.assertTrue(bake.is_throttle(gTTSError("x", response=rsp)))
        self.assertTrue(bake.is_throttle(gTTSError(MSG_429)))
        self.assertFalse(bake.is_throttle(gTTSError("500 (Server Error) from TTS API. Probable cause: Upstream")))
        self.assertFalse(bake.is_throttle(gTTSError("Failed to connect. Probable cause: Unknown")))

    def test_summary_counts_the_429s_of_the_pass(self):
        w = World(["zza_en", "zzb_en"], fresh=3)
        _, out, _ = w.run(FakeTTS(ok=0))
        line = [l for l in out.splitlines() if l.startswith("Summary:")][0]
        self.assertIn("gTTS 429s=3", line)
        self.assertIn("synth attempts=3", line)
        self.assertIn("breaker=OPEN", line)


class FairOrder(unittest.TestCase):
    def test_every_manifest_gets_its_newest_story_before_any_second(self):
        names = ["zza_en", "zzb_en", "zzc_en"]
        w = World(names, fresh=3)
        tts = FakeTTS(ok=10 ** 6)
        w.run(tts)
        self.assertEqual({f"{n}-f0" for n in names}, set(tts.calls[:3]))
        self.assertEqual(9, len(tts.calls))
        for n in names:   # newest first inside a manifest
            self.assertEqual([f"{n}-f0", f"{n}-f1", f"{n}-f2"], [c for c in tts.calls if c.startswith(n)])

    def test_under_throttle_each_manifest_still_gets_its_newest(self):
        names = ["zza_en", "zzb_en", "zzc_en"]
        w = World(names, fresh=5)
        rc, _, starved = w.run(FakeTTS(ok=3))
        for n in names:
            self.assertIn(f"{n}-f0", {a["id"] for a in w.s3.manifest(n)}, n)
        self.assertEqual([], starved)
        self.assertEqual(0, rc)
        w.assert_manifests_confirmed(self)

    def test_the_stalest_manifest_bakes_first(self):
        names = ["zza_en", "zzb_en", "zzc_en"]
        # Put the stalest manifest LAST in this pass's rotation, so only a staleness order
        # can reach it first.
        off = int(time.time() // 1800) % len(names)
        stalest = names[(off - 1) % len(names)]
        w = World(names, fresh=2, old_age_min={n: (1200 if n == stalest else 60) for n in names})
        tts = FakeTTS(ok=1)
        w.run(tts)
        self.assertEqual(f"{stalest}-f0", tts.calls[0])
        self.assertIn(f"{stalest}-f0", {a["id"] for a in w.s3.manifest(stalest)})


class RevoiceYields(unittest.TestCase):
    def test_revoice_is_skipped_for_the_pass_after_any_429(self):
        names = ["zza_en", "zzb_en"]
        w = World(names, fresh=1)
        tts = FakeTTS(ok=0, bad=1)   # one 429, then gTTS answers again
        w.run(tts, revoice_apps={"zza", "zzb"})
        self.assertEqual([], [c for c in tts.calls if "-o" in c], "re-voiced after a 429")
        for n in names:
            self.assertIn(f"{n}-f0", {a["id"] for a in w.s3.manifest(n)})

    def test_revoice_starts_only_after_every_fresh_story(self):
        names = ["zza_en", "zzb_en"]
        w = World(names, fresh=2)
        tts = FakeTTS(ok=10 ** 6)
        w.run(tts, revoice_apps={"zza", "zzb"})
        kinds = ["o" if "-o" in c else "f" for c in tts.calls]
        self.assertIn("o", kinds)   # control: the re-voice does run in a clean pass
        self.assertEqual(["f"] * 4, kinds[:4])
        self.assertNotIn("f", kinds[4:])


class Starved(unittest.TestCase):
    def test_starved_fires_for_failed_and_breaker_deferred_manifests(self):
        # Keep-guard for P1's alarm: with the breaker, zzc/zzd are never attempted, and they
        # must still be reported. Control: the P1 condition (failures and none baked) misses them.
        names = ["zza_en", "zzb_en", "zzc_en", "zzd_en"]
        w = World(names, fresh=2)
        rc, out, starved = w.run(FakeTTS(ok=0))
        self.assertEqual(1, rc)
        self.assertEqual(sorted((n, 2) for n in names), sorted(starved))
        self.assertIn("STARVED manifests", out)

    def test_no_alarm_when_nothing_was_fresh(self):
        w = World(["zza_en"], fresh=0)
        rc, _, starved = w.run(FakeTTS(ok=0))
        self.assertEqual((0, []), (rc, starved))


if __name__ == "__main__":
    unittest.main()
