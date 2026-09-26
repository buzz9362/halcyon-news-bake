"""Sep 26 2026 (RV): the r8 priority re-voice (tier 1 before fresh stories) and the
retext_ids one-shot dispatch.

Run from the repo root:  python -m pytest tests -q
No network: the R2, feed and gTTS fakes of test_throttle.py, and whole passes run through
bake.main(). Every test carries its own control: the same world with the one input that
matters changed must give a different result, so a test that cannot fail is caught here.
Positive control on the old code: BAKE_PY=<bake.py before RV> (new names are patched with
create=True, so the old code runs to the assertions and fails on behavior).
"""
import contextlib
import datetime
import io
import json
import os
import re
import time
import unittest
from unittest import mock

import yaml

import test_throttle as tt

bake = tt.bake
ROOT = tt.ROOT
R8 = "r8-2026-09-26"
OWNER_T1 = {"rss_1oweqv3", "rss_16ou9u0", "rss_1xvqood", "rss_o2biu8", "rss_1km17bp"}


def run(w, tts, entries=(), retext_ids=(), revoice_apps=(), cap=None):
    bake._STARVED.clear()
    bake._retext_cut.clear()
    out = io.StringIO()
    pr = {"entries": [dict(e) for e in entries]}
    with contextlib.ExitStack() as st:
        for p in (
            mock.patch.object(bake, "s3", w.s3),
            mock.patch.object(bake, "requests", w.requests),
            mock.patch.object(bake, "synth_to_mp3", tts),
            mock.patch.object(bake, "_sleep", lambda s: None, create=True),
            mock.patch.object(bake, "MANIFESTS", w.manifests),
            mock.patch.object(bake, "FORCE_APP", ""),
            mock.patch.object(bake, "RETEXT_APPS", set(revoice_apps)),
            mock.patch.object(bake, "retext_targeted", return_value={}),
            mock.patch.object(bake, "SOUNDICA_FM_COMPONENTS", {}),
            mock.patch.object(bake, "retext_priority", lambda: pr, create=True),
            mock.patch.object(bake, "RETEXT_IDS", list(retext_ids), create=True),
        ):
            st.enter_context(p)
        if cap is not None:
            st.enter_context(mock.patch.object(bake, "RETEXT_T1_MAX_PER_PASS", cap, create=True))
        st.enter_context(contextlib.redirect_stdout(out))
        rc = bake.main()
    bake._STARVED.clear()
    return rc, out.getvalue()


def t1(manifest, *ks, tier=1, **extra):
    return [dict({"manifest": manifest, "id": f"{manifest}-o{k}", "tier": tier}, **extra) for k in ks]


def first_fresh(calls):
    return next(i for i, c in enumerate(calls) if "-f" in c)


def carry(w, name, sid, age_min):
    """Put a story the car still plays from the carry-forward (in the live manifest, NOT in the
    feed window) into the world, with an old MP3."""
    a = tt.story(sid, age_min)
    w.s3.objs[bake.article_key(sid)] = (b"old", tt.OLD_MP3)
    key = f"{name}.json"
    items = json.loads(w.s3.objs[key][0].decode())["items"] if key in w.s3.objs else []
    w.s3.objs[key] = (json.dumps({"items": items + [a]}).encode(), tt.OLD_MP3)


def set_mod(w, sid, when_ms):
    k = bake.article_key(sid)
    w.s3.objs[k] = (w.s3.objs[k][0], datetime.datetime.fromtimestamp(when_ms / 1000, datetime.timezone.utc))


class TierOne(unittest.TestCase):
    def test_tier1_goes_before_fresh_stories(self):
        entries = t1("zzb_en", 3) + t1("zza_en", 1) + t1("zza_en", 2, tier=2)
        w = tt.World(["zza_en", "zzb_en"], fresh=3)
        tts = tt.FakeTTS(ok=10 ** 6)
        run(w, tts, entries)
        # Tier 1 first, in file order, then the fresh round-robin, then tier 2.
        self.assertEqual(["zzb_en-o3", "zza_en-o1"], tts.calls[:2])
        self.assertEqual(6, sum(1 for c in tts.calls if "-f" in c))
        self.assertTrue(all("-f" in c for c in tts.calls[2:8]), tts.calls)
        self.assertIn("zza_en-o2", tts.calls[8:])
        # Control: the same stories as tier 2 wait until every fresh story is baked.
        w2 = tt.World(["zza_en", "zzb_en"], fresh=3)
        tts2 = tt.FakeTTS(ok=10 ** 6)
        run(w2, tts2, [dict(e, tier=2) for e in entries])
        self.assertEqual(0, first_fresh(tts2.calls))

    def test_tier1_cap_holds_and_the_rest_follow_after_fresh(self):
        entries = t1("zza_en", *range(6)) + t1("zzb_en", *range(6))   # 12 tier-1 stories
        w = tt.World(["zza_en", "zzb_en"], fresh=2, old=8)
        tts = tt.FakeTTS(ok=10 ** 6)
        run(w, tts, entries)
        self.assertEqual(10, first_fresh(tts.calls))
        self.assertEqual(10, getattr(bake, "RETEXT_T1_MAX_PER_PASS", None))
        self.assertEqual([e["id"] for e in entries[:10]], tts.calls[:10])
        # The 2 over the cap are re-voiced in the same clean pass, after the fresh stories.
        after = tts.calls[first_fresh(tts.calls):]
        self.assertIn("zzb_en-o4", after)
        self.assertIn("zzb_en-o5", after)
        self.assertEqual(12, len({c for c in tts.calls if "-o" in c} & {e["id"] for e in entries}))
        # Control: without the cap all 12 go before the first fresh story.
        w2 = tt.World(["zza_en", "zzb_en"], fresh=2, old=8)
        tts2 = tt.FakeTTS(ok=10 ** 6)
        run(w2, tts2, entries, cap=10 ** 6)
        self.assertEqual(12, first_fresh(tts2.calls))

    def test_the_breaker_stops_tier1_too(self):
        entries = t1("zza_en", 0, 1, 2, 3)
        w = tt.World(["zza_en"], fresh=3)
        tts = tt.FakeTTS(ok=0)   # 429 for the whole pass
        rc, out = run(w, tts, entries)
        # story 1: 429 + one retry (429); story 2: 429 -> breaker open. Nothing after that.
        self.assertEqual(["zza_en-o0", "zza_en-o0", "zza_en-o1"], tts.calls)
        self.assertEqual(1, out.count("breaker OPEN"))
        self.assertEqual(b"old", w.s3.objs[bake.article_key("zza_en-o0")][0])   # old audio kept
        ids = {a["id"] for a in w.s3.manifest("zza_en")}
        self.assertIn("zza_en-o0", ids)       # the manifest is still written with what is confirmed
        self.assertNotIn("zza_en-f0", ids)
        w.assert_manifests_confirmed(self)
        # Control: two 429s and then gTTS answers again: the breaker stays closed and tier 1
        # and the fresh stories go on, so the 3 calls above come from the breaker.
        w2 = tt.World(["zza_en"], fresh=3)
        tts2 = tt.FakeTTS(ok=0, bad=2)
        run(w2, tts2, entries)
        self.assertTrue({"zza_en-o2", "zza_en-o3", "zza_en-f0"} <= set(tts2.calls), tts2.calls)

    def test_done_ids_and_ids_out_of_the_window_are_skipped(self):
        now = int(time.time() * 1000)
        cut = now - 3600 * 1000
        w = tt.World(["zza_en"], fresh=0, old=6)
        w.s3.objs[f"_retext/{R8}.json"] = (json.dumps({"cutover_ms": cut}).encode(), tt.OLD_MP3)
        set_mod(w, "zza_en-o0", now - 600 * 1000)                  # re-uploaded after the cutover
        set_mod(w, "zza_en-o2", cut - 3600 * 1000)                 # after its done_after_ms, before the cutover
        entries = (t1("zza_en", 0)                                 # done
                   + [{"manifest": "zza_en", "id": "gone-id", "tier": 1}]   # no longer in any window
                   + t1("zza_en", 1)                               # control: old MP3, voiced
                   + t1("zza_en", 2, tier=3, done_after_ms=cut - 2 * 3600 * 1000)   # done (own threshold)
                   + t1("zza_en", 3, tier=3, done_after_ms=cut - 2 * 3600 * 1000))  # control: voiced
        tts = tt.FakeTTS(ok=10 ** 6)
        run(w, tts, entries)
        self.assertEqual(["zza_en-o1", "zza_en-o3"], tts.calls)
        # Self-terminating: the next pass finds every entry done and voices nothing.
        tts2 = tt.FakeTTS(ok=10 ** 6)
        run(w, tts2, entries)
        self.assertEqual([], tts2.calls)


    def test_a_carried_story_the_car_still_plays_is_revoiced(self):
        # Sep 26: 4 of the 5 owner-flagged stories had left the feed window and were played from
        # the manifest carry-forward. c0 is carried (10 h old); c9 is past CARRY_MAX_AGE_MS.
        entries = [{"manifest": "zza_en", "id": "zza_en-c0", "tier": 1},
                   {"manifest": "zza_en", "id": "zza_en-c9", "tier": 1}]
        w = tt.World(["zza_en"], fresh=1)
        carry(w, "zza_en", "zza_en-c0", 600)
        carry(w, "zza_en", "zza_en-c9", 80 * 60)
        tts = tt.FakeTTS(ok=10 ** 6)
        run(w, tts, entries)
        self.assertEqual(["zza_en-c0", "zza_en-f0"], tts.calls)
        self.assertIn("zza_en-c0", {a["id"] for a in w.s3.manifest("zza_en")})   # still carried
        # Control: the same entry with no live manifest carrying it is not voiced (so the carry
        # path, not the feed, is what reached c0).
        w2 = tt.World(["zza_en"], fresh=1)
        w2.s3.objs[bake.article_key("zza_en-c0")] = (b"old", tt.OLD_MP3)
        tts2 = tt.FakeTTS(ok=10 ** 6)
        run(w2, tts2, entries)
        self.assertNotIn("zza_en-c0", tts2.calls)


class RetextIds(unittest.TestCase):
    def world(self):
        return tt.World(["zza_en", "zzb_en"], fresh=2)

    def test_retext_ids_dispatch_voices_exactly_those_ids(self):
        busy = dict(entries=t1("zza_en", 4), revoice_apps={"zza", "zzb"})
        w = self.world()
        tts = tt.FakeTTS(ok=10 ** 6)
        rc, out = run(w, tts, retext_ids=["zzb_en-o1", "zza_en-o3"], **busy)
        self.assertEqual(0, rc)
        self.assertEqual(["zzb_en-o1", "zza_en-o3"], tts.calls)
        self.assertEqual(b"mp3", w.s3.objs[bake.article_key("zzb_en-o1")][0])
        for n in ("zza_en", "zzb_en"):
            self.assertIsNone(w.s3.manifest(n), "a re-voice pass must not write manifests")
        self.assertIn("retext_ids voiced 2/2", out)
        # Control: the same world without retext_ids voices fresh, tier-1 and r6 stories.
        w2 = self.world()
        tts2 = tt.FakeTTS(ok=10 ** 6)
        run(w2, tts2, **busy)
        self.assertTrue({"zza_en-o4", "zza_en-f0", "zzb_en-f0"} <= set(tts2.calls), tts2.calls)

    def test_an_unknown_id_is_reported_and_fails_the_run(self):
        # "nope" has no MP3 in R2 and is in no window: it never existed (a typo), so the run is red.
        w = self.world()
        tts = tt.FakeTTS(ok=10 ** 6)
        rc, out = run(w, tts, retext_ids=["nope", "zza_en-o0"])
        self.assertEqual(["zza_en-o0"], tts.calls)
        self.assertEqual(1, rc)
        self.assertIn("nope: not in any feed window", out)
        # Control: with only ids that exist, the run is green.
        rc2, _ = run(self.world(), tt.FakeTTS(ok=10 ** 6), retext_ids=["zza_en-o0"])
        self.assertEqual(0, rc2)

    def test_an_id_that_left_every_window_is_a_notice_not_a_failure(self):
        # Sep 26 run 36233549008: 17/20 re-voiced, failed=0, but 3 ids had aged out of every feed
        # window AND every live manifest between the list being built and the dispatch. No car
        # plays them, so there is nothing to re-voice; the run went red and mailed the owner.
        w = self.world()
        w.s3.objs[bake.article_key("zzb_en-gone")] = (b"old", tt.OLD_MP3)   # voiced once, now in no window
        tts = tt.FakeTTS(ok=10 ** 6)
        rc, out = run(w, tts, retext_ids=["zzb_en-gone", "zza_en-o0"])
        self.assertEqual((0, ["zza_en-o0"]), (rc, tts.calls))
        self.assertIn("::notice::", out)
        self.assertIn("zzb_en-gone", out)
        # Control: the same dispatch with a real synth failure is still red.
        rc2, _ = run(self.world(), tt.FakeTTS(ok=0), retext_ids=["zza_en-o0"])
        self.assertEqual(1, rc2)

    def test_retext_ids_reaches_a_story_that_left_the_feed_window(self):
        w = self.world()
        carry(w, "zzb_en", "zzb_en-c0", 600)
        tts = tt.FakeTTS(ok=10 ** 6)
        rc, _ = run(w, tts, retext_ids=["zzb_en-c0"])
        self.assertEqual((0, ["zzb_en-c0"]), (rc, tts.calls))
        # Control: not in any feed and not in any live manifest -> not voiced (no car plays it,
        # so the run stays green and says so in a notice).
        w2 = self.world()
        w2.s3.objs[bake.article_key("zzb_en-c0")] = (b"old", tt.OLD_MP3)
        tts2 = tt.FakeTTS(ok=10 ** 6)
        rc2, out2 = run(w2, tts2, retext_ids=["zzb_en-c0"])
        self.assertEqual((0, []), (rc2, tts2.calls))
        self.assertIn("left every window", out2)

    def test_the_breaker_stops_a_retext_ids_pass(self):
        w = self.world()
        tts = tt.FakeTTS(ok=0)
        rc, out = run(w, tts, retext_ids=["zza_en-o0", "zza_en-o1", "zzb_en-o0", "zzb_en-o1"])
        # id 1: 429 + one retry; id 2: 429 -> breaker open; ids 3 and 4 are never sent.
        self.assertEqual(["zza_en-o0", "zza_en-o0", "zza_en-o1"], tts.calls)
        self.assertEqual(1, rc)
        self.assertIn("retext_ids voiced 0/4", out)
        self.assertIn("breaker=OPEN", out)
        # Control: two 429s, then gTTS answers: the other ids are voiced.
        tts2 = tt.FakeTTS(ok=0, bad=2)
        rc2, _ = run(self.world(), tts2, retext_ids=["zza_en-o0", "zza_en-o1", "zzb_en-o0", "zzb_en-o1"])
        self.assertTrue({"zza_en-o1", "zzb_en-o0", "zzb_en-o1"} <= set(tts2.calls), tts2.calls)

    def test_a_forced_id_counts_as_done_for_the_priority_list(self):
        entries = t1("zza_en", 0)
        w = self.world()
        run(w, tt.FakeTTS(ok=10 ** 6), entries=entries, retext_ids=["zza_en-o0"])
        self.assertIn(f"_retext/{R8}.json", w.s3.objs)   # the r8 cutover is set before the voice
        tts = tt.FakeTTS(ok=10 ** 6)
        run(w, tts, entries)
        self.assertNotIn("zza_en-o0", tts.calls)
        # Control: without the forced pass, the normal pass re-voices it as tier 1.
        w2 = self.world()
        tts2 = tt.FakeTTS(ok=10 ** 6)
        run(w2, tts2, entries)
        self.assertEqual("zza_en-o0", tts2.calls[0])


class Workflow(unittest.TestCase):
    def test_bake_yml_runs_retext_ids_as_one_pass_in_its_own_group(self):
        path = os.environ.get("BAKE_YML") or os.path.join(ROOT, ".github", "workflows", "bake.yml")
        with open(path, encoding="utf-8") as f:
            wf = yaml.safe_load(f)
        on = wf.get("on", wf.get(True))
        self.assertIn("retext_ids", on["workflow_dispatch"]["inputs"])
        step = [s for s in wf["jobs"]["bake"]["steps"] if s.get("name") == "Bake"][0]
        self.assertEqual("${{ github.event.inputs.retext_ids }}", step["env"]["RETEXT_IDS"])
        script = step["run"]
        m = re.search(r'if \[ -n "\$\{RETEXT_IDS\}" \]; then(.*?)fi', script, re.S)
        self.assertIsNotNone(m, "no retext_ids branch")
        self.assertIn("exec python bake.py", m.group(1))           # one pass, then the step ends
        self.assertLess(m.start(), script.index("while :; do"))    # before the loop
        self.assertIn("'bake-retext'", wf["concurrency"]["group"])  # does not queue behind a loop


def r8_problems(data, manifests):
    """What is wrong with an r8 list (empty = fine)."""
    probs = []
    entries = data.get("entries") or []
    if data.get("tag") != R8:
        probs.append(f"tag {data.get('tag')!r}")
    t1_ids = {e.get("id") for e in entries if e.get("tier") == 1}
    if not OWNER_T1 <= t1_ids:
        probs.append(f"tier 1 misses {sorted(OWNER_T1 - t1_ids)}")
    seen = set()
    for e in entries:
        k = (e.get("manifest"), e.get("id"))
        if e.get("manifest") not in manifests:
            probs.append(f"unknown manifest {k}")
        if e.get("tier") not in (1, 2, 3):
            probs.append(f"bad tier {k}")
        if not e.get("id"):
            probs.append(f"no id {k}")
        if k in seen:
            probs.append(f"duplicate {k}")
        seen.add(k)
        if e.get("tier") == 3 and not e.get("done_after_ms"):
            probs.append(f"tier 3 without done_after_ms {k}")
    kpop_t1 = [e for e in entries if e.get("tier") == 1 and e.get("manifest") == "kpop_en"]
    if {e["id"] for e in kpop_t1} != OWNER_T1:
        probs.append("the kpop_en tier-1 entries are not the 5 owner-flagged stories")
    return probs


class R8List(unittest.TestCase):
    def test_the_shipped_r8_list_is_well_formed_and_names_the_owner_stories(self):
        self.assertEqual(f"retext/{R8}.json", bake.RETEXT_PRIORITY_FILE)
        with open(os.path.join(ROOT, bake.RETEXT_PRIORITY_FILE), encoding="utf-8") as f:
            data = json.load(f)
        names = {m["manifest"] for m in bake.MANIFESTS}
        self.assertEqual([], r8_problems(data, names))
        # Control: the same list without the Tiffany story is caught.
        cut = dict(data, entries=[e for e in data["entries"] if e["id"] != "rss_1oweqv3"])
        self.assertTrue(r8_problems(cut, names))


if __name__ == "__main__":
    unittest.main()
