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


if __name__ == "__main__":
    unittest.main()
