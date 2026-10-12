"""r1010 N2-3 (Oct 12 2026): the interim id collision guard. The MP3 key is sha256(id)[:32] and the id is
the worker's rss_<djb2_32(link)>, one key space for every app and language. A new story whose id already
maps to a DIFFERENT link would find the old story's MP3 in R2 and be listed with the wrong audio, so it is
kept out of the manifest (logged as COLLISION). A story whose id maps to the same link is listed as usual.

Run from the repo root:  python -m unittest discover -s tests
Positive control: against the pre-r1010 bake.py (BAKE_PY=<old copy>) the colliding row is listed, so
test_a_colliding_row_is_dropped fails there.
"""
import json
import unittest

import test_throttle as tt

bake = tt.bake
NAME = "kpop_en"
LINK_A = "https://www.example-news.com/article/older-story"
LINK_B = "https://www.example-news.com/article/newer-story-same-id"
LINK_C = "https://www.example-news.com/article/known-story"


def _art(sid, link, age_min):
    a = tt.story(sid, age_min)
    a["articleUrl"] = link
    return a


def _world(feed, index):
    w = tt.World([NAME], fresh=0, old=4)
    w.requests.feeds[f"https://t/{NAME}"] = feed + w.requests.feeds[f"https://t/{NAME}"]
    for a in feed:   # every feed row already has an MP3 under its id key
        w.s3.objs[bake.article_key(a["id"])] = (b"old", tt.OLD_MP3)
    w.s3.objs["_index/ids.json"] = (json.dumps({"v": 1, "ids": index}).encode("utf-8"), tt.OLD_MP3)
    return w


class IdCollisionGuard(unittest.TestCase):
    def test_a_colliding_row_is_dropped(self):
        clash = _art("rss_clash1", LINK_B, 30)
        same = _art("rss_known1", LINK_C, 40)
        w = _world([clash, same], {"rss_clash1": [LINK_A, 20000], "rss_known1": [LINK_C, 20000]})
        rc, out, _ = w.run(tt.FakeTTS(ok=99))
        ids = [a["id"] for a in w.s3.manifest(NAME)]
        self.assertNotIn("rss_clash1", ids)
        self.assertIn(f"COLLISION rss_clash1 {LINK_A} {LINK_B}", out)
        # control: the same-link row and the plain rows of the same pass are listed
        self.assertIn("rss_known1", ids)
        self.assertIn(f"{NAME}-o0", ids)

    def test_a_new_id_is_recorded_and_the_index_stays_bounded(self):
        fresh = _art("rss_brandnew", LINK_A, 30)
        w = _world([fresh], {})
        w.run(tt.FakeTTS(ok=99))
        self.assertIn("rss_brandnew", [a["id"] for a in w.s3.manifest(NAME)])
        stored = json.loads(w.s3.objs["_index/ids.json"][0].decode("utf-8"))["ids"]
        self.assertEqual(LINK_A, stored["rss_brandnew"][0])
        idx = bake.IdLinkIndex({f"rss_{k}": [f"https://x/{k}", k] for k in range(bake.ID_INDEX_MAX + 5)})
        kept = json.loads(idx.to_json().decode("utf-8"))["ids"]
        self.assertEqual(bake.ID_INDEX_MAX, len(kept))
        self.assertNotIn("rss_0", kept)   # the oldest-seen ids go first
        self.assertIn(f"rss_{bake.ID_INDEX_MAX + 4}", kept)

    def test_an_unreadable_index_turns_the_guard_off_and_is_never_overwritten(self):
        idx = bake.IdLinkIndex(enabled=False)
        self.assertIsNone(idx.check("rss_x", LINK_A, 1))
        self.assertFalse(idx.dirty)


if __name__ == "__main__":
    unittest.main()
