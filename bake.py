"""
halcyon-news-bake — pre-bake MP3s for the 6 Halcyon Audio news apps so the
Android Automotive OS flavors play real audio URLs through ExoPlayer (no
system TTS dependency, no MainActivity wake-up, no audio-focus shims).

Uses gTTS (Google Translate TTS, free, no auth; it does answer 429 to a busy
datacenter IP, see ThrottleBreaker) — we
switched from edge-tts because Microsoft blocks the Edge synthesis endpoint
from GitHub Actions / cloud datacenter IPs (403 WSServerHandshakeError).

Architecture:
  1. For each app, fetch its Cloudflare Worker feed across all categories.
  2. For each article, compute a stable MP3 key = sha256(article.id)[:32] + ".mp3".
  3. If the key already exists in R2, skip. Otherwise, synthesize with gTTS
     in the app's primary language and upload to R2 with a long Cache-Control.
  4. Public URL pattern: https://pub-<r2-hash>.r2.dev/<key>
     The app predicts the same URL deterministically and hands it to ExoPlayer.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import sys
import time
import traceback
import unicodedata
from io import BytesIO
from typing import Any

import boto3
import requests
from botocore.exceptions import ClientError
from gtts import gTTS

# ---------- Configuration --------------------------------------------------

R2_ACCESS_KEY = os.environ["R2_ACCESS_KEY_ID"]
R2_SECRET_KEY = os.environ["R2_SECRET_ACCESS_KEY"]
R2_ENDPOINT = os.environ["R2_ENDPOINT_URL"]
R2_BUCKET = os.environ.get("R2_BUCKET", "halcyon-news-tts")

# Per-app primary gTTS language code. Bake server speaks the article
# title + summary in this language. The phone in-app path keeps using real-time
# system TTS for language switches; AAOS uses these pre-baked MP3s only.
APPS: list[dict[str, Any]] = [
    {
        "slug": "kpop",
        "phonetics": "kpop_en",
        "feed_url": "https://kpop-today.soundica.app/feed",
        "lang": "en",
        "tld": "us",
        "categories": ["latest", "trending", "charts"],
    },
    # bollywood is now driven by the MANIFESTS passes below (manifest = source of
    # truth for the appning app), so it is intentionally NOT in the broad APPS loop.
    {
        "slug": "anime",
        "phonetics": "anime_en",
        "feed_url": "https://anime-brief.soundica.app/feed",
        "lang": "en",
        "tld": "us",
        "categories": ["latest", "trending", "charts"],
    },
    {
        "slug": "tropic",
        "phonetics": "tropic_en",
        "feed_url": "https://kpop-tropic.soundica.app/feed",
        "lang": "en",
        "tld": "us",
        "categories": ["latest", "trending", "charts"],
    },
    {
        "slug": "hype",
        "phonetics": "hype_id",
        "feed_url": "https://hype-id.soundica.app/feed",
        "lang": "id",
        "tld": "co.id",
        "categories": ["latest", "trending", "charts"],
    },
    {
        "slug": "tinh",
        "phonetics": "tinh_vi",
        "feed_url": "https://tinh-tu.soundica.app/feed",
        "lang": "vi",
        "tld": "com.vn",
        "categories": ["latest", "trending", "charts"],
    },
]

# Manifest passes (Jun 9 2026): the appning app reads these R2 JSON manifests
# DIRECTLY (NOT the live worker feed), so it is immune to Cloudflare per-colo feed
# divergence (baker colo != car colo saw different rotating windows -> 404). Each
# bake_manifest() fetches the EXACT url the appning app fetches, bakes any missing
# MP3, and writes a manifest listing ONLY ids whose MP3 is CONFIRMED present in R2 —
# so the car can never request an un-baked id -> no "Source error". URLs mirror the
# appning NewsApi.fetchFromBackend reads: /feed (en) and /feed?lang=hi (hi).
MANIFESTS: list[dict[str, Any]] = [
    {"manifest": "bollywood_en", "feed_url": "https://bollywood-today.soundica.app/feed",
     "lang": "en", "tld": "us", "phonetics": "bollywood"},
    {"manifest": "bollywood_hi", "feed_url": "https://bollywood-today.soundica.app/feed?lang=hi",
     "lang": "hi", "tld": "co.in", "phonetics": "bollywood_hi"},
    # Jun 9 2026 — 5 sibling apps ported to the same appning manifest architecture.
    {"manifest": "kpop_en",   "feed_url": "https://kpop-today.soundica.app/feed",          "lang": "en", "tld": "us",     "phonetics": "kpop_en"},
    {"manifest": "kpop_es",   "feed_url": "https://kpop-today.soundica.app/feed?lang=es",  "lang": "es", "tld": "es",     "phonetics": "kpop_es"},
    {"manifest": "kpop_pt",   "feed_url": "https://kpop-today.soundica.app/feed?lang=pt",  "lang": "pt", "tld": "com.br", "phonetics": "kpop_pt"},
    {"manifest": "anime_en",  "feed_url": "https://anime-brief.soundica.app/feed",         "lang": "en", "tld": "us",     "phonetics": "anime_en"},
    {"manifest": "tropic_en", "feed_url": "https://kpop-tropic.soundica.app/feed",         "lang": "en", "tld": "us",     "phonetics": "tropic_en"},
    {"manifest": "tropic_id", "feed_url": "https://kpop-tropic.soundica.app/feed?lang=id", "lang": "id", "tld": "co.id",  "phonetics": "tropic_id"},
    {"manifest": "tropic_vi", "feed_url": "https://kpop-tropic.soundica.app/feed?lang=vi", "lang": "vi", "tld": "com.vn", "phonetics": "tropic_vi"},
    {"manifest": "hype_id",   "feed_url": "https://hype-id.soundica.app/feed",             "lang": "id", "tld": "co.id",  "phonetics": "hype_id"},
    {"manifest": "tinh_vi",   "feed_url": "https://tinh-tu.soundica.app/feed",             "lang": "vi", "tld": "com.vn", "phonetics": "tinh_vi"},
    # Circuitly (tech news) — appning baked-MP3. App fetches circuitly_<lang>.json. Worker
    # serves en/es/pt/vi/de/fr/it (ko/ja in the worker are unused — the app dropped them).
    # No phonetics CSV yet (tech terms read fine in gTTS; the unknown key is a no-op like anime_en).
    {"manifest": "circuitly_en", "feed_url": "https://circuitly.soundica.app/feed",          "lang": "en", "tld": "us",     "phonetics": "circuitly_en"},
    {"manifest": "circuitly_es", "feed_url": "https://circuitly.soundica.app/feed?lang=es",  "lang": "es", "tld": "es",     "phonetics": "circuitly_es"},
    {"manifest": "circuitly_pt", "feed_url": "https://circuitly.soundica.app/feed?lang=pt",  "lang": "pt", "tld": "com.br", "phonetics": "circuitly_pt"},
    {"manifest": "circuitly_vi", "feed_url": "https://circuitly.soundica.app/feed?lang=vi",  "lang": "vi", "tld": "com.vn", "phonetics": "circuitly_vi"},
    {"manifest": "circuitly_de", "feed_url": "https://circuitly.soundica.app/feed?lang=de",  "lang": "de", "tld": "de",     "phonetics": "circuitly_de"},
    {"manifest": "circuitly_fr", "feed_url": "https://circuitly.soundica.app/feed?lang=fr",  "lang": "fr", "tld": "fr",     "phonetics": "circuitly_fr"},
    {"manifest": "circuitly_it", "feed_url": "https://circuitly.soundica.app/feed?lang=it",  "lang": "it", "tld": "it",     "phonetics": "circuitly_it"},
    # Tickerly (finance news) — appning baked-MP3. Worker serves en/es/pt/vi/id/de/fr/it/hi,
    # matching the app's full 9-language AppLanguage enum. (hi was skipped until Jul 10 2026
    # because the worker had no Hindi finance sources; it now has 6 — Money9live/Amar
    # Ujala/Prabhat Khabar — and ?lang=hi serves a healthy 60-item window.)
    {"manifest": "tickerly_en", "feed_url": "https://tickerly.soundica.app/feed",          "lang": "en", "tld": "us",     "phonetics": "tickerly_en"},
    {"manifest": "tickerly_es", "feed_url": "https://tickerly.soundica.app/feed?lang=es",  "lang": "es", "tld": "es",     "phonetics": "tickerly_es"},
    {"manifest": "tickerly_pt", "feed_url": "https://tickerly.soundica.app/feed?lang=pt",  "lang": "pt", "tld": "com.br", "phonetics": "tickerly_pt"},
    {"manifest": "tickerly_vi", "feed_url": "https://tickerly.soundica.app/feed?lang=vi",  "lang": "vi", "tld": "com.vn", "phonetics": "tickerly_vi"},
    {"manifest": "tickerly_id", "feed_url": "https://tickerly.soundica.app/feed?lang=id",  "lang": "id", "tld": "co.id",  "phonetics": "tickerly_id"},
    {"manifest": "tickerly_de", "feed_url": "https://tickerly.soundica.app/feed?lang=de",  "lang": "de", "tld": "de",     "phonetics": "tickerly_de"},
    {"manifest": "tickerly_fr", "feed_url": "https://tickerly.soundica.app/feed?lang=fr",  "lang": "fr", "tld": "fr",     "phonetics": "tickerly_fr"},
    {"manifest": "tickerly_it", "feed_url": "https://tickerly.soundica.app/feed?lang=it",  "lang": "it", "tld": "it",     "phonetics": "tickerly_it"},
    {"manifest": "tickerly_hi", "feed_url": "https://tickerly.soundica.app/feed?lang=hi",  "lang": "hi", "tld": "co.in",  "phonetics": "tickerly_hi"},
]

MAX_TEXT_LEN = 4000      # Edge-TTS handles ~8k cleanly, cap at 4k for AAOS cadence
FAIR_USE_SNIPPET = 350   # match the app's Article.kt snippet(maxChars=350) for
                         # ALL_RIGHTS_RESERVED sources — the baked audio must not
                         # reproduce more of a publisher's text than the app shows.
MIN_TEXT_LEN = 20        # below this, the article is just a stub — skip
FEED_TIMEOUT_S = 30
MAX_NEW_BAKES_PER_APP = 30   # cap so one app can't exhaust the GHA timeout
MAX_NEW_HINDI_BAKES = 80     # Hindi gets a higher cap: the Amar Ujala feed rotates its
                             # ~60-item window every cycle, so a low cap left most of the
                             # live ids un-baked -> the app 404'd ("Source error").
# Jul 11 2026 — manifest carry-forward (fixes tickerly car thinness, QAB-audit finding):
# fast-rotating feeds (finance) rotate their 60-item window faster than gTTS rate
# limits let one run bake, so a window-only manifest stalled at the ~10 newest
# confirmed ids forever (tickerly vi/de/fr/it/hi sat at 8-12 items while the live
# feed had 60). Previously-manifested items are carried forward — their MP3s are in
# R2 by construction (a manifest never lists an un-baked id and MP3s are never
# deleted) — until they age out or the cap trims them.
CARRY_MAX_AGE_MS = 72 * 3600 * 1000  # carried items older than 72h drop off
MAX_MANIFEST_ITEMS = 80              # newest-first cap on the merged manifest

# Jun 9 2026 — per-app pronunciation tables (copied from each app's
# assets/phonetics_en.csv). gTTS ignores the in-app CSV, so apply the same
# respellings here before synthesis. Tuned for Google TTS English.
import re as _re
PHONETICS = {
    "bollywood": "phonetics/bollywood_en.csv",
    "bollywood_hi": "phonetics/bollywood_hi.csv",
    "kpop_en": "phonetics/kpop_en.csv",
    "kpop_es": "phonetics/kpop_es.csv",
    "kpop_pt": "phonetics/kpop_pt.csv",
    "tropic_en": "phonetics/tropic_en.csv",
    "tropic_id": "phonetics/tropic_id.csv",
    "tropic_vi": "phonetics/tropic_vi.csv",
    "hype_id": "phonetics/hype_id.csv",
    "tinh_vi": "phonetics/tinh_vi.csv",
    # Sep 26 2026: anime_en now has a table (the Anime Brief app's own respellings plus
    # the Japanese names with ou/ei/uu or macron vowels that English TTS misreads).
    "anime_en": "phonetics/anime_en.csv",
    "tickerly_en": "phonetics/tickerly_en.csv",
    "tickerly_id": "phonetics/tickerly_id.csv",
    "tickerly_vi": "phonetics/tickerly_vi.csv",
}
# Every manifest whose table file exists is mapped (P2 added audited header-only tables for
# the 13 circuitly/tickerly manifests), so no manifest is voiced without its table.
for _m in MANIFESTS:
    _rel = f"phonetics/{_m['phonetics']}.csv"
    if _m["phonetics"] not in PHONETICS and os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), _rel)):
        PHONETICS[_m["phonetics"]] = _rel

# Sep 26 2026 (owner: "names in capital letters are read as letters"; "apply the
# existing rules properly"). For these tables the text is prepared the way the apps'
# device preprocess prepares it before the table runs:
#   1. the curly apostrophe is folded to the straight one the table keys use
#      ("Girls’ Generation" never matched the key "Girls' Generation");
#   2. a stray ALL-CAPS word ("EXCLUSIVE", "JENNIE", "SEKIRO") becomes Title case so
#      gTTS reads it as a word, not letter by letter. Short tokens (<= 3 letters),
#      tokens without a vowel (BTS, NCT, SNSD, JTBC) and the letter-style acronyms
#      below keep their capitals. Table keys match case-insensitively, so a caps key
#      ("BLACKPINK", "AKMU") still gets its respelling;
#   3. a key that starts or ends with a non-word character ("&TEAM", "(G)I-DLE",
#      "D.O.", "f(x)") is anchored with lookarounds; `\b` next to such a character
#      only matched when a letter touched it, so those rows never fired.
# Opt-in per table so other apps' tables change only when their lane opts them in.
SPEECH_NORMALIZE = {
    "kpop_en", "kpop_es", "kpop_pt", "anime_en", "tropic_en", "tropic_id", "tropic_vi",
    # P2 lane tables (opted in by P2, Sep 26 2026). A manifest without a table still
    # gets the apostrophe fold and the caps pass.
    "bollywood", "bollywood_hi", "hype_id", "tinh_vi",
    "circuitly_en", "circuitly_es", "circuitly_pt", "circuitly_vi", "circuitly_de", "circuitly_fr", "circuitly_it",
    "tickerly_en", "tickerly_es", "tickerly_pt", "tickerly_vi", "tickerly_id", "tickerly_de", "tickerly_fr",
    "tickerly_it", "tickerly_hi",
}
# Letter-style acronyms of 4+ letters that contain a vowel (the rest keep their caps anyway).
# K-pop / anime (P1), plus the device keep-sets of the P2 apps and Soundica FM (P3), so
# the baked car audio and the phone/AAOS TTS keep the same capitals.
LETTER_ACRONYMS = {
    "BTOB", "AOMG", "ADHD", "CSAT", "RIAJ", "SPOTV", "KCON", "NCAA", "OECD", "IPTV", "IIFA",
    "BCCI", "FWICE", "ICICI", "IMAX", "IMDB",
    "AMOLED", "ANPD", "AOSP", "ASML", "BMVI", "CATL", "EEUU", "HDMI", "ICLR", "IEEE", "IPAD", "JMGO", "OCDE",
    "OLED", "POLED", "PUBG", "QLED", "RDNA", "RGEV", "RTVE", "TGIQF", "UEFI", "USAF", "WLAN",
    "AAHL", "AAPL", "ADBE", "AMRT", "APUS", "AVGO", "BASF", "BBCA", "BBVA", "BCRA", "BIDV", "BPER", "DPIIT",
    "EBUS", "EMEA", "EPFO", "ESDM", "FSSAI", "FTSE", "GOOG", "GOOGL", "HOFC", "IBGE", "IBJA", "IBOV", "ICMS",
    "IFIX", "IHSG", "INDFUT", "INKP", "INPS", "INTC", "IPCA", "IRDAI", "ISIN", "MBMA", "MSCI", "MSME", "NPCI",
    "NTRA", "NVDA", "ORCL", "PSEL", "PTFI", "PYPL", "SPBU", "TSLA", "UBND", "UKOIL", "UMKM", "USDC", "USDT",
    "USGS", "USTR", "WDAY", "WEGZY", "ANTV", "BPOM", "ITDC", "OOTD", "RCTI", "TVRI", "NSƯT", "TAND",
    "IRCTC", "NHTSA", "USMCA", "NAACP", "AICTE", "UPITS", "UEFA", "OPEC",
    # Short (2-3 letter) acronyms that keep their letters even in a shouting headline. WHO is
    # deliberately absent: it is the organization or the word "who", so it keeps its capitals
    # in a normal sentence (not a short word) and becomes "Who" only when the headline shouts.
    "BTS", "NCT", "TXT", "UFC", "CEO", "USA", "OMG", "OST", "EP", "LP", "AI", "IA", "UK", "US", "EU", "UE",
    "UN", "IPO", "ETF", "AAA", "MMA", "SMA", "AOA", "INI", "JYP", "EUA", "GDA", "KST", "OTT", "IFA", "UPI",
    "EMI", "ATM", "ID", "IU", "OK", "UV", "EV",
    # P2 pools (v2 review): letter-style in their headlines and datelines.
    "RBI", "SBI", "KYC", "SME", "MSI", "PMI", "AFX",
}
_VOWELS = set("AEIOU")
# FORCE_APP="bollywood" (or "all") re-bakes that app ignoring the R2 cache +
# per-app cap, so a pronunciation/voice change overwrites the old audio.
FORCE_APP = os.environ.get("FORCE_APP", "").strip().lower()

_phon_cache: dict[str, list] = {}
def load_phonetics(slug: str) -> list:
    if slug in _phon_cache:
        return _phon_cache[slug]
    rules: list[tuple[str, str]] = []
    path = PHONETICS.get(slug)
    if path and os.path.exists(path):
        seen: set[str] = set()
        with open(path, encoding="utf-8-sig") as f:
            for i, line in enumerate(f):
                if i == 0:
                    continue
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                c = line.find(",")
                if c <= 0:
                    continue
                frm, to = line[:c].strip(), line[c + 1:].strip()
                if not frm or not to or frm.lower() in seen:
                    continue
                seen.add(frm.lower())
                rules.append((frm, to))
        rules.sort(key=lambda r: len(r[0]), reverse=True)  # longest first
        print(f"[{slug}] loaded {len(rules)} phonetic rules from {path}")
    _phon_cache[slug] = rules
    return rules

def _has_vowel(tok: str) -> bool:
    for i, ch in enumerate(tok):
        base = unicodedata.normalize("NFD", ch)[0].upper()
        if base in _VOWELS or (base == "Y" and i > 0):
            return True
    return False

# Common 2-3 letter words that are Title-cased when written in capitals ("THE", "LA", "DAN");
# short acronyms (BTS, CEO, USA, AI, IA) are NOT in these lists. One list per voice language.
SHORT_WORDS = {
    "en": {"THE", "AND", "FOR", "BUT", "NOT", "NOR", "ARE", "WAS", "HAS", "HAD", "HOW", "WHY", "OUR", "HIS",
           "HER", "HIM", "SHE", "YOU", "ITS", "CAN", "GET", "GOT", "NEW", "BIG", "HIT", "TOP", "ONE", "TWO",
           "SIX", "TEN", "WIN", "WON", "ALL", "OUT", "NOW", "OFF", "DAY", "BOY", "MAN", "OLD", "RED", "HOT",
           "POP", "FAN", "SET", "SAY", "SEE", "LET", "YES", "WAY", "OF", "IN", "ON", "TO", "AT", "IS", "IT",
           "BE", "AS", "BY", "OR", "AN", "MY", "WE", "HE", "SO", "NO", "DO", "GO", "ME", "IF"},  # not UP: Uttar Pradesh
    "es": {"EL", "LA", "LOS", "LAS", "UN", "UNA", "DE", "DEL", "AL", "EN", "CON", "POR", "QUE", "SE", "SU",
           "SUS", "NO", "ES", "LO", "LE", "MÁS", "MAS", "SIN", "HOY", "YA", "MUY", "SI", "SÍ", "MI", "TU", "YO",
           "ESO", "ESA", "VA", "VAN", "FUE", "SON", "HAY"},
    "pt": {"OS", "AS", "DE", "DO", "DA", "DOS", "DAS", "EM", "NO", "NA", "NOS", "NAS", "UM", "UMA", "COM",
           "POR", "QUE", "SE", "SEU", "SUA", "AO", "AOS", "NÃO", "SÃO", "JÁ", "MEU", "TEM", "VAI", "SEM", "BOM",
           "TÁ", "ELE", "ELA", "FOI"},
    "id": {"DAN", "DI", "KE", "INI", "ITU", "ADA", "APA", "DIA", "AKU", "KAU", "TAK", "YA"},
    "vi": {"VÀ", "LÀ", "CÓ", "CỦA", "CHO", "VỚI", "KHI", "ĐÃ", "SẼ", "BỊ", "MỚI", "NÀY", "CÁC", "MỘT", "TỪ",
           "ĐI", "RA", "VỀ", "LẠI", "CÒN", "SAO", "GÌ", "ANH", "EM", "CÔ", "BÀ", "ÔNG", "HAY", "NHƯ", "ĐỂ",
           "TẠI", "SAU"},
    "de": {"DER", "DIE", "DAS", "UND", "IST", "MIT", "VON", "DEN", "DEM", "EIN", "AUF", "FÜR", "IM", "AM",
           "ZU", "ES", "ER"},
    "fr": {"LE", "LA", "LES", "DE", "DU", "DES", "UN", "UNE", "ET", "EN", "AU", "AUX", "EST", "SUR", "PAR",
           "QUI", "QUE", "IL"},
    "it": {"IL", "LO", "LA", "LE", "GLI", "DI", "DA", "IN", "CON", "SU", "PER", "UN", "UNA", "CHE", "NON",
           "DEL", "DEI"},
}
# A segment (sentence) is SHOUTING when it has >= 3 words of 2+ characters (any script: a
# Devanagari word counts, so a Hindi line with one Latin acronym never shouts) and at least
# this share of them is in capitals; then every capitals word of 2+ letters is Title-cased,
# except LETTER_ACRONYMS, words without a vowel and bracketed tokens.
SHOUT_SHARE = 0.6

def _caps_tokens(text: str):
    """(start, end, token) for runs that start with a letter: letters, combining marks
    (Devanagari vowel signs), digits, and an apostrophe followed by a letter ("PROJECT'S")."""
    i, n = 0, len(text)
    while i < n:
        if not text[i].isalpha():
            i += 1; continue
        j = i
        while j < n and (text[j].isalpha() or text[j].isdigit()
                         or unicodedata.category(text[j]).startswith("M")
                         or (text[j] == "'" and j + 1 < n and text[j + 1].isalpha())):
            j += 1
        yield i, j, text[i:j]
        i = j

def _segment_ids(text: str) -> list:
    """Segment number per character: a new segment starts after ". ", "! ", "? " or a newline."""
    ids, seg = [], 0
    for k, ch in enumerate(text):
        ids.append(seg)
        if ch == "\n" or (ch in ".!?" and k + 1 < len(text) and text[k + 1].isspace()):
            seg += 1
    return ids

def normalize_caps(text: str, lang: str = "en") -> str:
    """Title-case stray ALL-CAPS words (see SPEECH_NORMALIZE). Length-preserving.
    >= 4 letters: always; 2-3 letters: when the word is in SHORT_WORDS[lang] or its
    segment is shouting. Never: LETTER_ACRONYMS, no vowel, bracketed "(ELSA)"."""
    short = SHORT_WORDS.get(lang, set())
    toks = list(_caps_tokens(text))
    seg_of = _segment_ids(text)
    words, caps = {}, {}
    for i, j, tok in toks:
        word = tok.split("'")[0]
        if len(word) >= 2:
            sg = seg_of[i]
            words[sg] = words.get(sg, 0) + 1
            if word.isalpha() and word.upper() == word and word.lower() != word:
                caps[sg] = caps.get(sg, 0) + 1
    shouting = {sg for sg, c in words.items() if c >= 3 and caps.get(sg, 0) / c >= SHOUT_SHARE}
    out = list(text)
    for i, j, tok in toks:
        word = tok.split("'")[0]   # "PROJECT'S" is judged on "PROJECT"
        if not (len(word) >= 2 and word.isalpha() and word.upper() == word and word.lower() != word):
            continue
        # A token wrapped exactly in brackets is a ticker or acronym gloss: "(ELSA)", "(CBFC)".
        if i > 0 and text[i - 1] == "(" and j < len(text) and text[j] == ")":
            continue
        # The language's own short word wins over the global acronym set (es "UN" is "un").
        if word.upper() in short or (
                word.upper() not in LETTER_ACRONYMS and _has_vowel(word)
                and (len(word) >= 4 or seg_of[i] in shouting)):
            for k in range(i + 1, j):
                out[k] = text[k].lower() if len(text[k].lower()) == 1 else text[k]
    return "".join(out)

def _key_pattern(frm: str) -> str:
    start = r"(?<!\w)" if _re.match(r"\w", frm[0]) else ""
    end = r"(?!\w)" if _re.match(r"\w", frm[-1]) else ""
    return start + _re.escape(frm) + end

def _slug_lang(slug: str) -> str:
    """Voice language of a table key, derived from MANIFESTS / APPS (the SSOT)."""
    for m in MANIFESTS:
        if m["phonetics"] == slug:
            return m["lang"]
    for a in APPS:
        if a.get("phonetics") == slug:
            return a["lang"]
    return slug.rsplit("_", 1)[-1] if "_" in slug else "en"

def apply_phonetics(text: str, slug: str) -> str:
    if slug in SPEECH_NORMALIZE:
        text = text.replace("\u2019", "'").replace("\u2018", "'").replace("\u02bc", "'")
        text = normalize_caps(text, _slug_lang(slug))
        for frm, to in load_phonetics(slug):
            text = _re.sub(_key_pattern(frm), lambda _m, _to=to: _to, text, flags=_re.IGNORECASE)
        return text
    for frm, to in load_phonetics(slug):
        text = _re.sub(r"\b" + _re.escape(frm) + r"\b", to, text, flags=_re.IGNORECASE)
    return text

# ---------- R2 client ------------------------------------------------------

s3 = boto3.client(
    "s3",
    aws_access_key_id=R2_ACCESS_KEY,
    aws_secret_access_key=R2_SECRET_KEY,
    endpoint_url=R2_ENDPOINT,
    region_name="auto",
)

# ---------- Helpers --------------------------------------------------------

def article_key(article_id: str) -> str:
    h = hashlib.sha256(article_id.encode("utf-8")).hexdigest()[:32]
    return f"{h}.mp3"

def r2_exists(key: str) -> bool:
    try:
        s3.head_object(Bucket=R2_BUCKET, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return False
        raise

# Sep 24 2026 (r6) one-shot RE-VOICE. The workers now fold the em dash and drop edition
# tags in "source", and text_for drops tags from the spoken source, but an id already in
# R2 is never re-synthesized, so its MP3 still says the old name. The first pass of this
# code writes _retext/<tag>.json with its start time (the cutover); every later pass
# re-synthesizes, in place, any window item of RETEXT_APPS whose MP3 is OLDER than the
# cutover, up to RETEXT_MAX_PER_PASS per manifest. A re-voiced MP3 is newer than the
# cutover, so each id is redone once and the mode ends on its own; it is also switched
# off RETEXT_TTL_MS after the cutover, when every such id has left the window. A failed
# re-voice keeps the old audio and the item (it retries next pass), so a manifest can
# never shrink because of this mode.
RETEXT_TAG = "r6-2026-09-24"
RETEXT_APPS = {"anime", "kpop", "circuitly", "bollywood", "tickerly", "tropic"}
RETEXT_MAX_PER_PASS = 5   # Sep 24 2026: 30 made a pass take hours and starved fresh bakes
RETEXT_TTL_MS = 7 * 24 * 3600 * 1000   # 5/pass needs more passes; auto-terminates when done
_retext_cut: dict = {}

# Sep 26 2026 (r7, P1 pronunciation round): a TARGETED re-voice for the K-pop, tropic and
# anime manifests. The ids file lists, per manifest, the stories whose spoken text changes
# under the Sep 26 tables and apply_phonetics (generated from the live manifests at
# generated_ms). A window item of a listed manifest is redone once, after the r7 cutover,
# when it is listed OR its MP3 was baked after generated_ms (baked with the old rules
# before this change was deployed). Same per-pass budget, TTL and keep-old-audio rule.
RETEXT_TARGETED_TAG = "r7-2026-09-26"
RETEXT_TARGETED_FILE = "retext/r7-2026-09-26.json"
_targeted: list = []

def retext_targeted() -> dict:
    if not _targeted:
        try:
            with open(RETEXT_TARGETED_FILE, encoding="utf-8") as f:
                _targeted.append(json.load(f))
        except Exception as e:
            print(f"[retext] targeted list unavailable: {e}")
            _targeted.append({})
    return _targeted[0]

def retext_cutover_ms(tag: str = RETEXT_TAG) -> int | None:
    if tag in _retext_cut:
        return _retext_cut[tag]
    cut = None
    key = f"_retext/{tag}.json"
    try:
        try:
            obj = s3.get_object(Bucket=R2_BUCKET, Key=key)
            cut = int(json.loads(obj["Body"].read().decode("utf-8"))["cutover_ms"])
        except ClientError as e:
            if e.response["Error"]["Code"] not in ("404", "NoSuchKey", "NotFound"):
                raise
            cut = int(time.time() * 1000)
            s3.put_object(Bucket=R2_BUCKET, Key=key, ContentType="application/json",
                          Body=json.dumps({"cutover_ms": cut}).encode("utf-8"))
            print(f"[retext] cutover set {cut}")
        if int(time.time() * 1000) - cut > RETEXT_TTL_MS:
            cut = None
    except Exception as e:
        print(f"[retext] disabled for this pass: {e}")
        cut = None
    _retext_cut[tag] = cut
    return cut

def r2_modified_ms(key: str) -> int | None:
    try:
        h = s3.head_object(Bucket=R2_BUCKET, Key=key)
        return int(h["LastModified"].timestamp() * 1000)
    except Exception:
        return None

def upload(key: str, data: bytes) -> None:
    s3.put_object(
        Bucket=R2_BUCKET,
        Key=key,
        Body=data,
        ContentType="audio/mpeg",
        # 30-day immutable cache. Article content is keyed by hash of article-id
        # so a re-bake will land on a different key; same key always = same audio.
        CacheControl="public, max-age=2592000, immutable",
    )

# Strip HTML tags + collapse whitespace before TTS so we don't speak markup.
_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

def clean_text(t: str) -> str:
    t = _HTML_RE.sub(" ", t or "")
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
    t = _WS_RE.sub(" ", t).strip()
    return t

# ---------- Social residue (Sep 26 2026, SX): the apps' SocialResidue.kt, mirrored ----------
# Owner, Sep 26 (Appning car, KPop Today): "LE SSERAFIM's Chaewon | @_chaechae_1/Instagram" was
# read aloud. "We also made a set of rules about reading the social ids, why did you do this
# again?" The Sep 23 rules covered tweet credits only. Rule: a raw social handle is never spoken.
# The worker feed carries photo and embed credits in summaries ("Name | @handle/Instagram",
# "View this post on Instagram A post shared by Name (@handle)", "Soompi (@soompi) September 21,
# 2026", "Reproducao/Instagram", instagram.com/p/... links, a lone "@handle"; counts from 7,203
# harvested summaries in R/reports/SX_report.md). strip_social_residue() runs the same rules in
# the same order as stripSocialResidue() in every news app (vectors pinned in
# tests/test_social_residue.py and in each app's SocialResidueTest), so the voiced text and the
# text the app shows and plans its headline cut on stay the same. Not here: the apps' and the
# workers' unserved-script rule, which needs the app's served scripts; the worker has already
# applied it to this feed. Kept: prose that names a platform ("posted on Instagram"), e-mail
# addresses, "@34" age markers. Word edges are spelled out ([A-Za-z0-9_] look-arounds, never \b):
# Python, ICU (device) and the JVM (app unit tests) disagree on \b next to a non-ASCII letter.
_SR_B0 = r"(?<![A-Za-z0-9_])"
_SR_B1 = r"(?![A-Za-z0-9_])"
_SR_PLAT = (r"(?:Instagram|IG|X|Twitter|TikTok|Tiktok|Weibo|Facebook|FB|Threads|YouTube|Youtube|Pinterest|Naver|"
            r"Weverse|Bluesky|Snapchat)")
_SR_PLATW = r"(?:Instagram|Twitter|TikTok|Tiktok|Weibo|Facebook|Threads|YouTube|Youtube|Pinterest|Naver|Weverse)"
_SR_H = (r"@(?=[A-Za-z0-9_.]*[A-Za-z])(?![A-Za-z0-9_.]*\.(?:com|net|org|edu|gov)(?![A-Za-z0-9_]))"
         r"[A-Za-z0-9_](?:[A-Za-z0-9_.]*[A-Za-z0-9_])?")
# A handle as a checker sees it (tools/social_handle_check.py): not the tail of an e-mail or URL.
SOCIAL_HANDLE_RE = re.compile(r"(?<![A-Za-z0-9_.@/])" + _SR_H)
_SR_SOCIAL_DOMAIN = (r"(?:www\.|m\.|mobile\.|vm\.)?(?:instagram\.com|instagr\.am|twitter\.com|x\.com|t\.co|tiktok\.com|"
                     r"threads\.net|threads\.com|facebook\.com|fb\.watch|weibo\.com|youtube\.com|youtu\.be|bsky\.app)"
                     r"/[^\s)\]]*")
_SR_SOCIAL_URL = r"(?:https?://" + _SR_SOCIAL_DOMAIN + r"|(?<![A-Za-z0-9_.-])" + _SR_SOCIAL_DOMAIN + r")"
_SR_MONTH = (r"(?:January|February|March|April|May|June|July|August|September|October|November|December|"
             r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)")
_SR_CREDIT_KW = (r"(?:[Pp]hotos?|PHOTOS?|[Ff]otos?|FOTOS?|[Ii]mages?|IMAGES?|[Ii]magem|[Ii]magen|[\u1ea2\u1ea3]nh|\u1ea2NH|"
                 r"[Nn]gu\u1ed3n|[Cc]redits?|[Cc]r[\u00e9e]ditos?|[Cc]r[\u00e9e]dit|[Ss]umber|[Ff]onte|[Ff]uente|[Qq]uelle|"
                 r"[Bb]ild|[Ss]ource)")
_SR_CREDIT_HEAD = (_SR_CREDIT_KW + r"(?:\s*[:\uff1a]|\s+(?:[Cc]redits?|[Cc]ourtesy(?:\s+of)?|by|oleh|de|via|[Cc]r\.)"
                   r"(?:\s*[:\uff1a])?)")
_SR_CRED = (r"(?:" + _SR_H + r"(?:\s*/\s*" + _SR_PLAT + _SR_B1 + r")?|" + _SR_PLAT + r"\s*/\s*" + _SR_H + r"|" + _SR_PLATW +
            r"(?!\s+(?:Music|Shorts|Premium|Originals|TV|Live|Reels|Stories)" + _SR_B1 + r"))")
_SR_RULES_1 = [
    # "Instagram: @handle", "X (Japan): @handle", "Official X (Twitter): x.com/handle"
    re.compile(r"(?:" + _SR_B0 + r"Official\s+)?" + _SR_B0 + _SR_PLAT + r"(?:\s*\([^()\n]{1,24}\))?\s*[:\uff1a]\s*(?:" +
               _SR_H + r"|" + _SR_SOCIAL_URL + r")"),
    # instagram.com/p/..., x.com/..., t.co/..., youtu.be/... (pic.twitter is the Sep 23 rule)
    re.compile(_SR_SOCIAL_URL),
    # embed boilerplate, per served language
    re.compile(r"View this post on (?:Instagram|TikTok|Threads|X|Twitter|Facebook|YouTube)|View on (?:Threads|Instagram)|"
               r"Lihat postingan ini di Instagram|Ver esta publicaci[\u00f3o]n en Instagram|"
               r"Ver (?:essa|esta) (?:publica[\u00e7c][\u00e3a]o|foto) no Instagram|Voir cette publication sur Instagram|"
               r"Diesen Beitrag auf Instagram ansehen|Visualizza questo post su Instagram|"
               r"Xem b\u00e0i vi\u1ebft n\u00e0y tr\u00ean Instagram"),
    re.compile(r"(?:A (?:post|photo|video) (?:shared|posted) by|Sebuah kiriman dibagikan oleh|"
               r"Una publicaci[\u00f3o]n compartida (?:por|de)|Uma publica[\u00e7c][\u00e3a]o compartilhada por|"
               r"Um post compartilhado por|Une publication partag[\u00e9e]e par|Ein Beitrag geteilt von|"
               r"Un post condiviso da|B\u00e0i vi\u1ebft do)"
               r"(?:\s*[^()\n@]{0,60}?\s*\(\s*" + _SR_H + r"\s*\)|\s*" + _SR_H + r")?(?:\s+chia s\u1ebb)?"),
    re.compile(_SR_B0 + r"Post by\s+" + _SR_H),
    # a tweet credit that lost its dash: "Soompi (@soompi) September 21, 2026"
    re.compile(r"(?:[A-Z0-9][^\s()]*\s+){0,4}\(\s*" + _SR_H + r"\s*\)\s+" + _SR_MONTH + r"\.?\s+\d{1,2},\s+\d{4}"),
    # "Follow NCT WISH: TikTok | X | Instagram | YouTube"
    re.compile(r"(?:" + _SR_B0 + r"(?:Follow|FOLLOW|Siga|Sigue|Ikuti|Suivez|Folgt)\s+[^|\n:]{0,40}?:?\s*)?(?:" + _SR_PLATW +
               r"|X)(?:\s*\|\s*(?:" + _SR_PLATW + r"|X|Spotify|Apple Music|Website|Tickets)" + _SR_B1 + r")+(?:\s*\|)?"),
]
# A photo caption credit at a sentence start goes with its caption: "LE SSERAFIM's Chaewon | @_chaechae_1/Instagram"
_SR_CAPTION = re.compile(r"(^|[.!?\u2026\"\u201d\u2019)\]]\s+)(?:[^.!?|\n]{1,60}?\s+)?\|\s*" + _SR_CRED +
                         r"(?:\s*\|\s*" + _SR_CRED + r")*(?=\s|$)")
_SR_RULES_2 = [
    # the same credit mid-sentence: only the credit goes
    re.compile(r"\s*\|\s*" + _SR_CRED + r"(?:\s*\|\s*" + _SR_CRED + r")*(?=\s|$)"),
    # "(Foto: Instagram/@handle)", "(Imagem: Reproducao/YouTube/...)", "(Anh: @handle)"
    re.compile(r"\(\s*" + _SR_CREDIT_HEAD + r"[^()\n]{0,60}?(?:" + _SR_H + r"|" + _SR_B0 + _SR_PLAT + _SR_B1 +
               r")[^()\n]{0,60}\)"),
    # "Foto: Instagram/@handle", "Photo: @handle", "Anh: @handle"
    re.compile(_SR_B0 + _SR_CREDIT_HEAD + r"\s*(?:(?:[Dd]ok\.?\s*)?" + _SR_PLAT + r"\s*[/:]?\s*)?" + _SR_H + r"(?:\s*/\s*" +
               _SR_PLAT + _SR_B1 + r")?"),
    # "Foto: Instagram", "Source: X"
    re.compile(_SR_B0 + _SR_CREDIT_KW + r"\s*[:\uff1a]\s*(?:[Dd]ok\.?\s*)?" + _SR_PLAT + r"(?=[\s.,;)]|$)"),
    # "Reproducao/Instagram/Roberta Miranda", "Reproducao/TikTok"
    re.compile(_SR_B0 + r"(?:Reprodu[\u00e7c][\u00e3a]o|REPRODU[\u00c7C][\u00c3A]O|Divulga[\u00e7c][\u00e3a]o|"
               r"DIVULGA[\u00c7C][\u00c3A]O|Reproducci[\u00f3o]n|Captura(?: de tela| de pantalla)?|Screenshot|"
               r"Tangkapan layar)\s*/\s*" + _SR_PLAT + _SR_B1 +
               r"(?:\s*/\s*(?:[A-Z\u00c0-\u00dd][^\s/()]*(?:\s+[A-Z\u00c0-\u00dd][^\s/()]{2,})?|[^\s/()]+))?"),
    # "@handle/Instagram", "Instagram/@handle"
    re.compile(_SR_H + r"\s*/\s*" + _SR_PLAT + _SR_B1 + r"|" + _SR_B0 + _SR_PLAT + r"\s*/\s*" + _SR_H),
    # "(@handle)", "(via @handle)", "(Instagram @handle)"
    re.compile(r"\(\s*(?:(?:via|" + _SR_PLAT + r")\s*:?\s*)?" + _SR_H + r"(?:\s*/\s*" + _SR_PLAT + _SR_B1 + r")?\s*\)"),
    re.compile(_SR_B0 + r"[Vv]ia\s+" + _SR_H),
    # any handle left, with the run it heads: "@a, @b and @c"
    re.compile(r"(?<![A-Za-z0-9_.@/])" + _SR_H + r"(?:(?:\s*,\s*|\s+(?:(?:and|&|e|y|et|und|dan|v\u00e0|ou|o)\s+)?)" +
               _SR_H + r")*"),
]
# Tidy, only when a social rule removed something (clean text keeps its exact form).
_SR_TIDY = [
    (re.compile(r"[(\[]\s*[,.;:/|&-]*\s*[)\]]"), " "),
    (re.compile(r"\s+"), " "),
    (re.compile(r"\s*\|\s*(?=\||$)|^\s*\|\s*"), " "),
    (re.compile(r"([,;:])(?:\s*[,;:])+"), r"\1"),
    (re.compile(r"[,;:]\s*(?=[.!?])"), ""),
    (re.compile(r"^[\s,;:|/-]+"), ""),
]
# The Sep 23 rules (the apps' and workers' first version): pic.twitter tokens, dashed tweet credits,
# "[#label]" tags and hashtag-only runs.
_SR_PIC_TWITTER = re.compile(r"(?:https?://)?pic\.twitter(?:\.com)?(?:/\S*)?\.?", re.I)
_SR_TWEET_CREDIT = re.compile(r"\s[\u2014\u2013-]\s*(?:[^()\n@]{1,60}\s)?\(?@\w{1,15}\)?(?:\s*\(?(?:[A-Z][a-z]{2,8}\.? "
                              r"\d{1,2}(?:, \d{4})?|\d{1,2}/\d{1,2}/\d{2,4})\)?)?")
_SR_BRACKET_HASHTAG = re.compile(r"\[#[^\]\n]{1,40}\]")
_SR_HASHTAG_RUN = re.compile(r"(?:#\w+[\s,]*){2,}")
_SR_SPACE_BEFORE_PUNCT = re.compile(r"\s+([.,;:!?])")

def strip_social_handles(t: str) -> str:
    """The Sep 26 handle, photo-credit and embed rules; clean text comes back unchanged."""
    s = t
    for rx in _SR_RULES_1:
        s = rx.sub(" ", s)
    s = _SR_CAPTION.sub(lambda m: m.group(1) or " ", s)
    for rx in _SR_RULES_2:
        s = rx.sub(" ", s)
    if s == t:
        return t
    for rx, rep in _SR_TIDY:
        s = rx.sub(rep, s)
    return s

def strip_social_residue(text: str) -> str:
    """stripSocialResidue() of the apps, minus the unserved-script rule (see the block note)."""
    if not text or not text.strip():
        return text
    t = _SR_TWEET_CREDIT.sub(" ", _SR_PIC_TWITTER.sub(" ", text))
    t = strip_social_handles(t)
    t = _SR_HASHTAG_RUN.sub(" ", _SR_BRACKET_HASHTAG.sub(" ", t))
    return _SR_SPACE_BEFORE_PUNCT.sub(r"\1", _WS_RE.sub(" ", t)).strip()

# Worker feed JSON can carry LONE UTF-16 surrogate halves: some publishers encode
# an emoji as two HTML numeric entities (&#55358;&#56596;), the JS worker passes them
# through as "\ud83e"-style escapes (JS strings tolerate WTF-16), and Python's
# json.loads accepts them — but a later .encode("utf-8") REFUSES ("surrogates not
# allowed"). That killed the whole Jul 2 2026 run at the circuitly_pt manifest write
# (and silently skipped every manifest after it). Repair adjacent halves back into
# the real emoji and drop truly lone halves at INGEST, so neither gTTS nor
# write_manifest ever sees one.
def fix_surrogates(s: str) -> str:
    try:
        s.encode("utf-8")
        return s
    except UnicodeEncodeError:
        # utf-16 surrogatepass re-joins a high+low pair into the real code point;
        # errors="ignore" drops any half that has no partner.
        return s.encode("utf-16", "surrogatepass").decode("utf-16", "ignore")

def sanitize_article(article: dict) -> dict:
    return {k: (fix_surrogates(v) if isinstance(v, str) else v) for k, v in article.items()}

# Sep 24 2026 (r6): a roster edition tag ("KoreanIndo (ID)", "Kenh14 Star (VN)",
# "Investing.com France (FR)") must not be READ ALOUD. Spoken text only: the manifest
# "source" field is untouched, because on kpop-tropic it is the appning logo key.
# Same rule as the workers' stripEditionTag: a 2-letter upper-case code, alone or as
# the head of "(AA/Region)". Anything else ("Quem (Globo, BR)") stays.
def spoken_source(name: str) -> str:
    n = name.rstrip()
    if not n.endswith(")"):
        return name
    op = n.rfind(" (")
    if op <= 0:
        return name
    tag = n[op + 2:-1]
    head = tag.split("/")[0]
    is_code = len(head) == 2 and head.isascii() and head.isalpha() and head.isupper()
    if not is_code or (len(tag) != 2 and len(tag) < 4):
        return name
    return n[:op].rstrip()

def text_for(article: dict) -> str:
    title = clean_text(article.get("title", ""))
    # Sep 26 2026 (SX): a social handle, photo credit or embed line in the summary is never voiced.
    # The appning apps plan the headline cut on the same cleaned summary (BakedHeadlineCut).
    summary = strip_social_residue(clean_text(article.get("summary", "")))
    source = spoken_source(clean_text(article.get("source", "")))
    body_parts = []
    if source:
        body_parts.append(f"{source},")
    if title:
        body_parts.append(title)
        if not title.endswith((".", "!", "?")):
            body_parts.append(".")
    if summary and summary.lower() != title.lower():
        body_parts.append(summary[:FAIR_USE_SNIPPET])  # fair-use excerpt cap
    body = " ".join(body_parts).strip()
    return body[:MAX_TEXT_LEN]

def synth_to_mp3(text: str, lang: str, tld: str) -> bytes:
    tts = gTTS(text=text, lang=lang, tld=tld, slow=False)
    buf = BytesIO()
    tts.write_to_fp(buf)
    return buf.getvalue()

# ---------- Per-app bake loop ----------------------------------------------

def bake_app(app: dict[str, Any], breaker: "ThrottleBreaker | None" = None) -> tuple[int, int]:
    """Returns (baked_count, skipped_count) for logging. With a breaker (main()), its
    gTTS calls share the pass's 429 breaker and stop when it opens."""
    slug = app["slug"]
    lang = app["lang"]
    tld = app["tld"]
    feed_url = app["feed_url"]
    baked = 0
    skipped = 0
    seen_ids: set[str] = set()
    force = FORCE_APP in (slug, "all")
    if force:
        print(f"[{slug}] FORCE re-bake: ignoring R2 cache + per-app cap")

    for category in app["categories"]:
        try:
            r = requests.get(f"{feed_url}?category={category}", timeout=FEED_TIMEOUT_S)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"[{slug}/{category}] feed fetch failed: {e}")
            continue

        items = [sanitize_article(a) for a in data.get("items", []) if isinstance(a, dict)]
        print(f"[{slug}/{category}] feed has {len(items)} items")

        for article in items:
            aid = article.get("id")
            if not aid or aid in seen_ids:
                continue
            seen_ids.add(aid)

            key = article_key(aid)
            try:
                if not force and r2_exists(key):
                    skipped += 1
                    continue
            except Exception as e:
                print(f"[{slug}] head_object failed for {aid[:30]}: {e}")
                continue

            text = text_for(article)
            # Sep 26 2026: the table key, not the slug ("hype" has no table; "hype_id" does).
            text = apply_phonetics(text, app.get("phonetics", slug))
            if len(text) < MIN_TEXT_LEN:
                print(f"[{slug}] skipping {aid[:30]}: text too short ({len(text)} chars)")
                continue

            try:
                mp3 = breaker.synth(text, lang, tld, who=slug) if breaker else synth_to_mp3(text, lang, tld)
                upload(key, mp3)
                baked += 1
                print(f"[{slug}] baked {aid[:40]}... -> {key} ({len(mp3)} bytes)")
            except Exception as e:
                print(f"[{slug}] bake failed for {aid[:30]}: {e}")
                if breaker and breaker.tripped:
                    return baked, skipped
                if not is_throttle(e):
                    traceback.print_exc()
                continue

            if not force and baked >= MAX_NEW_BAKES_PER_APP:
                print(f"[{slug}] hit per-app bake cap ({MAX_NEW_BAKES_PER_APP}); stopping")
                return baked, skipped

    return baked, skipped

# ---------- Hindi pass -----------------------------------------------------

def bake_hindi(app: dict[str, Any]) -> tuple[int, int]:
    """Bake the Hindi feed with gTTS hi. Incremental on the cron (skips already-
    baked keys, like English); FORCE_APP=bollywood_hi/all_hi re-bakes all."""
    slug = app["slug"]
    force = FORCE_APP in (slug, "all", "bollywood_hi", "all_hi")
    baked = 0
    skipped = 0
    try:
        r = requests.get(app["feed_url"], timeout=FEED_TIMEOUT_S)
        r.raise_for_status()
        items = [sanitize_article(a) for a in r.json().get("items", []) if isinstance(a, dict)]
    except Exception as e:
        print(f"[{slug}/hi] feed fetch failed: {e}")
        return 0, 0
    print(f"[{slug}/hi] feed has {len(items)} items (force={force})")
    for article in items:
        aid = article.get("id")
        if not aid:
            continue
        key = article_key(aid)
        if not force and r2_exists(key):
            skipped += 1
            continue
        # Amar Ujala gives clean Hindi title + summary, so read the full text like
        # the English path; phonetics_hi transliterates any Latin names to Devanagari.
        text = apply_phonetics(text_for(article), app["phonetics_slug"])
        if len(text) < MIN_TEXT_LEN:
            continue
        try:
            mp3 = synth_to_mp3(text, app["lang"], app["tld"])
            upload(key, mp3)
            baked += 1
            print(f"[{slug}/hi] baked {aid[:40]} -> {key} ({len(mp3)} bytes)")
        except Exception as e:
            print(f"[{slug}/hi] bake failed for {aid[:30]}: {e}")
            traceback.print_exc()
        if not force and baked >= MAX_NEW_HINDI_BAKES:
            break
    print(f"[{slug}/hi] done: baked={baked} skipped={skipped} (force={force})")
    return baked, skipped

# ---------- Manifest pass (appning source of truth) ------------------------

def write_manifest(name: str, items: list[dict]) -> None:
    """Write the baked-article manifest to R2 as ArticleFeed-shaped JSON. The
    appning app reads this single global object, so every device sees the same
    list and every id in it is guaranteed to have an MP3 in the same bucket."""
    # fix_surrogates is a last-resort guard here (ingest sanitizing should make it
    # a no-op): a stray surrogate must never kill the run at the final write again.
    body = fix_surrogates(json.dumps(
        {"generatedAtMs": int(time.time() * 1000), "items": items},
        ensure_ascii=False,
    )).encode("utf-8")
    s3.put_object(
        Bucket=R2_BUCKET,
        Key=f"{name}.json",
        Body=body,
        ContentType="application/json; charset=utf-8",
        CacheControl="public, max-age=120",
    )
    print(f"[{name}] wrote manifest {name}.json ({len(items)} items, {len(body)} bytes)")

# Sep 26 2026 (GC4 handoff): a gTTS throttle and a stalled run look the same from outside:
# every synth fails, carry-forward keeps the manifest full, and the car hears day-old news.
# A manifest that had fresh stories to bake and baked none of them (they failed, or the
# 429 breaker deferred them) is recorded here; main() prints it and exits non-zero so the
# pass shows as FAILED. The workflow loop survives a failed pass.
_STARVED: list = []
MIN_MANIFEST_ITEMS = 5

# ---------- gTTS throttle circuit breaker ----------------------------------
# Sep 26 2026 (BK). Run 36174562701 (Sep 25, 10 passes over 5 h): gTTS answered
# "429 (Too Many Requests)" to the runner IP after ~476 synths in pass 1 and never let up.
# Passes 2-10 baked 0 stories and still sent 540-694 synth requests each (every excluded
# story retried on every pass, in every manifest, plus the re-voice): 5,908 failures in one
# run. Now a 429 gets ONE retry after a short jittered sleep, and THROTTLE_TRIP_429S 429s in
# a row open the breaker: no synth (fresh or re-voice) is attempted for the rest of the pass,
# the manifests are written with what is confirmed in R2, and the next pass tries again.
# The voice, language, tld and engine are unchanged.
THROTTLE_TRIP_429S = 3
THROTTLE_RETRY_BASE_S = 4.0
THROTTLE_RETRY_JITTER_S = 4.0
_sleep = time.sleep   # tests replace this
_THROTTLE_CODE = re.compile(r"\b429\b")

def is_throttle(e: BaseException) -> bool:
    """A gTTS 429: the HTTP status when gTTS kept the response, else its message."""
    if getattr(getattr(e, "rsp", None), "status_code", None) == 429:
        return True
    s = str(e)
    return bool(_THROTTLE_CODE.search(s)) and "too many requests" in s.lower()

class BreakerOpen(Exception):
    """Raised instead of a synth request once the breaker is open for this pass."""

class ThrottleBreaker:
    """Every gTTS call of a pass goes through one instance of this."""

    def __init__(self, trip_after: int = THROTTLE_TRIP_429S):
        self.trip_after = trip_after
        self.consecutive = 0   # 429s since the last successful synth
        self.total_429 = 0     # 429s this pass
        self.attempts = 0      # synth calls made this pass (a retry is a call)
        self.tripped = False

    def synth(self, text: str, lang: str, tld: str, who: str = "", retry: bool = True) -> bytes:
        tries = 2 if retry else 1
        for n in range(tries):
            if self.tripped:
                raise BreakerOpen("gTTS breaker open for this pass")
            self.attempts += 1
            try:
                mp3 = synth_to_mp3(text, lang, tld)
            except Exception as e:
                if not is_throttle(e):
                    raise
                self.total_429 += 1
                self.consecutive += 1
                if self.consecutive >= self.trip_after:
                    self.tripped = True
                    print(f"[throttle] {self.consecutive} gTTS 429s in a row (last at {who}): breaker OPEN, "
                          "no more synth this pass; manifests keep what is confirmed, the next pass retries")
                    raise
                if n + 1 < tries:
                    _sleep(THROTTLE_RETRY_BASE_S + random.uniform(0, THROTTLE_RETRY_JITTER_S))
                    continue
                raise
            self.consecutive = 0
            return mp3
        raise BreakerOpen("unreachable")

# ---------- Pass order: plan, fresh round-robin, write, re-voice -----------
# Sep 26 2026 (BK): a pass is now plan -> fresh round-robin -> write -> re-voice, across ALL
# manifests, instead of bake-then-write one manifest at a time. Before, the first manifests
# in the rotation drained the gTTS budget (Sep 25 pass 1: tickerly vi/id/de/fr/it baked 60
# each, then the throttle hit and 16 manifests baked none). Now each round bakes ONE fresh
# story per manifest, newest first, stalest manifest first, until the pending lists, the
# per-manifest cap or the breaker end it, so every car gets its newest story before any
# manifest gets a second one.
MANIFEST_FLUSH_S = 300   # re-write manifests that gained stories after round 1, then this often

def _pub_ms(a: dict) -> int:
    try:
        return int(a.get("publishedAtMs") or 0)
    except (TypeError, ValueError):
        return 0

def plan_manifest(m: dict[str, Any]) -> dict | None:
    """Fetch the EXACT feed url the appning app reads and sort its items into confirmed
    (MP3 in R2) and pending (to synth, newest first). No synth happens here."""
    name = m["manifest"]
    phon = m["phonetics"]
    force = FORCE_APP in (name, name.split("_")[0], "all")
    try:
        r = requests.get(m["feed_url"], timeout=FEED_TIMEOUT_S)
        r.raise_for_status()
        items = [sanitize_article(a) for a in r.json().get("items", []) if isinstance(a, dict)]
    except Exception as e:
        # Do NOT rewrite the manifest on a fetch failure — leave the last good one.
        print(f"[{name}] feed fetch failed: {e}; manifest left unchanged")
        return None
    print(f"[{name}] feed has {len(items)} items (force={force})")
    # Re-voice modes for this manifest: (cutover_ms, listed ids or None = every window item,
    # baked-after ms or None). An item is redone when its MP3 predates a mode's cutover and
    # the mode selects it.
    retext_modes: list[tuple[int, set | None, int | None]] = []
    if name.split("_")[0] in RETEXT_APPS:
        c = retext_cutover_ms()
        if c is not None:
            retext_modes.append((c, None, None))
    tgt = retext_targeted()
    if name in tgt.get("manifests", {}):
        c = retext_cutover_ms(RETEXT_TARGETED_TAG)
        if c is not None:
            retext_modes.append((c, set(tgt["manifests"][name]), int(tgt.get("generated_ms", 0))))
    window: list[dict] = []
    confirmed: set[str] = set()
    pending: list[tuple[dict, str, str, bool]] = []   # (article, key, text, mp3 already in R2)
    retext_candidates: list[tuple[str, str, dict]] = []
    seen: set[str] = set()
    skipped = 0
    for article in items:
        aid = article.get("id")
        if not aid or aid in seen:
            continue
        seen.add(aid)
        key = article_key(aid)
        try:
            exists = r2_exists(key)
        except Exception as e:
            print(f"[{name}] head_object failed {aid[:30]}: {e}")
            continue
        window.append(article)
        if exists and not force:
            if retext_modes:
                retext_candidates.append((aid, key, article))
            confirmed.add(aid)   # confirmed present
            skipped += 1
            continue
        if exists:
            confirmed.add(aid)   # FORCE re-bake: the old MP3 stays listed until the new one lands
        text = apply_phonetics(text_for(article), phon)
        if len(text) < MIN_TEXT_LEN:
            if not exists:
                print(f"[{name}] skip {aid[:30]}: text too short ({len(text)})")
            continue
        pending.append((article, key, text, exists))
    pending.sort(key=lambda j: _pub_ms(j[0]), reverse=True)   # newest first
    prev_items: list = []
    if not force:
        try:
            prev = s3.get_object(Bucket=R2_BUCKET, Key=f"{name}.json")
            prev_items = json.loads(prev["Body"].read().decode("utf-8")).get("items", [])
        except Exception:
            prev_items = []
    # What the car plays now: the newest confirmed story in the window or the live manifest.
    head_ms = max([_pub_ms(a) for a in window if a["id"] in confirmed]
                  + [_pub_ms(a) for a in prev_items if isinstance(a, dict)], default=0)
    return {
        "name": name, "lang": m["lang"], "tld": m["tld"], "phon": phon, "force": force,
        "window": window, "seen": seen, "confirmed": confirmed, "pending": pending,
        "fresh_total": sum(1 for j in pending if not j[3]), "prev_items": prev_items,
        "head_ms": head_ms, "retext_modes": retext_modes, "retext_candidates": retext_candidates,
        "skipped": skipped, "baked": 0, "fresh_baked": 0, "failed": 0, "retexted": 0,
        "dirty": False, "flushed": False, "written": False, "size": 0,
    }

def _bake_one(p: dict, job: tuple, breaker: ThrottleBreaker) -> None:
    """Synth + upload one story. It joins the manifest ONLY after a confirmed upload."""
    article, key, text, exists = job
    name, aid = p["name"], article["id"]
    try:
        mp3 = breaker.synth(text, p["lang"], p["tld"], who=name)
        upload(key, mp3)
    except Exception as e:
        p["failed"] += 1
        print(f"[{name}] bake FAILED {aid[:30]}: {e}; {'old audio kept' if exists else 'EXCLUDED from manifest'}")
        if not (is_throttle(e) or isinstance(e, BreakerOpen)):
            traceback.print_exc()
        return
    p["baked"] += 1
    if not exists:
        p["fresh_baked"] += 1
    p["confirmed"].add(aid)
    p["dirty"] = True
    print(f"[{name}] baked {aid[:40]} -> {key} ({len(mp3)} bytes)")

def bake_fresh(plans: list[dict], breaker: ThrottleBreaker) -> None:
    """Round-robin: each round bakes the newest pending story of every manifest (stalest
    manifest first). Keeps the per-manifest cap (MAX_NEW_HINDI_BAKES; FORCE ignores it)
    and stops the moment the breaker opens."""
    order = sorted(plans, key=lambda p: p["head_ms"])   # stable: rotation breaks ties
    rnd, last_flush = 0, time.monotonic()
    while not breaker.tripped:
        rnd += 1
        took = False
        for p in order:
            if breaker.tripped:
                break
            if not p["pending"] or (not p["force"] and p["baked"] >= MAX_NEW_HINDI_BAKES):
                continue
            took = True
            _bake_one(p, p["pending"].pop(0), breaker)
        if not took:
            break
        if rnd == 1 or time.monotonic() - last_flush >= MANIFEST_FLUSH_S:
            for p in plans:
                if p["dirty"]:
                    try:
                        finalize_manifest(p)
                    except Exception as e:   # main() writes it again after the fresh phase
                        print(f"[{p['name']}] manifest flush failed: {e}")
            last_flush = time.monotonic()

def finalize_manifest(p: dict) -> None:
    """Write the manifest: the confirmed window items (feed order) plus the carry-forward.
    Never an un-baked id; never a thin manifest over a good one."""
    name = p["name"]
    items = [a for a in p["window"] if a["id"] in p["confirmed"]]
    # Carry-forward union: keep the previous manifest's items whose ids rotated out
    # of the live window (MP3s confirmed in R2 by construction — see CARRY_MAX_AGE_MS
    # note). After a FORCE re-voice, carried items keep the old audio until they age
    # out (<=72h) — acceptable. Window items always win on id collision via `seen`.
    if not p["force"]:
        now_ms = int(time.time() * 1000)
        carried = [
            a for a in p["prev_items"]
            if isinstance(a, dict) and a.get("id") and a["id"] not in p["seen"]
            and 0 <= now_ms - int(a.get("publishedAtMs") or 0) <= CARRY_MAX_AGE_MS
        ]
        if carried:
            items.extend(carried)
            items.sort(key=lambda a: int(a.get("publishedAtMs") or 0), reverse=True)
            del items[MAX_MANIFEST_ITEMS:]
            print(f"[{name}] carried {len(carried)} prior items forward (total {len(items)})")
    # MIN floor: a successful-but-empty/thin feed (a transient worker hiccup on a
    # quiet language) must NOT clobber the last good manifest with an empty or
    # near-empty one, which would blank or 1-item the car language section. Skip
    # the write and leave the previous good manifest in place; the next cron bake
    # retries once the feed recovers. (A healthy manifest is dozens of items.)
    if len(items) < MIN_MANIFEST_ITEMS:
        print(f"[{name}] manifest only {len(items)} items (< {MIN_MANIFEST_ITEMS}); leaving last good manifest unchanged")
        p["dirty"], p["flushed"] = False, True
        return
    write_manifest(name, items)
    p["dirty"], p["flushed"], p["written"], p["size"] = False, True, True, len(items)

def report_starved(plans: list[dict]) -> None:
    for p in plans:
        if p["fresh_total"] and not p["fresh_baked"]:
            deferred = sum(1 for j in p["pending"] if not j[3])
            _STARVED.append((p["name"], p["fresh_total"]))
            print(f"[{p['name']}] STARVED: {p['fresh_total']} fresh stories, 0 baked this pass "
                  f"({p['failed']} failed, {deferred} deferred by the 429 breaker)")

def revoice(plans: list[dict], breaker: ThrottleBreaker) -> None:
    """r6/r7 re-voice, AFTER every manifest is written, and only in a pass that saw no
    gTTS 429: re-voicing old stories must never spend the budget that fresh stories need.
    At most RETEXT_MAX_PER_PASS per manifest; a failure keeps the old audio."""
    if breaker.total_429 or breaker.tripped:
        if any(p["retext_candidates"] for p in plans):
            print(f"[retext] skipped this pass: {breaker.total_429} gTTS 429s seen; fresh stories first")
        return
    for p in plans:
        if not p["written"]:
            continue
        name = p["name"]
        for aid, key, article in p["retext_candidates"]:
            if p["retexted"] >= RETEXT_MAX_PER_PASS:
                break
            mod = r2_modified_ms(key)
            if mod is None or not any(
                mod < cut and (ids is None or aid in ids or (after is not None and mod >= after))
                for cut, ids, after in p["retext_modes"]
            ):
                continue
            rtext = apply_phonetics(text_for(article), p["phon"])
            if len(rtext) < MIN_TEXT_LEN:
                continue
            try:
                upload(key, breaker.synth(rtext, p["lang"], p["tld"], who=name, retry=False))
                p["retexted"] += 1
                print(f"[{name}] re-voiced {aid[:40]} -> {key}")
            except Exception as e:
                print(f"[{name}] re-voice FAILED {aid[:30]}: {e}; old audio kept")
                if breaker.total_429 or breaker.tripped:
                    print("[retext] stopped for this pass after a gTTS 429")
                    return

def _done_line(p: dict) -> str:
    deferred = sum(1 for j in p["pending"] if not j[3])
    return (f"[{p['name']}] done: manifest={p['size']} baked={p['baked']} skipped={p['skipped']} "
            f"failed={p['failed']} deferred={deferred} (force={p['force']}) re-voiced={p['retexted']}")

def bake_manifest(m: dict[str, Any], breaker: ThrottleBreaker | None = None) -> tuple[int, int]:
    """One manifest on its own (ad hoc runs and tests): the same plan -> fresh -> write ->
    re-voice steps main() runs across all manifests."""
    breaker = breaker or ThrottleBreaker()
    p = plan_manifest(m)
    if p is None:
        return 0, 0
    bake_fresh([p], breaker)
    if p["dirty"] or not p["flushed"]:
        finalize_manifest(p)
    report_starved([p])
    revoice([p], breaker)
    print(_done_line(p))
    return p["baked"], p["skipped"]

# ---------- Soundica FM merged manifests ------------------------------------
# Aug 14 2026. Soundica FM's appning (FORVIA car) flavor is a multi-topic super
# app, but it shipped reading kpop_<lang>.json, so its car News tab could only
# ever offer K-Pop; the other categories sat empty and are now hidden by the
# app's honest-categories rule. Every missing category ALREADY has a baked
# sibling manifest in this bucket (circuitly=tech, tickerly=finance, anime,
# bollywood, kpop), so this pass just merges them into soundicafm_<lang>.json,
# stamping each item's `category` with its topic. The app buckets manifest
# articles by that field, so categories appear on the car with no app update
# once this file exists. No new synthesis happens here: component manifests
# list only ids whose MP3 is already confirmed in R2, so the merge inherits
# that guarantee for free.
#
# `entertainment` is deliberately absent: its only English sources are Google
# News queries, which are off-limits for the commercial baker path (see the
# COMMERCIAL POSTURE note in the memory doc), so the car simply does not offer
# that category.
SOUNDICA_FM_COMPONENTS: dict[str, list[tuple[str, str]]] = {
    "en": [("kpop", "kpop_en"), ("anime", "anime_en"), ("bollywood", "bollywood_en"),
           ("tech", "circuitly_en"), ("finance", "tickerly_en")],
    "es": [("kpop", "kpop_es"), ("tech", "circuitly_es"), ("finance", "tickerly_es")],
    "pt": [("kpop", "kpop_pt"), ("tech", "circuitly_pt"), ("finance", "tickerly_pt")],
    "vi": [("tech", "circuitly_vi"), ("finance", "tickerly_vi")],
    "de": [("tech", "circuitly_de"), ("finance", "tickerly_de")],
    "fr": [("tech", "circuitly_fr"), ("finance", "tickerly_fr")],
    "it": [("tech", "circuitly_it"), ("finance", "tickerly_it")],
    "id": [("finance", "tickerly_id")],
    "hi": [("bollywood", "bollywood_hi"), ("finance", "tickerly_hi")],
}
# Per-topic cap inside a merged manifest: enough for a full car shelf, small
# enough that five topics still fit a manifest the head unit parses instantly.
SOUNDICA_FM_PER_TOPIC = 20

def merge_soundicafm() -> None:
    for lang, comps in SOUNDICA_FM_COMPONENTS.items():
        merged: list[dict] = []
        seen_ids: set[str] = set()
        for topic, name in comps:
            try:
                obj = s3.get_object(Bucket=R2_BUCKET, Key=f"{name}.json")
                items = json.loads(obj["Body"].read().decode("utf-8")).get("items", [])
            except Exception as e:
                print(f"[soundicafm_{lang}] component {name} unavailable: {e}")
                continue
            items = [a for a in items if isinstance(a, dict) and a.get("id")]
            items.sort(key=lambda a: int(a.get("publishedAtMs") or 0), reverse=True)
            for a in items[:SOUNDICA_FM_PER_TOPIC]:
                if a["id"] in seen_ids:
                    continue
                seen_ids.add(a["id"])
                # The app's topic bucketing reads this field for manifest
                # articles; a component manifest's own category value (a
                # language tag on some) is not meaningful here.
                a = dict(a)
                a["category"] = topic
                merged.append(a)
        # Same thin-write guard as bake_manifest: never clobber a good merged
        # manifest with a near-empty one when components are transiently missing.
        if len(merged) < 5:
            print(f"[soundicafm_{lang}] only {len(merged)} items; leaving previous manifest unchanged")
            continue
        write_manifest(f"soundicafm_{lang}", merged)

# ---------- Main -----------------------------------------------------------

def main() -> int:
    started = time.monotonic()
    _STARVED.clear()
    breaker = ThrottleBreaker()   # one per pass: every gTTS call of this pass goes through it
    # Manifest passes FIRST: the appning app reads these R2 manifests directly.
    # Each lists ONLY ids whose MP3 is confirmed in R2, so the car never 404s,
    # regardless of which Cloudflare colo the baker vs the car hit.
    # Jul 11 2026 — rotate the starting manifest each run so late-list apps
    # (tickerly, 9 manifests at the tail) get first claim on the gTTS/time
    # budget as often as the early ones; a fixed order starved them.
    # Sep 26 2026 (BK): the rotation is now only the tie-break; bake_fresh() orders each
    # round stalest manifest first and bakes one story per manifest per round.
    off = int(time.time() // 1800) % len(MANIFESTS)
    plans: list[dict] = []
    for m in MANIFESTS[off:] + MANIFESTS[:off]:
        # One manifest crashing must not kill the rest of the run (the Jul 2 2026
        # surrogate crash at circuitly_pt silently skipped every tickerly pass).
        try:
            p = plan_manifest(m)
        except Exception as e:
            print(f"[{m['manifest']}] manifest pass CRASHED: {e}; continuing with next app")
            traceback.print_exc()
            continue
        if p is not None:
            plans.append(p)
    try:
        bake_fresh(plans, breaker)
    except Exception as e:
        print(f"[fresh] round-robin CRASHED: {e}; writing the manifests with what is confirmed")
        traceback.print_exc()
    for p in plans:
        if p["dirty"] or not p["flushed"]:
            try:
                finalize_manifest(p)
            except Exception as e:
                print(f"[{p['name']}] manifest write CRASHED: {e}; continuing with next app")
                traceback.print_exc()
    report_starved(plans)
    # Soundica FM merged manifests right after the component manifests are written (before
    # the re-voice, which changes audio, not manifests). Pure R2 reads + one write per
    # language; never bakes.
    try:
        merge_soundicafm()
    except Exception as e:
        print(f"[soundicafm] merge pass CRASHED: {e}; component manifests unaffected")
        traceback.print_exc()
    try:
        revoice(plans, breaker)
    except Exception as e:
        print(f"[retext] re-voice CRASHED: {e}; manifests unaffected")
        traceback.print_exc()
    for p in plans:
        print(_done_line(p))
    total_baked = sum(p["baked"] for p in plans)
    total_skipped = sum(p["skipped"] for p in plans)
    # All apps are now manifest-driven (the appning app reads the R2 manifest, not
    # broad per-category baking). Skip the broad APPS loop in normal runs to avoid
    # wasted synth + gTTS rate-limit pressure; still runnable via FORCE_APP=<slug>/all.
    for app in APPS:
        if FORCE_APP in (app["slug"], "all"):
            b, s = bake_app(app, breaker)
            total_baked += b
            total_skipped += s
    elapsed = time.monotonic() - started
    print(f"\nSummary: {total_baked} baked, {total_skipped} already-cached, {elapsed:.1f}s, "
          f"gTTS 429s={breaker.total_429}, synth attempts={breaker.attempts}, "
          f"breaker={'OPEN' if breaker.tripped else 'closed'}")
    if _STARVED:
        print("STARVED manifests (fresh stories, none baked): " + ", ".join(f"{n} ({c} fresh)" for n, c in _STARVED))
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
