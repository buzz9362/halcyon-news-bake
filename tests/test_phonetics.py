"""Sep 26 2026 pronunciation round (P1): pins apply_phonetics and the K-pop / anime / tropic tables.

Run from the repo root:  python -m unittest discover -s tests
Each fix has a positive control that shows the old behaviour or data is caught.
"""
import atexit
import csv
import importlib.util
import os
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_bake():
    for k, v in (("R2_ACCESS_KEY_ID", "x"), ("R2_SECRET_ACCESS_KEY", "x"), ("R2_ENDPOINT_URL", "https://example.invalid")):
        os.environ.setdefault(k, v)
    spec = importlib.util.spec_from_file_location("bake", os.path.join(ROOT, "bake.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


os.chdir(ROOT)
bake = _load_bake()


def table(slug):
    with open(os.path.join(ROOT, bake.PHONETICS[slug]), encoding="utf-8-sig") as f:
        rows = [r for r in csv.reader(f)][1:]
    return [(r[0].strip(), ",".join(r[1:]).strip()) for r in rows if r and r[0].strip() and not r[0].startswith("#")]


def with_temp_table(rows, normalize):
    """Register a throwaway slug with the given rows; returns the slug."""
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("Name,Phonetic\n" + "".join(f"{k},{v}\n" for k, v in rows))
    atexit.register(os.remove, path)
    slug = f"_t{abs(hash((tuple(rows), normalize)))}"
    bake.PHONETICS[slug] = path
    if normalize:
        bake.SPEECH_NORMALIZE.add(slug)
    return slug


# Common English first names and native English words that must never be respelled.
ENGLISH_NAMES = {"Tiffany", "Jennie", "Lisa", "Joshua", "Jake", "Wendy", "Irene", "Sunny", "Karina",
                 "Mark", "Winter", "Rain", "Crush", "Dean", "Bias", "Victoria", "Amber", "Nicole"}


def english_name_rows(rows):
    return [(k, v) for k, v in rows if k in ENGLISH_NAMES and v.replace(" ", "").lower() != k.lower()]


def syllabified_english(rows):
    bad = ("Dou ble", "Sev en", "Twen ty", "Vel vet", "Su per", "Won der", "Jel ly", "Mys tic", "Tri ple", "Fly ing")
    return [(k, v) for k, v in rows if any(b in v for b in bad)]


class TiffanyAndEnglishNames(unittest.TestCase):
    def test_tiffany_is_read_as_the_english_name(self):
        out = bake.apply_phonetics("Koreaboo, Byun Yo Han Opens Up About Being Girls’ Generation Tiffany’s Husband .", "kpop_en")
        self.assertIn("Tiffany", out)
        self.assertNotIn("Tih", out)

    def test_control_the_old_row_respelled_tiffany(self):
        slug = with_temp_table([("Tiffany", "Tih fa nee")], normalize=True)
        self.assertIn("Tih fa nee", bake.apply_phonetics("Girls' Generation Tiffany", slug))

    def test_no_english_name_or_word_is_respelled_in_the_k_tables(self):
        for slug in ("kpop_en", "tropic_en"):
            self.assertEqual([], english_name_rows(table(slug)), slug)
            self.assertEqual([], syllabified_english(table(slug)), slug)

    def test_control_checkers_flag_the_old_rows(self):
        old = [("Tiffany", "Tih fa nee"), ("Lisa", "Lee sa"), ("Bias", "Bye-us"), ("GOT7", "Got Sev en"),
               ("RBW", "Ar Bee Dou ble You")]
        self.assertEqual(3, len(english_name_rows(old)))
        self.assertEqual(2, len(syllabified_english(old)))


class CurlyApostrophe(unittest.TestCase):
    def test_curly_apostrophe_matches_a_straight_key(self):
        slug = with_temp_table([("Girls' Generation", "GG_HIT")], normalize=True)
        self.assertEqual("GG_HIT Tiffany", bake.apply_phonetics("Girls’ Generation Tiffany", slug))

    def test_control_without_the_fold_the_curly_form_never_matched(self):
        slug = with_temp_table([("Girls' Generation", "GG_HIT")], normalize=False)
        self.assertEqual("Girls’ Generation Tiffany", bake.apply_phonetics("Girls’ Generation Tiffany", slug))


class AllCapsWords(unittest.TestCase):
    def test_stray_caps_words_become_words(self):
        self.assertEqual("Exclusive: Jennie Returns, Sekiro Anime", bake.normalize_caps("EXCLUSIVE: JENNIE Returns, SEKIRO Anime"))
        self.assertEqual("aespa Synk Rosé", bake.normalize_caps("aespa SYNK ROSÉ"))
        self.assertEqual("Allday Project's Annie, BTS'S, Tuide's", bake.normalize_caps("ALLDAY PROJECT'S ANNIE, BTS'S, TUIDE's"))

    def test_letter_style_acronyms_keep_their_caps(self):
        for t in ("BTS", "NCT", "TXT", "SNSD", "WJSN", "TVXQ", "JTBC", "BTOB", "ADHD", "CSAT", "RIAJ", "NCT127", "2NE1"):
            self.assertEqual(t, bake.normalize_caps(t), t)

    def test_caps_key_still_gets_its_respelling(self):
        out = bake.apply_phonetics("BLACKPINK and AKMU with BTS", "kpop_en")
        self.assertEqual("Black Pink and Ack Moo with Bee Tee Ess", out)

    def test_control_old_path_left_caps_untouched(self):
        slug = with_temp_table([("Zzqq", "unused")], normalize=False)
        self.assertEqual("EXCLUSIVE: JENNIE", bake.apply_phonetics("EXCLUSIVE: JENNIE", slug))

    def test_every_manifest_table_is_opted_in(self):
        # Derived from MANIFESTS (the SSOT), so a new manifest cannot silently skip the pass.
        missing = sorted({m["phonetics"] for m in bake.MANIFESTS} - bake.SPEECH_NORMALIZE)
        self.assertEqual([], missing)

    def test_control_the_opt_in_check_catches_a_missing_manifest(self):
        before = set(bake.SPEECH_NORMALIZE)
        try:
            bake.SPEECH_NORMALIZE.discard("tickerly_it")
            self.assertEqual(["tickerly_it"], sorted({m["phonetics"] for m in bake.MANIFESTS} - bake.SPEECH_NORMALIZE))
        finally:
            bake.SPEECH_NORMALIZE.clear(); bake.SPEECH_NORMALIZE.update(before)

    def test_bracketed_gloss_and_possessive(self):
        self.assertEqual("Elnusa (ELSA) dan Nvidia's Exclusive", bake.apply_phonetics("Elnusa (ELSA) dan NVIDIA's EXCLUSIVE", "tickerly_id"))

    def test_p2_bollywood_non_word_edge_key(self):
        self.assertEqual("Scoop: rupees 60 crore", bake.apply_phonetics("SCOOP: Rs. 60 crore", "bollywood"))


def old_normalize_caps(text):
    """The first Sep 26 version (>= 4 letters only), kept here as the positive control."""
    out, i, n = [], 0, len(text)
    while i < n:
        if not text[i].isalpha():
            out.append(text[i]); i += 1; continue
        j = i
        while j < n and (text[j].isalpha() or text[j].isdigit() or (text[j] == "'" and j + 1 < n and text[j + 1].isalpha())):
            j += 1
        tok = text[i:j]; word = tok.split("'")[0]
        if len(word) >= 4 and word.isalpha() and word.isupper() and word.upper() not in bake.LETTER_ACRONYMS and bake._has_vowel(word):
            tok = tok[0] + tok[1:].lower()
        out.append(tok); i = j
    return "".join(out)


class ShortWordsAndShouting(unittest.TestCase):
    """Coordinator review: short capital words (THE, OF, LA, DAN) and shouting headlines."""
    # Real headlines from the Sep 26 manifests (kpop_en, kpop_en, tropic_id).
    SHOUT_EN = "THE ARCHITECTURE OF EASE: HOW ALLDAY PROJECT'S ANNIE IS REDEFINING GLOBAL POP CULTURE"
    SLASH_EN = "Number_i Release EP, REBON / BUGS LIFE / DIGITAL GIRL"
    SHOUT_ID = "ALLDAY PROJECT Rilis Video Musik 'DO IT LIKE THIS'"

    def test_real_shouting_headlines(self):
        self.assertEqual("The Architecture Of Ease: How Allday Project's Annie Is Redefining Global Pop Culture",
                         bake.normalize_caps(self.SHOUT_EN, "en"))
        self.assertEqual("Number_i Release EP, Rebon / Bugs Life / Digital Girl", bake.normalize_caps(self.SLASH_EN, "en"))
        self.assertEqual("Allday Project Rilis Video Musik 'Do It Like This'", bake.normalize_caps(self.SHOUT_ID, "id"))

    def test_control_the_old_function_left_short_words_in_capitals(self):
        old = old_normalize_caps(self.SHOUT_EN)
        for w in ("THE", "OF", "HOW", "IS", "POP"):
            self.assertIn(w, old.split())
        self.assertIn("'DO IT", old_normalize_caps(self.SHOUT_ID))

    def test_short_words_per_language_outside_a_shouting_headline(self):
        self.assertEqual("The Boyz and NCT on the Top chart, AI and US news",
                         bake.normalize_caps("THE BOYZ and NCT on the TOP chart, AI and US news", "en"))
        self.assertEqual("Un concierto de la ONU y la UE", bake.normalize_caps("UN concierto de la ONU y la UE", "es"))
        self.assertEqual("Konser BTS Dan TXT", bake.normalize_caps("Konser BTS DAN TXT", "id"))

    def test_acronyms_survive_shouting_and_who_is_ambiguous(self):
        self.assertEqual("WHO warns BTS fans", bake.normalize_caps("WHO warns BTS fans", "en"))
        self.assertEqual("Who Says BTS Is Back", bake.normalize_caps("WHO SAYS BTS IS BACK", "en"))
        self.assertEqual("La Nueva Era De BTS", bake.normalize_caps("LA NUEVA ERA DE BTS", "es"))
        self.assertEqual("Twice e BTS No Brasil: O Que Saber", bake.normalize_caps("TWICE e BTS NO BRASIL: O QUE SABER", "pt"))
        self.assertEqual("Nóng: Công Bố Mới Của BTS", bake.normalize_caps("NÓNG: CÔNG BỐ MỚI CỦA BTS", "vi"))
        for t in ("CEO", "USA", "UFC", "OMG", "OST", "NCT", "TXT"):
            self.assertEqual(f"Big {t} News Today", bake.normalize_caps(f"BIG {t} NEWS TODAY", "en"))

    def test_apply_phonetics_uses_the_manifest_language(self):
        self.assertEqual("es", bake._slug_lang("kpop_es"))
        self.assertEqual("en", bake._slug_lang("bollywood"))
        self.assertEqual("Be Te Ese: La Gira", bake.apply_phonetics("BTS: LA GIRA", "kpop_es"))


class NonWordKeyEdges(unittest.TestCase):
    def test_keys_starting_or_ending_with_punctuation_now_fire(self):
        self.assertEqual("Jee Eye Dul and And Team", bake.apply_phonetics("(G)I-DLE and &TEAM", "kpop_en"))

    def test_control_word_boundary_never_matched_them(self):
        slug = with_temp_table([("(G)I-DLE", "Jee Eye Dul"), ("&TEAM", "And Team")], normalize=False)
        self.assertEqual("(G)I-DLE and &TEAM", bake.apply_phonetics("(G)I-DLE and &TEAM", slug))

    def test_fm_parity_rows(self):
        self.assertEqual("Eh pik High and Eye Dul", bake.apply_phonetics("Epik High and i-dle", "kpop_en"))
        self.assertEqual("rock n roll, l and v", bake.apply_phonetics("rock n roll, l and v", "kpop_en"))

    def test_word_edges_still_need_a_boundary(self):
        # "San" (ATEEZ) must not fire inside "Sandara"; "Jin" not inside "Jinwoo".
        self.assertEqual("Sandara", bake.apply_phonetics("Sandara", "kpop_en"))
        self.assertIn("Jinwoo", bake.apply_phonetics("Jinwoo", "kpop_en"))


class ForceAppTableKey(unittest.TestCase):
    def test_every_apps_row_names_a_real_table(self):
        self.assertEqual([], [a["slug"] for a in bake.APPS if a.get("phonetics") not in bake.PHONETICS])

    def test_control_the_slug_itself_is_not_a_table(self):
        self.assertEqual(["anime", "hype", "kpop", "tinh", "tropic"], sorted(a["slug"] for a in bake.APPS if a["slug"] not in bake.PHONETICS))


class JapaneseAndOtherLanguages(unittest.TestCase):
    def test_anime_table_is_loaded(self):
        self.assertEqual("Aoki Den-shoh Welsh", bake.apply_phonetics("Aoki Denshou Welsh", "anime_en"))
        self.assertEqual("Moo-shoh-koo Ten-say Season 3", bake.apply_phonetics("Mushoku Tensei Season 3", "anime_en"))
        self.assertEqual("Masami Oh-bah-ree", bake.apply_phonetics("Masami Ōbari", "anime_en"))
        self.assertEqual("Sekiro: No Defeat", bake.apply_phonetics("SEKIRO: NO DEFEAT", "anime_en"))  # "NO" is an en short word

    def test_control_anime_had_no_table(self):
        slug = with_temp_table([("Zzqq", "unused")], normalize=False)
        self.assertEqual("Aoki Denshou Welsh", bake.apply_phonetics("Aoki Denshou Welsh", slug))

    def test_anime_table_keeps_english_words_whole(self):
        keys = {k.lower() for k, _ in table("anime_en")}
        for w in ("madhouse", "cowboy bebop", "made in abyss", "simulcast", "fullmetal alchemist", "ann", "wit"):
            self.assertNotIn(w, keys)

    def test_es_pt_curated_rows_unchanged(self):
        self.assertEqual("Be Te Ese y Yeni", bake.apply_phonetics("BTS y Jennie", "kpop_es"))
        self.assertEqual("Bê Tê Esse", bake.apply_phonetics("BTS", "kpop_pt"))

    def test_vi_and_id_sibling_fixes(self):
        self.assertEqual("Hát Đê", bake.apply_phonetics("HD", "tropic_vi"))
        self.assertEqual("Ô Ét Tê", bake.apply_phonetics("OST", "tropic_vi"))
        self.assertEqual("Em Si", bake.apply_phonetics("MC", "tropic_id"))
        self.assertEqual("Ai-lit", bake.apply_phonetics("ILLIT", "tropic_id"))


class TargetedRevoice(unittest.TestCase):
    """r7: only listed ids (or MP3s baked after the list was made) are re-voiced."""

    def run_pass(self, listed, mods, r6_apps):
        from unittest import mock
        items = [{"id": i, "title": f"Title {i} with enough words to pass the minimum length check",
                  "summary": "Summary text long enough.", "source": "Soompi", "publishedAtMs": 1} for i in mods]
        resp = mock.Mock(); resp.json.return_value = {"items": items}; resp.raise_for_status.return_value = None
        voiced = []
        tgt = {"generated_ms": 500, "manifests": {"kpop_en": listed}}
        key_of = {bake.article_key(i): i for i in mods}
        with mock.patch.object(bake.requests, "get", return_value=resp),              mock.patch.object(bake, "r2_exists", return_value=True),              mock.patch.object(bake, "r2_modified_ms", side_effect=lambda k: mods[key_of[k]]),              mock.patch.object(bake, "upload", side_effect=lambda k, d: voiced.append(key_of[k])),              mock.patch.object(bake, "synth_to_mp3", return_value=b"mp3"),              mock.patch.object(bake, "write_manifest"),              mock.patch.object(bake.s3, "get_object", side_effect=Exception("no prev")),              mock.patch.object(bake, "retext_targeted", return_value=tgt),              mock.patch.object(bake, "RETEXT_APPS", r6_apps),              mock.patch.object(bake, "retext_cutover_ms", side_effect=lambda tag=bake.RETEXT_TAG: 1000):
            bake.bake_manifest({"manifest": "kpop_en", "feed_url": "x", "lang": "en", "tld": "us", "phonetics": "kpop_en"})
        return sorted(voiced)

    def test_only_listed_or_late_baked_ids_are_revoiced(self):
        # a: listed + old -> redo; b: unlisted, baked before the list -> keep;
        # c: unlisted, baked after the list but before the cutover -> redo; d: listed but already new -> keep.
        mods = {"a": 100, "b": 200, "c": 700, "d": 1500, "e": 300, "f": 400}
        self.assertEqual(["a", "c"], self.run_pass(["a", "d"], mods, set()))

    def test_a_manifest_whose_fresh_stories_all_fail_is_reported_starved(self):
        from unittest import mock
        items = [{"id": f"n{k}", "title": "A fresh story title with enough words for the length check",
                  "summary": "Summary.", "source": "Soompi", "publishedAtMs": 1} for k in range(6)]
        resp = mock.Mock(); resp.json.return_value = {"items": items}; resp.raise_for_status.return_value = None
        bake._STARVED.clear()
        with mock.patch.object(bake.requests, "get", return_value=resp),              mock.patch.object(bake, "r2_exists", return_value=False),              mock.patch.object(bake, "synth_to_mp3", side_effect=Exception("429 Too Many Requests")),              mock.patch.object(bake, "write_manifest"),              mock.patch.object(bake.s3, "get_object", side_effect=Exception("no prev")),              mock.patch.object(bake, "retext_targeted", return_value={}),              mock.patch.object(bake, "RETEXT_APPS", set()):
            bake.bake_manifest({"manifest": "kpop_en", "feed_url": "x", "lang": "en", "tld": "us", "phonetics": "kpop_en"})
        self.assertEqual([("kpop_en", 6)], bake._STARVED)
        bake._STARVED.clear()

    def test_control_the_r6_whole_window_mode_redoes_every_old_item(self):
        mods = {"a": 100, "b": 200, "c": 700, "d": 1500, "e": 300}
        self.assertEqual(["a", "b", "c", "e"], self.run_pass([], mods, {"kpop"}))


if __name__ == "__main__":
    unittest.main()
