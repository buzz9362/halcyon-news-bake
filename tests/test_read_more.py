"""r1010 N2-2 (Oct 12 2026): a publisher's read-more marker ends the teaser, and the promo call to action after it
("[Lire la suite]Si vous voulez recevoir les meilleures actus Frandroid sur WhatsApp ...") is never stored or
voiced. Rows shaped on the live circuitly_fr manifest (Oct 12; 27 of 80 carry the marker at index 143..408):
teaser, marker, start of the promo. Twin of the apps' SocialResidue.kt cutReadMorePromo.

Run from the repo root:  python -m unittest discover -s tests
Positive control: test_old_text_voiced_the_promo shows the promo is voiced when the cut is bypassed (the
pre-r1010 r1007_text shape); against the pre-r1010 bake.py (BAKE_PY=<old copy>) the cut tests fail.
"""
import os
import re
import unittest
from unittest import mock

import test_feed_quality as fq

bake = fq.bake

TEASER_1 = ("Après avoir lancé ses citadines électriques, Volkswagen s'attaque à son best-seller. "
            "La nouvelle génération arrive avec une autonomie revue et une recharge plus rapide.")
PROMO_1 = "[Lire la suite]Si vous voulez recevoir les meilleures actus Frandroid sur WhatsApp, rejoignez cette discussion."
TEASER_2 = ("Opel profite du Mondial de l'Auto de Paris pour montrer le STX Concept, un break électrique "
            "qui annonce le style des prochains modèles de la marque.")
PROMO_2 = "[Lire la suite]Utilisez-vous Google News (Actualités en France)? Vous pouvez suivre vos médias favoris."
TEASER_3 = ("Citroën dévoile au Mondial de Paris 2026 un concept de voiture électrique de 3,7 mètres, "
            "pensé pour la ville. ")
PROMO_3 = "[LIRE LA SUITE] Abonnez-vous à la newsletter Watt Else de Numerama et Survoltés!"
# kpop_pt, Oct 12: a bracketed ellipsis marks a cut in the middle of the text; it is not a footer.
ELLIPSIS = ("A torre, um dos principais cartões-postais de São Paulo, será iluminada de roxo entre os dias "
            "26 e 31 de outubro em homenagem ao […]")
ELLIPSIS_ASCII = ("O grupo anunciou nesta sexta-feira um novo projeto que reúne as oito integrantes. "
                  "A novidade foi [...]")


def _row(summary):
    return {"id": "rss_rm", "title": "Le concept électrique arrive au Mondial", "summary": summary,
            "source": "Frandroid", "articleUrl": "https://www.frandroid.com/x"}


class ReadMore(unittest.TestCase):
    def test_old_text_voiced_the_promo(self):   # positive control
        with mock.patch.object(bake, "cut_read_more_promo", lambda s: s):
            self.assertIn("WhatsApp", bake.text_for(bake.sanitize_article(_row(TEASER_1 + PROMO_1))))

    def test_the_promo_is_cut_at_the_marker(self):
        for teaser, promo in ((TEASER_1, PROMO_1), (TEASER_2, PROMO_2), (TEASER_3, PROMO_3)):
            with self.subTest(promo=promo[:30]):
                self.assertEqual(teaser.rstrip(), bake.cut_read_more_promo(teaser + promo))
                clean = bake.sanitize_article(_row(teaser + promo))
                self.assertEqual(teaser.rstrip(), clean["summary"])
                self.assertNotIn("Lire la suite", bake.text_for(clean))
                self.assertNotIn("Google News", bake.text_for(clean))

    def test_a_marker_before_index_60_is_kept(self):
        short = "Court teaser. " + PROMO_1
        self.assertLess(short.index("[Lire"), bake.READ_MORE_MIN_INDEX)
        self.assertEqual(short, bake.cut_read_more_promo(short))

    def test_other_languages_and_the_earliest_marker(self):
        t = "x" * 70
        for m in bake.READ_MORE_MARKERS:
            with self.subTest(marker=m):
                self.assertEqual(t, bake.cut_read_more_promo(t + " " + m + " Promo."))
                self.assertEqual(t, bake.cut_read_more_promo(t + " " + m.upper() + " Promo."))
        self.assertEqual(t, bake.cut_read_more_promo(t + "[Read more] one [Lire la suite] two"))

    def test_bracketed_ellipsis_rows_stay_untouched(self):   # negative control
        for s in (ELLIPSIS, ELLIPSIS_ASCII):
            self.assertEqual(s, bake.cut_read_more_promo(s))
            self.assertEqual(s, bake.sanitize_article(_row(s))["summary"])


@unittest.skipUnless(os.path.isdir(fq.APPS_ROOT), "App Market Submission is not beside this repo")
class ReadMoreParity(unittest.TestCase):
    def test_markers_match_the_apps(self):
        found = 0
        for app in fq.NEWS_APPS:
            for dp, _dn, fns in os.walk(os.path.join(fq.APPS_ROOT, f"{app}-app", "app", "src", "main")):
                if "SocialResidue.kt" not in fns:
                    continue
                with open(os.path.join(dp, "SocialResidue.kt"), encoding="utf-8") as f:
                    src = f.read()
                if "READ_MORE_MARKERS" not in src:
                    continue
                found += 1
                with self.subTest(app=app):
                    self.assertEqual(list(bake.READ_MORE_MARKERS), fq._kt_list(src, "READ_MORE_MARKERS"))
                    self.assertTrue(re.search(r"READ_MORE_MIN_INDEX = %d\b" % bake.READ_MORE_MIN_INDEX, src))
        if not found:
            self.skipTest("no app ships READ_MORE_MARKERS yet")


if __name__ == "__main__":
    unittest.main()
