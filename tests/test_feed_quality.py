"""Oct 8 2026 (r1007 BK): the news apps' r1007 feed-quality rules on the baked appning path.

The 8 news apps (App Market Submission, r1007 NS lane) strip syndication footers, decode a
double-encoded entity once, repair a cut Times of India title, cut a chained outlet suffix, and drop
low-value, template and profane rows and near-duplicate stories, on the phone AND on the appning
manifest. The baker still voiced the text and baked the rows. Each rule here is pinned by the apps'
own test vectors (FeedQualityTest, TextUtilsTest, CreditAndTitleTest of kpop-today-app; the 8 apps'
FeedQuality.kt files are identical), plus whole passes through bake.main() with real manifest items
of Oct 8 2026 (kpop_en, hype_id, tickerly_en, kpop_es).

  BAKER-1 footer strip            Footer, EndToEnd.test_r9_*
  BAKER-2 double-encoded entity   Entities
  BAKER-3 window age cap          EndToEnd.test_window_items_past_two_weeks_*
  BAKER-4 rows the car hides      LowValueRows, NearDuplicates, EndToEnd.test_no_mp3_*, *_unbaked_copy_*
  BAKER-6 cut and chained titles  Titles
  SSOT parity with the apps' Kotlin (skipped when App Market Submission is not beside this repo)

Run from the repo root:  python -m pytest tests -q
Positive control: BAKE_PY=<pre-r1007 bake.py> python -m pytest tests/test_feed_quality.py runs the same
tests against the old code; every rule test fails there (the BK report lists the run).
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

import test_throttle as tt

bake = tt.bake
ROOT = tt.ROOT
APPS_ROOT = os.path.join(os.path.dirname(ROOT), "App Market Submission")
NEWS_APPS = ("kpop-today", "kpop-tropic", "bollywood-today", "circuitly", "tickerly", "anime-brief", "hype-id", "tinh-tu")
NOW = int(time.time() * 1000)
HOUR = 3600 * 1000

# Real items of the live manifests, Oct 8 2026.
SOOMPI = {"id": "rss_1nicx9o", "title": "Watch: &TEAM Introduces Official “TEAMILY” Characters For Each Member",
          "summary": "Meet the official “TEAMILY” characters for &TEAM! On October 6, &TEAM released an adorable video "
                     "introducing the “TEAMILY” characters representing each of the group’s members. Check out the new "
                     "introduction video and teaser image below! The post Watch: &TEAM Introduces Official “TEAMILY” "
                     "Characters For Each Member appeared first on Soompi.",
          "source": "Soompi", "sourceUrl": "https://www.soompi.com",
          "articleUrl": "https://www.soompi.com/article/1875835wpp/watch-team-introduces-official-teamily-characters-for-each-member",
          "imageUrl": None, "category": "en"}
LIPUTAN6_NEW = {"id": "rss_k9lcbi", "title": "Utamakan Pendidikan, Deretan Selebriti Indonesia Ini Pernah Berkuliah di Australia",
                "summary": "Sejumlah selebriti Indonesia menempuh pendidikan tinggi di Australia.", "source": "Liputan6 Showbiz",
                "articleUrl": "https://www.liputan6.com/showbiz/read/8307858/utamakan-pendidikan-deretan-selebriti-indonesia-ini-pernah-berkuliah-di-australia",
                "imageUrl": "https://cdn0-production-images-kly.akamaized.net/a/058560400_1791354518-New_Project__1_.jpg"}
LIPUTAN6_OLD = {"id": "rss_zzgfwv", "title": "Punya Ijazah Asli, Deretan Selebriti Indonesia Ini Pernah Berkuliah di Australia",
                "summary": "Sejumlah selebriti Indonesia menempuh pendidikan tinggi di Australia.", "source": "Liputan6 Showbiz",
                "articleUrl": "https://www.liputan6.com/showbiz/read/8307858/punya-ijazah-asli-deretan-selebriti-indonesia-ini-pernah-berkuliah-di-australia",
                "imageUrl": "https://cdn0-production-images-kly.akamaized.net/a/058560400_1791354518-New_Project__1_.jpg"}
TONCOIN = {"id": "rss_119on4q", "title": "Toncoin (TON) Price Prediction 2025, 2026, 2027-2030", "summary": "Toncoin outlook.",
           "source": "Benzinga", "articleUrl": "https://www.benzinga.com/money/toncoin-ton-price-prediction"}
TOP_STOCKS = {"id": "rss_1g48s89", "title": "Top Performing Stocks", "summary": "Stocks that performed best this month.",
              "source": "Benzinga", "articleUrl": "https://www.benzinga.com/money/stocks-to-buy-now"}
PROFANE = {"id": "rss_dck", "title": "“D*ck!” BTS Jin’s Unexpected Actions Towards BTS’s V Sparks Major Shock",
           "summary": "A clip from a variety show went viral this week.", "source": "Koreaboo",
           "articleUrl": "https://www.koreaboo.com/news/bts-jin-unexpected-actions-v/"}


def art(base, **kw):
    a = dict(base)
    a.update(kw)
    return a


def story(title, at, link=None, publisher=None, image="img"):
    """FeedQualityTest.story: the app fixture shape."""
    a = {"id": "id" + str(abs(hash(title))) + str(len(link or "")), "title": title, "summary": "", "source": "S",
         "sourceUrl": "https://outlet.example", "articleUrl": link or ("https://outlet.example/" + str(len(title))),
         "imageUrl": ("https://img.example/" + str(len(title)) + ".jpg") if image else None, "publishedAtMs": at}
    if publisher is not None:
        a["realPublisher"] = publisher
    return a


# ---------------------------------------------------------------- BAKER-1
class Footer(unittest.TestCase):
    def test_posted_first_footers_are_stripped(self):   # FeedQualityTest.posted_first_footers_are_stripped
        benzinga = ("Here are the platforms we like. The post Best Alternative Investment Platforms by A Writer "
                    "appeared first on Benzinga. Visit Benzinga to get more great content like this.")
        self.assertEqual("Here are the platforms we like.", bake.strip_posted_first_footer(benzinga))
        self.assertEqual("Body text.", bake.strip_posted_first_footer("Body text. The post Comeback Review appeared first on Seoulbeats."))
        self.assertEqual("Texto.", bake.strip_posted_first_footer("Texto. O post Novo single apareceu primeiro em Portal."))
        self.assertEqual("Nur Text.", bake.strip_posted_first_footer("Nur Text. Der Beitrag Neues Handy erschien zuerst auf Blog."))

    def test_a_dotted_site_name_and_a_cut_footer_strip_cleanly(self):   # FeedQualityTest (r1007 NS3)
        # Positive control: the old site tail stopped at the first "." ("Fintech news today.  com.") and the
        # old English cue needed "appeared first on" (a summary cut at "appeared first" kept the footer).
        self.assertEqual("Fintech news today.", bake.strip_posted_first_footer(
            "Fintech news today. The post Payments Firm Raises New Funds appeared first on PYMNTS.com."))
        self.assertEqual("Big week for chips.", bake.strip_posted_first_footer(
            "Big week for chips. The post Nvidia Earnings Preview appeared first"))
        self.assertEqual("Big week for chips.", bake.strip_posted_first_footer(
            "Big week for chips. The post Nvidia Earnings Preview appeared first on"))
        keep = "Samsung said the feature appeared first on its foldable phones."
        self.assertEqual(keep, bake.strip_posted_first_footer(keep))

    def test_ordinary_text_is_untouched(self):   # FeedQualityTest.ordinary_text_is_untouched
        s = "The first time the post office appeared on screen, fans cheered."
        self.assertEqual(s, bake.strip_posted_first_footer(s))
        self.assertEqual("No footer.", bake.strip_posted_first_footer("No footer."))

    def test_the_car_no_longer_voices_or_shows_a_footer(self):
        # Control: the raw worker summary carries the footer inside the voiced 350-char snippet.
        self.assertIn("appeared first on Soompi", bake.text_for(SOOMPI))
        clean = bake.sanitize_article(SOOMPI)
        self.assertNotIn("appeared first", clean["summary"])   # stored: the car shows what it hears
        voiced = bake.text_for(clean)
        self.assertNotIn("appeared first", voiced)
        self.assertTrue(voiced.endswith("Check out the new introduction video and teaser image below!"), voiced)


# ---------------------------------------------------------------- BAKER-2
class Entities(unittest.TestCase):
    def test_a_double_encoded_entity_decodes_once_fully(self):   # TextUtilsTest
        self.assertEqual("MC dẫn 'Vì bạn xứng đáng' thay MC",
                         bake.decode_entities("MC dẫn &amp;apos;Vì bạn xứng đáng&amp;apos; thay MC"))
        self.assertEqual("Kim & Park", bake.decode_entities("Kim &amp;amp; Park"))
        self.assertEqual("BTS’s tour", bake.decode_entities("BTS&amp;#8217;s tour"))
        self.assertEqual("AT&T; plan", bake.decode_entities("AT&amp;T; plan"))   # an unknown name stays

    def test_plain_entities_and_text(self):
        self.assertEqual("A & B", bake.decode_entities("A &amp; B"))
        self.assertEqual("Café «»", bake.decode_entities("Caf&eacute; &laquo;&raquo;"))
        self.assertEqual("no entity", bake.decode_entities("no entity"))
        self.assertEqual("ab", bake.decode_entities("a​b"))

    def test_the_voiced_title_has_no_entity_name(self):
        raw = {"id": "rss_vnn", "title": "MC dẫn &amp;apos;Vì bạn xứng đáng&amp;apos; thay MC Quyền Linh",
               "summary": "Chương trình có MC mới từ tuần này.", "source": "VietnamNet Giải trí"}
        self.assertIn("&apos;", bake.text_for(raw))   # control: clean_text alone leaves "&apos;"
        voiced = bake.text_for(bake.sanitize_article(raw))
        self.assertNotIn("&", voiced)
        self.assertIn("'Vì bạn xứng đáng'", voiced)


# ---------------------------------------------------------------- BAKER-4 (stateless rows)
class LowValueRows(unittest.TestCase):
    def test_template_catalog_and_deal_rows_are_low_value(self):   # FeedQualityTest
        lv = bake.is_low_value_story
        self.assertTrue(lv("Best REIT Stocks Right Now", "https://www.benzinga.com/money/best-reit-stocks-right-now"))
        self.assertTrue(lv("Renewable Energy Stocks", "https://www.benzinga.com/money/best-renewable-energy-stocks", shop_markers=False))
        self.assertTrue(lv("XRP Price Prediction 2025, 2026, 2030", "https://example.com/xrp"))
        self.assertTrue(lv("Naruto Shippuden: The Assembly of the Five Kage (Telugu Dub) - Episode 215 - Two Fates", "http://www.crunchyroll.com/watch/x"))
        self.assertTrue(lv("13 tech bargains for only $13 or less to upgrade your desktop PC setup", "https://www.tomshardware.com/x"))
        self.assertTrue(lv("'KPop Demon Hunters' Merch Is Up to Nearly 60% Off During October Prime Day - Billboard", "https://news.google.com/x"))
        self.assertTrue(lv("Anzeige: Dashcam für vorne und hinten am Prime Day für nur 47,45 Euro", "https://www.golem.de/x"))
        self.assertTrue(lv("The best October Prime Day deals from Apple, Sony, Google, and more", "https://news.google.com/x", shop_markers=False))
        self.assertTrue(lv("Samsung Galaxy Z Flip 8 a 729 euro su Amazon, sconto del 47%", "https://www.tecnoandroid.it/x"))
        self.assertTrue(lv("MSI PRO MP165A E6 a 89 euro: monitor portatile al minimo storico", "https://www.tecnoandroid.it/y"))

    def test_real_news_is_not_low_value(self):   # FeedQualityTest
        lv = bake.is_low_value_story
        self.assertFalse(lv("Kakao Entertainment strikes K-pop partnership with Atlantic Music Group", "https://example.com/a"))
        self.assertFalse(lv("Seol In Ah Deals With Yim Si Wan's Duality In New Drama", "https://www.soompi.com/a"))
        self.assertFalse(lv("Goldman raises its oil price prediction after OPEC cut", "https://example.com/b"))
        self.assertFalse(lv("Detective Conan (1214-current) - Episode 1215 - The Crimson Closing Day", "http://www.crunchyroll.com/watch/y"))
        self.assertFalse(lv("Benzinga: Nvidia rallies after earnings", "https://www.benzinga.com/news/26/10/123/nvidia"))
        self.assertFalse(lv("Chip stocks trade 40% off their peak", "https://example.com/c", shop_markers=False))

    def test_wire_templates_are_low_value(self):   # FeedQualityTest
        lv = bake.is_low_value_story
        self.assertTrue(lv("Piper Sandler reiterates Federal Realty stock rating on upside", "https://www.investing.com/x", shop_markers=False))
        self.assertTrue(lv("Piper Sandler cuts Live Oak Bancshares price target on provision concerns", "https://www.investing.com/y", shop_markers=False))
        self.assertTrue(lv("BTB Real Estate Investment Trust declares CAD 0.025 dividend", "https://seekingalpha.com/z", shop_markers=False))
        self.assertTrue(lv("Sinopsis Sinetron Biarkan Hati Bicara Episode 66, Rabu 7 Oktober 2026 Pukul 21.21 WIB di SCTV", "https://www.liputan6.com/a"))
        self.assertTrue(lv("Sinopsis The Bricklayer, Bioskop Trans TV 7 Oktober 2026", "https://www.cnnindonesia.com/b"))
        self.assertTrue(lv("Top Performing Stocks", "https://www.benzinga.com/money/stocks-to-buy-now", shop_markers=False))

    def test_real_stories_are_not_templates(self):   # FeedQualityTest
        lv = bake.is_low_value_story
        self.assertFalse(lv("Goldman lifts its S&P 500 year-end target to 7,400", "https://example.com/c", shop_markers=False))
        self.assertFalse(lv("Sinopsis Carrie, Serial Horor Stephen King Garapan Mike Flanagan", "https://www.cnnindonesia.com/d"))
        self.assertFalse(lv("Apple raises its dividend and expands buybacks", "https://example.com/e", shop_markers=False))

    def test_profane_and_censored_headlines_are_caught(self):   # FeedQualityTest
        self.assertTrue(bake.is_profane_title("\"D*ck!\" BTS Jin's Unexpected Actions Towards BTS's V Sparks Major Shock"))
        self.assertTrue(bake.is_profane_title("Rapper says the F**k word on live TV"))
        self.assertTrue(bake.is_profane_title("Star calls the critics bullshit"))

    def test_names_and_stars_are_not_profanity(self):   # FeedQualityTest
        self.assertFalse(bake.is_profane_title("Dickens adaptation casts a Hancock star"))
        self.assertFalse(bake.is_profane_title("Dick Van Dyke turns 100"))
        self.assertFalse(bake.is_profane_title("Rated 5* by critics: the *new* album"))

    def test_shop_markers_follow_the_app(self):
        # The apps pass shopMarkers = false on the manifest only in Tickerly (finance).
        self.assertFalse(bake.shop_markers_for("tickerly_en"))
        self.assertFalse(bake.shop_markers_for("tickerly_hi"))
        for m in bake.MANIFESTS:
            if not m["manifest"].startswith("tickerly_"):
                self.assertTrue(bake.shop_markers_for(m["manifest"]), m["manifest"])
        self.assertTrue(bake.drops_row(TONCOIN, "tickerly_en"))
        self.assertTrue(bake.drops_row(TOP_STOCKS, "tickerly_en"))
        self.assertTrue(bake.drops_row(PROFANE, "kpop_en"))
        self.assertFalse(bake.drops_row({"title": "Chip stocks trade 40% off their peak", "articleUrl": "https://x.example/c"}, "tickerly_en"))
        self.assertTrue(bake.drops_row({"title": "Chip stocks trade 40% off their peak", "articleUrl": "https://x.example/c"}, "circuitly_en"))


# ---------------------------------------------------------------- BAKER-4 (near-duplicates)
class NearDuplicates(unittest.TestCase):
    def test_one_story_from_several_outlets_is_one_row(self):   # FeedQualityTest
        nd, tk = bake.is_near_duplicate_title, bake.near_dup_tokens
        self.assertTrue(nd(tk("HYBE set to bring K-pop festival Weverse Con to India - The Hindu"),
                           tk("India gets its own Weverse Con Festival: HYBE, agency behind BTS, SEVENTEEN, to bring global K-pop event to New Delhi - Hindustan Times")))
        self.assertTrue(nd(tk("Kangana Ranaut moves Delhi high court seeking protection of personality rights"),
                           tk("Kangana Ranaut seeks Delhi High Court protection over misuse of personality rights")))
        self.assertTrue(nd(tk("MC Quyền Linh bị thay thế"), tk("MC Quyền Linh bị thay thế")))
        self.assertTrue(nd(tk("Walking Home with You Anime Premieres in April 2027 - Crunchyroll"),
                           tk("Walking Home with You TV Anime Reveals April 2027 Premiere")))

    def test_distinct_stories_about_one_artist_stay_apart(self):   # FeedQualityTest
        nd, tk = bake.is_near_duplicate_title, bake.near_dup_tokens
        self.assertFalse(nd(tk("BTS won't submit music for 2027 Grammy Awards consideration"), tk("Stray Kids won't submit music for 2027 Grammys")))
        self.assertFalse(nd(tk("BLACKPINK Jennie's Speculated To Be On Hiatus, Sparks Major Reactions"), tk("Jennie releases new solo single teaser")))
        self.assertFalse(nd(tk("Drishyam 3 Box Office Day 5: crosses 200 crore"), tk("Drishyam 3 Box Office Day 6: crosses 220 crore")))
        self.assertFalse(nd(tk("Lisa (BlackPink) lại thành tâm điểm"),
                            tk("Lisa (BlackPink) diện gợi cảm, đọ sắc Zendaya, Emma Stone")))

    def test_the_best_copy_survives_in_list_order(self):   # FeedQualityTest
        now = 1_800_000_000_000
        aggregator = story("Kangana Ranaut moves Delhi high court seeking protection of personality rights - The Hindu", now,
                           link="https://news.google.com/rss/articles/abc", publisher="The Hindu")
        direct = story("Kangana Ranaut seeks Delhi High Court protection over misuse of personality rights", now - 3_600_000)
        other = story("Kiara Advani announces second pregnancy", now - 60_000)
        self.assertEqual([other, direct], bake.dedupe_near_duplicates([aggregator, other, direct]))
        old = story("Kangana Ranaut seeks Delhi High Court protection over misuse of personality rights", now - 40 * 3_600_000,
                    link="https://outlet.example/old")
        self.assertEqual(2, len(bake.dedupe_near_duplicates([direct, old])))

    def test_a_retitled_story_is_one_row(self):   # FeedQualityTest (car walk 5556, Hype ID)
        now = 1_800_000_000_000
        newer = story(LIPUTAN6_NEW["title"], now, link=LIPUTAN6_NEW["articleUrl"])
        older = story(LIPUTAN6_OLD["title"], now - 3_128_000, link=LIPUTAN6_OLD["articleUrl"])
        # Control: the headline rule alone keeps both (6 of 8 words shared).
        self.assertFalse(bake.is_near_duplicate_title(bake.near_dup_tokens(newer["title"]), bake.near_dup_tokens(older["title"])))
        self.assertEqual([newer], bake.dedupe_near_duplicates([newer, older]))

    def test_article_numbers_skip_dates_and_aggregators(self):   # FeedQualityTest
        k = bake.article_number_key
        self.assertEqual("liputan6.com|8307858", k("https://www.liputan6.com/showbiz/read/8307858/slug"))
        self.assertEqual("cnnindonesia.com|20261007134512|1234567", k("https://www.cnnindonesia.com/hiburan/20261007134512-234-1234567/slug"))
        self.assertIsNone(k("https://outlet.example/2026/10/07/slug"))
        self.assertIsNone(k("https://outlet.example/20261007/slug"))
        self.assertIsNone(k("https://news.google.com/rss/articles/CBMi123456789"))
        now = 1_800_000_000_000
        a = story("Raisa rilis album baru bersama Isyana", now, link="https://www.liputan6.com/showbiz/read/8307001/a")
        b = story("Raisa rilis singel baru untuk film", now, link="https://www.liputan6.com/showbiz/read/8307002/b")
        self.assertEqual(2, len(bake.dedupe_near_duplicates([a, b])))

    def test_a_story_with_an_mp3_wins_over_an_unbaked_copy(self):
        # Baker only: prefer ranks the confirmed copy first, whatever the app's rank says.
        now = 1_800_000_000_000
        listed = story(LIPUTAN6_OLD["title"], now - 3_128_000, link=LIPUTAN6_OLD["articleUrl"], image=None)
        fresh = story(LIPUTAN6_NEW["title"], now, link=LIPUTAN6_NEW["articleUrl"])
        self.assertEqual([fresh], bake.dedupe_near_duplicates([fresh, listed]))   # the app keeps the one with a picture
        self.assertEqual([listed], bake.dedupe_near_duplicates([fresh, listed], prefer=lambda a: a is listed))


# ---------------------------------------------------------------- BAKER-6
class Titles(unittest.TestCase):
    TOI_HEAD = "Drishyam 3 box office day 9: Ajay Devgn, Jd. Ahlawat starrer sees a jump; India net reaches Rs 111 cr; wo"

    def test_a_cut_times_of_india_headline_ends_at_a_whole_word(self):   # FeedQualityTest
        head = self.TOI_HEAD
        self.assertEqual(105, len(head))
        fixed = bake.repair_cut_headline(head + " - The Times of India", "The Times of India")
        self.assertTrue(fixed.endswith("Rs 111 cr... - The Times of India"), fixed)
        self.assertEqual(head + " - Mid-Day", bake.repair_cut_headline(head + " - Mid-Day", "Mid-Day"))
        self.assertEqual("Short TOI headline - The Times of India",
                         bake.repair_cut_headline("Short TOI headline - The Times of India", "The Times of India"))

    def test_a_cut_toi_title_is_stored_and_voiced_whole_words(self):
        raw = {"id": "rss_toi", "title": self.TOI_HEAD, "summary": "Ajay Devgn's film gained on its second Saturday.",
               "source": "Times of India Entertainment"}
        self.assertIn("; wo .", bake.text_for(raw))   # control: the fragment is voiced today
        clean = bake.sanitize_article(raw)
        self.assertTrue(clean["title"].endswith("reaches Rs 111 cr..."), clean["title"])
        self.assertNotIn("; wo", bake.text_for(clean))

    def test_a_chained_outlet_suffix_is_cut_once_and_for_all(self):   # CreditAndTitleTest
        self.assertEqual("India gets its own Weverse Con Festival in March 2027",
                         bake.strip_outlet_suffix("India gets its own Weverse Con Festival in March 2027 | Hindustan Times - Hindustan Times", "Hindustan Times"))
        self.assertEqual("Kiara Advani announces second pregnancy",
                         bake.strip_outlet_suffix("Kiara Advani announces second pregnancy - The Times of India", "The Times of India"))
        # A worker edition tag on the source is not part of the name in the title.
        self.assertEqual("BTS tẩy chay Grammy", bake.strip_outlet_suffix("BTS tẩy chay Grammy - Kenh14 Musik", "Kenh14 Musik (VN)"))

    def test_a_suffix_cut_never_changes_the_title_the_app_shows(self):
        # The app's display pass also cuts any short last segment. Cutting the outlet first would let it
        # eat "Remix" from the headline, so the title stays as it was.
        t = "Stray Kids drops a surprise single - Remix - Soompi"
        self.assertEqual("Stray Kids drops a surprise single - Remix", bake.device_clean_title(t, "Soompi"))
        self.assertEqual(t, bake.strip_outlet_suffix(t, "Soompi"))
        # Titles without the outlet are untouched.
        self.assertEqual("BTS - Dynamite review", bake.strip_outlet_suffix("BTS - Dynamite review", "Soompi"))
        self.assertEqual("No suffix here at all", bake.strip_outlet_suffix("No suffix here at all", "Soompi"))

    def test_the_voiced_title_reads_the_outlet_once(self):
        raw = {"id": "rss_ht", "title": "India gets its own Weverse Con Festival in March 2027 | Hindustan Times - Hindustan Times",
               "summary": "HYBE will bring its K-pop festival to New Delhi next March.", "source": "Hindustan Times"}
        self.assertEqual(3, bake.text_for(raw).count("Hindustan Times"))   # control
        self.assertEqual(1, bake.text_for(bake.sanitize_article(raw)).count("Hindustan Times"))


# ---------------------------------------------------------------- whole passes (bake.main)
class Tts:
    def __init__(self):
        self.texts = []

    def __call__(self, text, lang, tld):
        self.texts.append(text)
        return b"new"


def run(w, tts):
    bake._STARVED.clear()
    bake._retext_cut.clear()
    out = io.StringIO()
    with contextlib.ExitStack() as st:
        for p in (
            mock.patch.object(bake, "s3", w.s3),
            mock.patch.object(bake, "requests", w.requests),
            mock.patch.object(bake, "synth_to_mp3", tts),
            mock.patch.object(bake, "_sleep", lambda s: None, create=True),
            mock.patch.object(bake, "MANIFESTS", w.manifests),
            mock.patch.object(bake, "FORCE_APP", ""),
            mock.patch.object(bake, "RETEXT_APPS", set()),
            mock.patch.object(bake, "retext_targeted", return_value={}),
            mock.patch.object(bake, "retext_priority", lambda: {}, create=True),
            mock.patch.object(bake, "SOUNDICA_FM_COMPONENTS", {}),
        ):
            st.enter_context(p)
        st.enter_context(contextlib.redirect_stdout(out))
        rc = bake.main()
    bake._STARVED.clear()
    return rc, out.getvalue()


def world(name, feed, baked=(), prev=()):
    """One manifest. feed: articles in the worker window; baked: ids with an old MP3 in R2;
    prev: articles of the live manifest (the carry-forward)."""
    w = tt.World([name], fresh=0, old=0)
    w.requests.feeds[f"https://t/{name}"] = [dict(a) for a in feed]
    for sid in baked:
        w.s3.objs[bake.article_key(sid)] = (b"old", tt.OLD_MP3)
    if prev:
        w.s3.objs[f"{name}.json"] = (json.dumps({"items": [dict(a) for a in prev]}).encode(), tt.OLD_MP3)
    return w


def listed(w, name):
    return [a["id"] for a in (w.s3.manifest(name) or [])]


def filler(prefix, n, age_h=2):
    return [tt.story(f"{prefix}-{k}", age_h * 60 + k) for k in range(n)]


class EndToEnd(unittest.TestCase):
    def test_no_mp3_is_baked_for_a_row_the_car_hides(self):
        # tickerly_en, Oct 8: Benzinga's evergreen /money/ pages; kpop_en: the censored Koreaboo headline.
        fill = filler("tk", 5)
        feed = [art(TONCOIN, publishedAtMs=NOW - HOUR), art(TOP_STOCKS, publishedAtMs=NOW - HOUR),
                art(PROFANE, publishedAtMs=NOW - HOUR), tt.story("tk-fresh", 30)] + fill
        # The live manifest still lists an older Benzinga guide page; it is not carried forward.
        old_guide = {"id": "rss_guide", "title": "Best REIT Stocks Right Now", "summary": "REITs.", "source": "Benzinga",
                     "articleUrl": "https://www.benzinga.com/money/best-reit-stocks-right-now", "publishedAtMs": NOW - 20 * HOUR}
        w = world("tickerly_en", feed, baked=[a["id"] for a in fill] + ["rss_guide"], prev=[old_guide])
        tts = Tts()
        rc, out = run(w, tts)
        voiced = " ".join(tts.texts)
        for t in ("Price Prediction", "Top Performing", "D*ck"):
            self.assertNotIn(t, voiced)
        self.assertIn("Story tk-fresh ", voiced)   # control: the real story of the same pass is baked
        ids = listed(w, "tickerly_en")
        for sid in (TONCOIN["id"], TOP_STOCKS["id"], PROFANE["id"], "rss_guide"):
            self.assertNotIn(sid, ids)
            self.assertNotIn(bake.article_key(sid), {k for k, v in w.s3.objs.items() if v[0] == b"new"})
        self.assertIn("tk-fresh", ids)
        self.assertIn("r1007: 3 rows the app drops", out)

    def test_an_unbaked_copy_of_a_listed_story_is_not_baked(self):
        # hype_id, Oct 8: Liputan6 re-titled article 8307858; the older title is already baked.
        fill = filler("hy", 5)
        feed = [art(LIPUTAN6_NEW, publishedAtMs=NOW - HOUR), art(LIPUTAN6_OLD, publishedAtMs=NOW - 2 * HOUR),
                # two outlets' copies of one new story, neither baked yet: only the first is baked
                {"id": "rss_kr1", "title": "Kangana Ranaut moves Delhi high court seeking protection of personality rights",
                 "summary": "The actor asked the court to stop misuse of her name.", "source": "Outlet A",
                 "articleUrl": "https://a.example/kangana", "imageUrl": "https://a.example/k.jpg", "publishedAtMs": NOW - 30 * 60 * 1000},
                {"id": "rss_kr2", "title": "Kangana Ranaut seeks Delhi High Court protection over misuse of personality rights",
                 "summary": "The actor went to court over her personality rights.", "source": "Outlet B",
                 "articleUrl": "https://b.example/kangana", "imageUrl": "https://b.example/k.jpg", "publishedAtMs": NOW - 40 * 60 * 1000},
                # control: another article of the same site (another number) is its own story
                {"id": "rss_raisa", "title": "Raisa rilis singel baru untuk film", "summary": "Raisa merilis singel baru untuk sebuah film.",
                 "source": "Liputan6 Showbiz", "articleUrl": "https://www.liputan6.com/showbiz/read/8307002/b", "publishedAtMs": NOW - HOUR}] + fill
        w = world("hype_id", feed, baked=[a["id"] for a in fill] + [LIPUTAN6_OLD["id"]])
        tts = Tts()
        run(w, tts)
        voiced = " ".join(tts.texts)
        self.assertNotIn("Utamakan Pendidikan", voiced)                  # the re-titled copy is not baked
        self.assertEqual(1, voiced.count("Kangana Ranaut"))              # one copy of the new story
        self.assertIn("Raisa rilis singel", voiced)
        ids = listed(w, "hype_id")
        self.assertIn(LIPUTAN6_OLD["id"], ids)                          # the listed copy stays listed
        self.assertNotIn(LIPUTAN6_NEW["id"], ids)
        self.assertEqual(1, len({"rss_kr1", "rss_kr2"} & set(ids)))
        tt.World.assert_manifests_confirmed(w, self)

    def test_a_copy_of_a_carried_story_is_not_baked(self):
        # The car still plays the first copy from the carry-forward; a second outlet's copy arrives.
        fill = filler("kc", 5)
        first = {"id": "rss_bts1", "title": "BTS won't submit music for 2027 Grammy Awards consideration", "summary": "HYBE confirmed it.",
                 "source": "Soompi", "articleUrl": "https://www.soompi.com/article/bts-grammy", "imageUrl": "https://img.example/1.jpg",
                 "publishedAtMs": NOW - 20 * HOUR}
        copy = {"id": "rss_bts2", "title": "BTS won't submit music for 2027 Grammy Awards consideration, agency says",
                "summary": "The agency confirmed the decision.", "source": "Koreaboo", "articleUrl": "https://www.koreaboo.com/news/bts-grammy/",
                "imageUrl": "https://img.example/2.jpg", "publishedAtMs": NOW - 18 * HOUR}
        other = {"id": "rss_skz", "title": "Stray Kids won't submit music for 2027 Grammys", "summary": "JYP confirmed it.",
                 "source": "Koreaboo", "articleUrl": "https://www.koreaboo.com/news/skz-grammy/", "publishedAtMs": NOW - 17 * HOUR}
        w = world("kpop_en", [copy, other] + fill, baked=[a["id"] for a in fill] + ["rss_bts1"], prev=[first])
        tts = Tts()
        run(w, tts)
        voiced = " ".join(tts.texts)
        self.assertNotIn("agency says", voiced)
        self.assertIn("Stray Kids", voiced)   # control: a different story with shared words is baked
        ids = listed(w, "kpop_en")
        self.assertIn("rss_bts1", ids)
        self.assertNotIn("rss_bts2", ids)

    def test_window_items_past_two_weeks_are_neither_baked_nor_listed(self):
        # kpop_es, Oct 8: HallyuReviews roundups of May (5,037 h) sat in the manifest.
        day = 24 * HOUR
        fill = filler("es", 5)
        feed = [{"id": "rss_old_fresh", "title": "YENA Is Back To Catch Catch Us", "summary": "A review of YENA's comeback.",
                 "source": "HallyuReviews", "articleUrl": "https://hallyureviews.example/yena", "publishedAtMs": NOW - 15 * day},
                {"id": "rss_old_listed", "title": "K-POP Releases We Missed: March 2026 Roundup", "summary": "The March releases.",
                 "source": "HallyuReviews", "articleUrl": "https://hallyureviews.example/march", "publishedAtMs": NOW - 189 * day},
                {"id": "rss_13d", "title": "Dónde y cuándo ver tus premios coreanos favoritos", "summary": "Las fechas de los premios.",
                 "source": "Con K de Kpop", "articleUrl": "https://conk.example/premios", "publishedAtMs": NOW - 13 * day}] + fill
        w = world("kpop_es", feed, baked=[a["id"] for a in fill] + ["rss_old_listed"])
        tts = Tts()
        rc, out = run(w, tts)
        voiced = " ".join(tts.texts)
        self.assertNotIn("YENA", voiced)
        self.assertIn("premios coreanos", voiced)   # control: 13 days old is kept
        ids = listed(w, "kpop_es")
        self.assertNotIn("rss_old_listed", ids)
        self.assertNotIn("rss_old_fresh", ids)
        self.assertIn("rss_13d", ids)
        self.assertIn("2 older than 14 days", out)

    def test_r9_revoices_a_listed_story_whose_voice_changed_once(self):
        fill = filler("kp", 5)
        long_body = "Seventeen announced a world tour with stops in twelve cities. " * 8   # 488 chars
        far = {"id": "rss_far", "title": "SEVENTEEN Announces World Tour Dates For Next Year", "source": "Soompi",
               "summary": long_body + "The post SEVENTEEN Announces World Tour Dates appeared first on Soompi.",
               "articleUrl": "https://www.soompi.com/article/far", "publishedAtMs": NOW - 2 * HOUR}
        carried = art(SOOMPI, id="rss_carried", title="Watch: NCT WISH Shares A New Teaser For Their Comeback",
                      articleUrl="https://www.soompi.com/article/carried", publishedAtMs=NOW - 30 * HOUR)
        feed = [art(SOOMPI, publishedAtMs=NOW - HOUR), far] + fill
        w = world("kpop_en", feed, baked=[a["id"] for a in fill] + [SOOMPI["id"], "rss_far", "rss_carried"], prev=[carried])
        tts = Tts()
        run(w, tts)
        # (the kpop_en table voices "&TEAM" as "And Team", and the caps pass writes "Teamily")
        revoiced = [t for t in tts.texts if any(k in t.lower() for k in ("teamily", "teaser", "seventeen"))]
        self.assertEqual(2, len(revoiced), tts.texts)                   # the window story and the carried one
        self.assertTrue(all("appeared first" not in t for t in revoiced))
        self.assertEqual(b"new", w.s3.objs[bake.article_key(SOOMPI["id"])][0])
        self.assertEqual(b"new", w.s3.objs[bake.article_key("rss_carried")][0])
        self.assertEqual(b"old", w.s3.objs[bake.article_key("rss_far")][0])   # its footer is past the voiced snippet
        stored = {a["id"]: a for a in w.s3.manifest("kpop_en")}
        for sid in (SOOMPI["id"], "rss_far", "rss_carried"):
            self.assertNotIn("appeared first", stored[sid]["summary"])
        # Second pass: every re-voiced MP3 is newer than the r9 cutover; nothing is voiced again.
        tts2 = Tts()
        run(w, tts2)
        self.assertEqual([], tts2.texts)


# ---------------------------------------------------------------- SSOT parity with the apps' Kotlin
def _kt_strings(block: str) -> list:
    out = []
    for m in re.finditer(r'"((?:[^"\\]|\\.)*)"', block):
        s = m.group(1)
        s = re.sub(r"\\u([0-9a-fA-F]{4})", lambda u: chr(int(u.group(1), 16)), s)
        s = s.replace("\\$", "$").replace('\\"', '"').replace("\\\\", "\\")
        out.append(s)
    return out


def _kt_list(src: str, name: str) -> list:
    # One-line or multi-line listOf(...) / setOf(...): the list ends at the first ")" that ends a line.
    m = re.search(r"val " + name + r"\b[^=]*=\s*(?:listOf|setOf)\((.*?)\)[ \t]*$", src, re.S | re.M)
    if not m:
        raise AssertionError(f"{name} not found in FeedQuality.kt")
    # Whole-line // comments inside a list quote examples ("sconto del 47%"); they are not entries.
    return _kt_strings("\n".join(l for l in m.group(1).split("\n") if not l.strip().startswith("//")))


@unittest.skipUnless(os.path.isdir(APPS_ROOT), "App Market Submission is not beside this repo")
class AppParity(unittest.TestCase):
    def feed_quality(self, app):
        for dp, _dn, fns in os.walk(os.path.join(APPS_ROOT, f"{app}-app", "app", "src", "main")):
            if "FeedQuality.kt" in fns:
                with open(os.path.join(dp, "FeedQuality.kt"), encoding="utf-8") as f:
                    return f.read()
        raise AssertionError(f"no FeedQuality.kt in {app}")

    def test_the_8_apps_share_one_rule_file(self):
        def norm(s):
            return re.sub(r"\bcom\.[a-z]+\.[a-z]+(?:\.[a-z]+)?\.data\b", "PKG.data", re.sub(r"^package .*$", "", s, flags=re.M))
        base = norm(self.feed_quality(NEWS_APPS[0]))
        for app in NEWS_APPS[1:]:
            self.assertEqual(base, norm(self.feed_quality(app)), app)

    def test_lists_match_feed_quality_kt(self):
        src = self.feed_quality("kpop-today")
        self.assertEqual(list(bake._COMMERCE_CORE), _kt_list(src, "COMMERCE_CORE_MARKERS"))
        self.assertEqual(list(bake._COMMERCE_SHOP), _kt_list(src, "COMMERCE_SHOP_MARKERS"))
        self.assertEqual(list(bake._COMMERCE_PREFIXES), _kt_list(src, "COMMERCE_TITLE_PREFIXES"))
        self.assertEqual(list(bake._TARGET_VERBS), _kt_list(src, "TARGET_VERBS"))
        self.assertEqual(set(bake._PROFANE_WORDS), set(_kt_list(src, "PROFANE_WORDS")))
        self.assertEqual(set(bake._NEAR_DUP_STOP), set(_kt_list(src, "NEAR_DUP_STOP_WORDS")))
        self.assertEqual(list(bake._FOOTER_CUES), _kt_list(src, "FOOTER_CUES"))
        self.assertIn(f"TOI_TITLE_CUT = {bake.TOI_TITLE_CUT}", src)
        self.assertIn("NEAR_DUP_WINDOW_MS = 36L * 60L * 60L * 1000L", src)
        self.assertEqual(36 * 3600 * 1000, bake.NEAR_DUP_WINDOW_MS)

    def test_footer_pattern_matches_feed_quality_kt(self):
        src = self.feed_quality("kpop-today")
        m = re.search(r"POSTED_FIRST_FOOTER_REGEX = Regex\((.*?)RegexOption", src, re.S)
        kotlin = "".join(_kt_strings(m.group(1)))
        python = re.sub(r"\\u([0-9a-fA-F]{4})", lambda u: chr(int(u.group(1), 16)), bake._POSTED_FIRST_FOOTER.pattern)
        self.assertEqual(kotlin, python)

    def test_shop_markers_off_only_in_tickerly_manifests(self):
        off = set()
        for app in NEWS_APPS:
            for dp, _dn, fns in os.walk(os.path.join(APPS_ROOT, f"{app}-app", "app", "src", "main")):
                if "NewsApi.kt" in fns:
                    with open(os.path.join(dp, "NewsApi.kt"), encoding="utf-8") as f:
                        # The manifest read's filter chain (fetchManifest), one line in every app.
                        line = next(l for l in f if "dedupeMergedArticles(it.items)" in l and "isLowValueStory(" in l)
                    if "shopMarkers = false" in line:
                        off.add(app.split("-")[0])
        self.assertEqual(set(bake.SHOP_MARKERS_OFF_APPS), off)


if __name__ == "__main__":
    unittest.main()
