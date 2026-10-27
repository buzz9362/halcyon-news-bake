"""r1027 W58-15 (Oct 27 2026): SEO spam from a hacked non-topic site ("Anime Ai Free Premium Account Advanced AI
Girlfriend Chat {us45RT}", outlet "NYC Health + Hospitals") reached the anime-brief queue and was read aloud.
is_spam_title drops it through is_low_value_story (drops_row: never in a manifest). The news apps'
R1027DataLayerTest pins the SAME vectors against FeedQuality.kt isSpamTitle.

Run from the repo root:  python -m unittest discover -s tests
Positive control: the pre-r1027 is_low_value_story (no spam step) kept the owner sample.
"""
import unittest

import test_throttle as tt

bake = tt.bake

SPAM = [
    "Anime Ai Free Premium Account Advanced AI Girlfriend Chat {us45RT}",
    "Crunchyroll Free Premium Account 2026 {x7Kp2Q}",
    "Genshin Impact unlimited gems no human verification",
    "Roblox free robux generator",
    "Anime Fighters mod apk download latest",
]
KEEP = [
    "Crunchyroll raises the price of its premium tier",
    "One Piece chapter 1130 delayed a week",
    "AI girlfriend apps face new scrutiny in Japan",
    "Function f(x) {return x} explained",
    "Studio Ghibli opens a free exhibition in Tokyo",
]


class SpamTitle(unittest.TestCase):
    def test_spam_titles_are_dropped(self):
        for t in SPAM:
            self.assertTrue(bake.is_spam_title(t), t)
            self.assertTrue(bake.is_low_value_story(t, "https://www.nychealthandhospitals.org/x"), t)

    def test_news_titles_stay(self):
        for t in KEEP:
            self.assertFalse(bake.is_spam_title(t), t)
            self.assertFalse(bake.is_low_value_story(t, "https://example.com/a"), t)

    def test_drops_row_on_every_manifest(self):
        art = {"title": SPAM[0], "articleUrl": "https://www.nychealthandhospitals.org/x"}
        for manifest in ("anime_en", "kpop_en", "tickerly_en", "circuitly_de"):
            self.assertTrue(bake.drops_row(art, manifest), manifest)

    def test_positive_control_old_rule_kept_the_owner_sample(self):
        t = " " + SPAM[0].lower() + " "
        self.assertFalse(any(m in t for m in bake._COMMERCE_CORE))
        self.assertFalse(bake._is_template_title(t))



class OffTopicOutlet(unittest.TestCase):
    """r1027 W58-15 / W54-1: the outlet gate, same list as the apps' FeedQuality.isOffTopicOutlet (R1027DataLayerTest)."""

    def test_institutions_are_dropped(self):
        for p in ("NYC Health + Hospitals", "Mount Sinai Medical Center", "Kaiser Permanente Health System",
                  "Department of Education", "County of Los Angeles", "City of Austin", "Ministry of Culture", "cdc.gov"):
            self.assertTrue(bake.is_off_topic_outlet(p), p)

    def test_news_outlets_stay(self):
        for p in (None, "", "Crunchyroll News", "Anime News Network", "Soompi", "BBC News", "Men's Health",
                  "Vatican News", "The Korea Times"):
            self.assertFalse(bake.is_off_topic_outlet(p), p)

    def test_drops_row_by_publisher_with_a_clean_title(self):
        art = {"title": "Top 10 anime of the season", "articleUrl": "https://news.google.com/x",
               "source": "Google News Anime", "realPublisher": "NYC Health + Hospitals"}
        self.assertTrue(bake.drops_row(art, "anime_en"))
        art["realPublisher"] = "Anime News Network"
        self.assertFalse(bake.drops_row(art, "anime_en"))
        self.assertTrue(bake.drops_row({"title": "x y z", "articleUrl": "", "source": "NYC Health + Hospitals"}, "anime_en"))


if __name__ == "__main__":
    unittest.main()
