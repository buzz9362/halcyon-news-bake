"""r1010 N2-7 (Oct 12 2026, deferred item 4, title half): a single hashtag in a TITLE is voiced as words, the
same single-hashtag step the summary already gets (split_hashtag_words). Only that step: the rest of the social
strip stays summary-only. Parity: the apps' splitHashtagWords on titles (parse time and manifest map).

Run from the repo root:  python -m unittest discover -s tests
Positive control: test_old_text_for_voiced_the_hash asserts the pre-r1010 shape (title passed through
clean_text only) still voices "#SongYuqi", and against the pre-r1010 bake.py (BAKE_PY=<old copy>)
test_a_single_title_hashtag_is_voiced_as_words fails.
"""
import unittest

import test_throttle as tt

bake = tt.bake


def _art(title, summary="Fans filled the arena for both nights of the tour."):
    return {"id": "rss_ht1", "title": title, "summary": summary, "source": "Wire"}


class TitleHashtag(unittest.TestCase):
    def test_old_text_for_voiced_the_hash(self):
        self.assertIn("#SongYuqi", bake.clean_text("#SongYuqi returns to the stage"))

    def test_a_single_title_hashtag_is_voiced_as_words(self):
        text = bake.text_for(_art("#SongYuqi returns to the stage"))
        self.assertNotIn("#", text)
        self.assertIn("Song Yuqi returns to the stage", text)
        self.assertIn("BTS Army floods the timeline", bake.text_for(_art("#BTSArmy floods the timeline")))
        self.assertIn("Kpop Jakarta", bake.text_for(_art("Tagar #Kpop_Jakarta ramai dibicarakan")))

    def test_the_same_shapes_stay_as_in_the_summary_rule(self):
        for keep in ("BTS hits #1 on the Billboard 200", "C# 13 ships with new features", "Tom &#38; Jerry return"):
            self.assertEqual(keep, bake.split_single_hashtags(keep))
        # Only the single step runs on a title: a hashtag run is split word by word, not removed.
        self.assertEqual("Stray Kids and BTS trend", bake.split_single_hashtags("#StrayKids and #BTS trend"))
        self.assertEqual("No tags here", bake.split_single_hashtags("No tags here"))


class HashtagKeepsBrandCase(unittest.TestCase):
    """r1019 N2-18: a single title hashtag that is a name in the app's search dictionary keeps its case,
    parity with the apps' splitTitleHashtags (HASHTAG_KEEP_LOWER from data/SearchDictionary.kt).
    Positive control: without an app key (the r1010 rule) the same names are split."""

    def test_hashtag_keeps_brand_case(self):
        self.assertEqual("NewJeans comeback", bake.split_single_hashtags("#NewJeans comeback", "kpop_en"))
        self.assertEqual("iKON and SHINee", bake.split_single_hashtags("#iKON and #SHINee", "tropic_vi"))
        self.assertEqual("NewJeans comeback", bake.split_single_hashtags("#NewJeans comeback", "hype_id"))
        self.assertEqual("OpenAI ships a model", bake.split_single_hashtags("#OpenAI ships a model", "circuitly_de"))
        self.assertEqual("JPMorgan beats estimates", bake.split_single_hashtags("#JPMorgan beats estimates", "tickerly_en"))
        self.assertIn("NewJeans comeback", bake.text_for(_art("#NewJeans comeback"), "kpop_en"))

    def test_the_r1010_split_stays(self):
        self.assertEqual("Song Yuqi returns", bake.split_single_hashtags("#SongYuqi returns", "kpop_en"))
        self.assertEqual("Salman Khan returns", bake.split_single_hashtags("#SalmanKhan returns", "bollywood_hi"))
        self.assertEqual("One Piece returns", bake.split_single_hashtags("#OnePiece returns", "anime_en"))
        self.assertEqual("BTS Army floods the timeline", bake.split_single_hashtags("#BTSArmy floods the timeline", "kpop_en"))

    def test_positive_control_without_the_keep_list(self):
        self.assertEqual("New Jeans comeback", bake.split_single_hashtags("#NewJeans comeback"))
        self.assertEqual("i KON returns", bake.split_single_hashtags("#iKON returns", "unknown_xx"))

    def test_every_manifest_key_has_a_keep_list(self):
        keys = {m["phonetics"] for m in bake.MANIFESTS} | {a.get("phonetics", a["slug"]) for a in bake.APPS}
        for k in sorted(keys):
            self.assertTrue(bake.hashtag_keep_for(k), k)

    def test_keep_list_matches_the_apps(self):
        """hashtag_keep.json is generated from the apps' data/SearchDictionary.kt; skipped where the app
        repo is not checked out (CI)."""
        import importlib.util
        import os
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        spec = importlib.util.spec_from_file_location("sync_hashtag_keep", os.path.join(root, "tools", "sync_hashtag_keep.py"))
        sync = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sync)
        if not os.path.isdir(sync.DEFAULT_APPS_ROOT):
            self.skipTest("app repo not present")
        want = {k: frozenset(v) for k, v in sync.build(sync.DEFAULT_APPS_ROOT).items()}
        self.assertEqual(want, dict(bake.HASHTAG_KEEP))


if __name__ == "__main__":
    unittest.main()
