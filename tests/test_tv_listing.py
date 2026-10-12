"""r1010 N2-6 (Oct 12 2026, deferred item 1): Hype ID TV programme listing rows ("Saksikan Sinetron Kisah Nyata
Siang Minggu 11 Oktober Pukul 13.30 WIB di Indosiar", the bare "Kisah Nyata 13.30") are not baked or listed.
Twin of hype-id FeedQuality.kt isTvListingTitle (the last branch of its isTemplateTitle), Hype ID only. The 18
vectors are N2.md section 3, verbatim, the same ones TvListingTitleTest.kt pins.

Run from the repo root:  python -m unittest discover -s tests
Positive control: the live hype_id rows pass the pre-r1010 rung (_is_template_title, asserted below), so they
were baked and listed; against the pre-r1010 bake.py (BAKE_PY=<old copy>) test_the_18_vectors fails.
"""
import os
import re
import unittest

import test_feed_quality as fq

bake = fq.bake

DROP = [
    "Saksikan Sinetron Kisah Nyata Siang Minggu 11 Oktober Pukul 13.30 WIB di Indosiar",
    "Saksikan Sinetron Kisah Nyata Pagi Minggu 11 Oktober Pukul 08.30 WIB di Indosiar",
    "Kisah Nyata 13.30",
    "Kisah Nyata Siang 12.00 WIB",
    "Tonton FTV Pintu Berkah Hari Ini di Indosiar",
    "Jadwal Acara TV Hari Ini Minggu 11 Oktober 2026",
    "Sinetron Cinta Berkah Tayang Malam Ini Pukul 19.30 WIB di SCTV",
    "Live Streaming Konser Avenged Sevenfold di Vidio",
]
KEEP = [
    "Kabar Terbaru Pemain Sinetron Tersayang Setelah 27 Tahun Sejak Tayang Perdana",
    "Sinopsis Drama China The Lament of Autumn, Taruhan Cinta Panglima",
    "Gempa Guncang Bali Pukul 13.30 WIB, Warga Panik",
    "IHSG Ditutup Menguat Pukul 15.00 WIB",
    "IHSG Sesi I Ditutup Pukul 12.00",
    "Rupiah Dibuka Melemah Jam 09.00 WIB",
    "NPD Batal Manggung di Palembang Gegara Asap Karhutla, Pesawat Tak Bisa Landing",
    "Saksikan Momen Lucu Ranty Maria Masak untuk Rayn Wijaya",
    "Indosiar Umumkan Sinetron Baru untuk 2027",
    "Marvel Perlihatkan Episode 1 VisionQuest, Tuai Pujian",
]


def _row(title):
    return {"id": "rss_tv", "title": title, "summary": "Ringkasan.", "source": "Liputan6 Showbiz",
            "articleUrl": "https://www.liputan6.com/showbiz/read/1/x"}


class TvListing(unittest.TestCase):
    def test_old_rung_let_the_live_rows_through(self):   # positive control
        for title in DROP[:2]:
            self.assertFalse(bake._is_template_title(" " + title.lower() + " "), title)

    def test_the_18_vectors(self):
        for title in DROP:
            with self.subTest(drop=title):
                self.assertTrue(bake.drops_row(_row(title), "hype_id"))
                self.assertTrue(bake.is_tv_listing_title(title))
        for title in KEEP:
            with self.subTest(keep=title):
                self.assertFalse(bake.drops_row(_row(title), "hype_id"))
                self.assertFalse(bake.is_tv_listing_title(title))

    def test_hype_id_only(self):
        # The short-title rung stays away from the other manifests (finance titles that end in a time).
        self.assertFalse(bake.drops_row(_row("Kisah Nyata 13.30"), "kpop_en"))
        self.assertFalse(bake.drops_row(_row("Kisah Nyata 13.30"), "tropic_id"))
        self.assertTrue(bake.drops_row(_row("Kisah Nyata 13.30"), "hype_id"))


@unittest.skipUnless(os.path.isdir(fq.APPS_ROOT), "App Market Submission is not beside this repo")
class TvListingParity(unittest.TestCase):
    def test_lists_match_hype_id_feed_quality_kt(self):
        src = fq.AppParity.feed_quality(None, "hype-id")
        if "isTvListingTitle" not in src:
            self.skipTest("hype-id FeedQuality.kt has no isTvListingTitle yet")
        self.assertEqual(list(bake._TV_OPENERS), fq._kt_list(src, "TV_OPENERS"))
        self.assertEqual(list(bake._TV_JADWAL), fq._kt_list(src, "TV_JADWAL"))
        self.assertEqual(list(bake._TV_CHANNELS), fq._kt_list(src, "TV_CHANNELS"))
        self.assertEqual(list(bake._TV_SCHED), fq._kt_list(src, "TV_SCHED"))
        self.assertEqual(set(bake._TV_ZONES), set(fq._kt_list(src, "TV_ZONES")))
        self.assertIn("if (isTvListingTitle(t)) return true", src)
        self.assertTrue(re.search(r"w\.size in 2\.\.6 && isClockToken\(w\.last\(\)\)", src))


if __name__ == "__main__":
    unittest.main()
