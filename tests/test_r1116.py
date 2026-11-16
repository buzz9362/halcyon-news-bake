"""r1116 (Nov 17 2026) baker fixes: CN-05 spoken summary cut at a sentence end (TextCut.kt cutToBudget),
CN-06 unbracketed read-more tails, CN-04 per-source cap on the carry-forward, CN-15 Tickerly / Circuitly
topic gate. Each test holds the defect case and a control.

Run from the repo root:  python -m unittest discover -s tests
"""
import unittest
from unittest import mock

import test_feed_quality as fq

bake = fq.bake


class SummaryCut(unittest.TestCase):
    def test_short_summary_is_unchanged(self):   # control: the CN-05 test the report asked for
        art = {"id": "x", "title": "BTS returns", "summary": "The group confirmed a world tour for next year.", "source": "Soompi"}
        self.assertTrue(bake.text_for(art).endswith(" The group confirmed a world tour for next year."))
        s = "x" * 350
        self.assertEqual(s, bake.cut_to_budget(s, 350, 116))

    def test_long_summary_ends_on_a_sentence(self):
        s = ("Ngan hang Nha nuoc vua cong bo so lieu moi ve tang truong tin dung trong quy ba. " * 6).strip()
        out = bake.cut_to_budget(s, 350, 116)
        self.assertLessEqual(len(out), 350)
        self.assertTrue(out.endswith("."), out[-20:])
        self.assertTrue(s.startswith(out))

    def test_no_sentence_end_cuts_at_a_word(self):
        s = "word " * 100
        out = bake.cut_to_budget(s, 350, 116)
        self.assertTrue(out.endswith("word…"), out[-12:])
        self.assertLessEqual(len(out), 350)

    def test_abbreviation_and_number_dots_are_not_ends(self):
        s = "A" * 200 + " was seen with Dr. Kim at 2.5 x.com today and " + "b" * 200
        out = bake.cut_to_budget(s, 350, 116)
        self.assertNotIn(out[-4:], ("Dr.",))
        self.assertTrue(out.endswith("…"))

    def test_old_slice_cut_inside_a_word(self):   # positive control: the pre-r1116 slice
        s = "Mot " + "cau chuyen dai " * 40
        self.assertNotEqual(s[:350], bake.cut_to_budget(s, 350, 116))


class ReadMore(unittest.TestCase):
    def test_new_markers_cut(self):
        teaser = "Stray Kids will release a new mini album next month, the agency announced on Monday afternoon."
        self.assertEqual(teaser, bake.cut_read_more_promo(teaser + " Continue reading Stray Kids announce comeback"))
        t3n = "Der Konzern stellt seine KI-Strategie neu auf und gibt dem Assistenten eine neue Rolle"
        self.assertEqual(t3n, bake.cut_read_more_promo(t3n + "weiterlesen auf t3n.de"))
        viva = "Artis senior itu akhirnya buka suara soal kabar yang beredar luas di media sosial pekan ini."
        self.assertEqual(viva, bake.cut_read_more_promo(viva + " Simak selengkapnya."))

    def test_marker_early_in_text_stays(self):   # control: index floor 60
        s = "Continue reading the full interview with the band about their tour plans for next year."
        self.assertEqual(s, bake.cut_read_more_promo(s))


class CarrySourceCap(unittest.TestCase):
    def _plan(self, window, prev):
        return {"name": "tickerly_it", "window": window, "confirmed": {a["id"] for a in window},
                "prev_items": prev, "seen": {a["id"] for a in window}, "force": False}

    def test_one_outlet_cannot_take_the_carry_forward(self):
        import time
        now = int(time.time() * 1000)
        window = [{"id": f"w{i}", "title": f"Titolo borsa numero {i}", "summary": "", "source": "Il Sole 24 Ore",
                   "publishedAtMs": now - i * 60000} for i in range(30)]
        prev = [{"id": f"p{i}", "title": f"Notizia investimenti {i}", "summary": "", "source": "Investing.com Italia (IT)",
                 "publishedAtMs": now - 3600000 - i * 60000} for i in range(70)]
        prev += [{"id": f"q{i}", "title": f"Mercati europei {i}", "summary": "", "source": "Milano Finanza",
                  "publishedAtMs": now - 7200000 - i * 60000} for i in range(15)]
        written = {}
        with mock.patch.object(bake, "write_manifest", lambda n, items: written.setdefault(n, items)):
            bake.finalize_manifest(self._plan(window, prev))
        items = written["tickerly_it"]
        inv = sum(1 for a in items if a["source"].startswith("Investing"))
        self.assertLessEqual(inv, bake.CARRY_SOURCE_CAP)
        self.assertEqual(30, sum(1 for a in items if a["id"].startswith("w")))   # window rows all kept
        self.assertEqual(15, sum(1 for a in items if a["id"].startswith("q")))   # control: small outlet carried

    def test_window_rows_over_the_cap_are_kept(self):   # control
        import time
        now = int(time.time() * 1000)
        window = [{"id": f"w{i}", "title": f"Titolo {i}", "summary": "", "source": "Investing.com Italia (IT)",
                   "publishedAtMs": now - i * 60000} for i in range(40)]
        written = {}
        with mock.patch.object(bake, "write_manifest", lambda n, items: written.setdefault(n, items)):
            bake.finalize_manifest(self._plan(window, []))
        self.assertEqual(40, len(written["tickerly_it"]))


class TopicGate(unittest.TestCase):
    def test_disaster_rows_drop_on_finance_and_tech(self):
        self.assertTrue(bake.drops_row({"title": "Kebakaran gudang, 11 Orang Tewas", "summary": ""}, "tickerly_id"))
        self.assertTrue(bake.drops_row({"title": "Thai Lan: Chay lon", "summary": "47 người thương vong"}, "tickerly_vi"))
        self.assertTrue(bake.drops_row({"title": "Nach Terroranschlag: Jordanien laesst Telegram sperren", "summary": ""}, "circuitly_de"))
        self.assertTrue(bake.drops_row({"title": "Putin meets tech CEOs", "summary": ""}, "circuitly_en"))

    def test_controls(self):
        # an ordinary finance story stays; a token inside a longer word is not a match; other apps are not gated
        self.assertFalse(bake.drops_row({"title": "Saham teknologi menguat di sesi pagi", "summary": ""}, "tickerly_id"))
        self.assertFalse(bake.drops_row({"title": "Trade war fears ease as tariffs pause", "summary": ""}, "tickerly_en"))
        self.assertFalse(bake.drops_row({"title": "Kebakaran gudang, 11 Orang Tewas", "summary": ""}, "kpop_en"))
        self.assertFalse(bake.contains_token("protestant churches", "protest"))


if __name__ == "__main__":
    unittest.main()
