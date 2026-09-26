"""Sep 26 2026 pronunciation round (P2): pins the Bollywood / Hype ID / Tinh Tu / Tickerly tables.

Run from the repo root:  python -m unittest discover -s tests
Each fixed row is pinned through bake.apply_phonetics; the old table text fails every
assertion marked "old:". The rule checks carry their own positive controls.
"""
import importlib.util
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS = os.path.join(os.path.dirname(ROOT), "App Market Submission")


def _load_bake():
    for k, v in (("R2_ACCESS_KEY_ID", "x"), ("R2_SECRET_ACCESS_KEY", "x"), ("R2_ENDPOINT_URL", "https://example.invalid")):
        os.environ.setdefault(k, v)
    spec = importlib.util.spec_from_file_location("bake", os.path.join(ROOT, "bake.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


os.chdir(ROOT)
bake = _load_bake()


def say(text, slug, path=None):
    if path and slug not in bake.PHONETICS:
        bake.PHONETICS[slug] = path
    bake._phon_cache.pop(slug, None)
    return bake.apply_phonetics(text, slug)


def rows(path):
    out = []
    with open(path, encoding="utf-8-sig") as f:
        for i, line in enumerate(f):
            s = line.strip()
            if i == 0 or not s or s.startswith("#") or "," not in s:
                continue
            k, v = s.split(",", 1)
            out.append((k.strip(), v.strip()))
    return out


def rule_breaks(spoken):
    """Rulebook: no respelling fragment of 2 chars or fewer, no Bh/Dh/Gh/Jh onset
    fragment, no single letter + hyphen. A phrase of single capitals is a letter-style
    acronym and is allowed."""
    out = []
    if re.search(r"(?:^|\s)[A-Za-z]-[A-Za-z]", spoken):
        out.append("single letter + hyphen")
    frags = [f.strip(",.'\"") for f in re.split(r"[\s\-]+", spoken) if f.strip(",.'\"")]
    if not all(len(f) == 1 and f.isupper() for f in frags):
        ok = {"a", "i", "of", "to", "in", "on", "my", "yo", "go", "by", "oh", "ah", "be", "we", "no", "so", "do",
              # rulebook letter names (ADOR = "Ay Door", MV = "Em Vi") and the English name Jo
              "ay", "ee", "em", "en", "el", "ex", "jo"}
        out += [f"fragment {f}" for f in frags if len(f) <= 2 and f.isalpha() and not f.isupper() and f.lower() not in ok]
    out += [f"digraph {f}" for f in frags if re.fullmatch(r"(Bh|Dh|Gh|Jh)[a-z]{0,2}", f)]
    return out


class BollywoodEnglish(unittest.TestCase):
    def test_digraph_rows_reached_the_baker(self):
        # old baker table: "Varun Dhawan,Varun Dhawan", "Bhumi,Bhumi", "Bhai,Bhai" (never got the Jun 14 fix)
        self.assertEqual(say("Varun Dhawan", "bollywood"), "Vah Roon Dah Waan")
        self.assertEqual(say("Bhumi Pednekar", "bollywood"), "Boo Mee Ped Nay Kar")
        self.assertEqual(say("Shreya Ghoshal", "bollywood"), "Shray Yaa Go Shaal")

    def test_corrupted_rows_are_gone(self):
        # old: "ShankarMa haadevan", "La taMangeshkar", "Kar waChowth"
        self.assertEqual(say("Shankar Mahadevan", "bollywood"), "Shankar Mahaa Dayvan")
        self.assertEqual(say("Lata Mangeshkar", "bollywood"), "Lataa Mangeshkar")
        self.assertEqual(say("Karwa Chauth", "bollywood"), "Kar Waa Chowth")

    def test_yash_raj_films_and_tseries(self):
        self.assertEqual(say("Yash Raj Films", "bollywood"), "Yash Raj Films")   # old: Yush Raj Films
        self.assertEqual(say("T-Series", "bollywood"), "Tee Series")            # old: T-Series (T minus)
        self.assertEqual(say("The Vvaan", "bollywood"), "The Vaan")
        self.assertEqual(say("Yami Gautam Dhar", "bollywood"), "Yami Gautam Dar")
        self.assertEqual(say("Ab Tak Chhappan", "bollywood"), "Ab Tak Chhappan")   # old: AB Tak (P3 finding)
        self.assertEqual(say("Vishal Bhardwaj", "bollywood"), "Vishaal Bard Waaj")  # old: Vishaal Bhardwaaj

    def test_no_row_breaks_the_fragment_rules(self):
        bad = [(k, say(k, "bollywood")) for k, _ in bake.load_phonetics("bollywood")
               if rule_breaks(say(k, "bollywood"))]
        self.assertEqual(bad, [])

    def test_rule_checker_positive_control(self):
        self.assertTrue(rule_breaks("La taMangeshkar"))       # the old corrupted row
        self.assertTrue(rule_breaks("A-jay De-vgun"))
        self.assertTrue(rule_breaks("D ha van"))
        self.assertFalse(rule_breaks("Y R F"))
        self.assertFalse(rule_breaks("Vah Roon Dah Waan"))


class BollywoodHindi(unittest.TestCase):
    def test_latin_film_titles_are_transliterated(self):
        self.assertEqual(say("Bigg Boss 20 और Dhamaal 4", "bollywood_hi"), "बिग बॉस 20 और धमाल 4")
        self.assertEqual(say("The Vvaan", "bollywood_hi"), "The वन")


class HypeIndonesian(unittest.TestCase):
    def test_mc_letter_names(self):
        self.assertEqual(say("MC acara", "hype_id"), "Em Si acara")   # old: Em Se (Jul 24 fix never ported)


class TinhVietnamese(unittest.TestCase):
    def test_letter_names_and_titles(self):
        self.assertEqual(say("HD", "tinh_vi"), "Hát Đê")             # old: Ếch Đi ("frog")
        self.assertEqual(say("OST", "tinh_vi"), "Ô Ét Tê")           # old: Ô Eo Tê
        self.assertEqual(say("NSND Thanh Ngoan", "tinh_vi"), "Nghệ sĩ Nhân dân Thanh Ngoan")
        self.assertEqual(say("NSƯT Việt Anh", "tinh_vi"), "Nghệ sĩ Ưu tú Việt Anh")
        self.assertEqual(say("HIEUTHUHAI", "tinh_vi"), "Hiếu Thứ Hai")  # old: Hi Yu Thư Hai


class Tickerly(unittest.TestCase):
    def test_tables_exist_and_apply(self):
        p = "phonetics/tickerly_en.csv"
        self.assertEqual(say("PYMNTS", "tickerly_en", p), "Payments")
        self.assertEqual(say("up 25 bps", "tickerly_en", p), "up 25 basis points")
        self.assertEqual(say("GDP naik", "tickerly_id", "phonetics/tickerly_id.csv"), "Ji Di Pi naik")
        self.assertEqual(say("GDP tăng", "tickerly_vi", "phonetics/tickerly_vi.csv"), "Gờ Đê Pê tăng")


@unittest.skipUnless(os.path.isdir(APPS), "app repo not beside the baker")
class MirrorsTheAppTables(unittest.TestCase):
    """The baker table is a copy of the app's device table (SSOT = the app asset)."""
    PAIRS = {
        "phonetics/bollywood_en.csv": "bollywood-today-app/app/src/main/assets/phonetics_en.csv",
        "phonetics/bollywood_hi.csv": "bollywood-today-app/app/src/main/assets/phonetics_hi.csv",
        "phonetics/hype_id.csv": "hype-id-app/app/src/main/assets/phonetics_id.csv",
        "phonetics/tinh_vi.csv": "tinh-tu-app/app/src/main/assets/phonetics_vi.csv",
        "phonetics/tickerly_en.csv": "tickerly-app/app/src/main/assets/phonetics_en.csv",
        "phonetics/tickerly_id.csv": "tickerly-app/app/src/main/assets/phonetics_id.csv",
        "phonetics/tickerly_vi.csv": "tickerly-app/app/src/main/assets/phonetics_vi.csv",
    }

    def test_rows_match(self):
        for baker, app in self.PAIRS.items():
            self.assertEqual(rows(os.path.join(ROOT, baker)), rows(os.path.join(APPS, app)), baker)


if __name__ == "__main__":
    unittest.main()
