"""r1019 D-5 (device, kpop-today Koreaboo story): a bare image URL at the end of a summary was shown and
spoken ("... https://storage.googleapis.com/koreaboo-cdn/2026/10/Choa-1."). strip_social_residue drops a bare
http/https token (with its trailing punctuation), parity with the apps' SocialResidue.kt BARE_URL_REGEX.

Run from the repo root:  python -m unittest discover -s tests
Positive control: against the pre-r1019 bake.py (BAKE_PY=<old copy>) test_bare_url_is_dropped fails.
"""
import unittest

import test_throttle as tt

bake = tt.bake

KOREABOO = "Fans could not recognize her at the event. https://storage.googleapis.com/koreaboo-cdn/2026/10/Choa-1."


class BareUrl(unittest.TestCase):
    def test_bare_url_is_dropped(self):
        self.assertEqual("Fans could not recognize her at the event.", bake.strip_social_residue(KOREABOO))
        self.assertEqual("Full gallery here and more", bake.strip_social_residue("Full gallery here HTTP://example.com/a?b=1 and more"))

    def test_text_without_a_scheme_stays(self):
        self.assertEqual("Visit example.com today", bake.strip_social_residue("Visit example.com today"))
        self.assertEqual("Plain text stays", bake.strip_social_residue("Plain text stays"))

    def test_voiced_text_has_no_url(self):
        art = {"id": "rss_u1", "title": "Idol becomes unrecognizable", "summary": KOREABOO, "source": "Koreaboo"}
        self.assertNotIn("https://", bake.text_for(art, "kpop_en"))


if __name__ == "__main__":
    unittest.main()
