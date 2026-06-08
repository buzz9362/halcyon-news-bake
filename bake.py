"""
halcyon-news-bake — pre-bake MP3s for the 6 Halcyon Audio news apps so the
Android Automotive OS flavors play real audio URLs through ExoPlayer (no
system TTS dependency, no MainActivity wake-up, no audio-focus shims).

Uses gTTS (Google Translate TTS, free, no auth, works from any IP) — we
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
import os
import re
import sys
import time
import traceback
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
        "feed_url": "https://kpop-today.buzz9362.workers.dev/feed",
        "lang": "en",
        "tld": "us",
        "categories": ["latest", "trending", "charts"],
    },
    {
        "slug": "bollywood",
        "feed_url": "https://bollywood-today.buzz9362.workers.dev/feed",
        "lang": "en",
        "tld": "us",
        "categories": ["latest", "trending", "charts"],
    },
    {
        "slug": "anime",
        "feed_url": "https://anime-brief.buzz9362.workers.dev/feed",
        "lang": "en",
        "tld": "us",
        "categories": ["latest", "trending", "charts"],
    },
    {
        "slug": "tropic",
        "feed_url": "https://kpop-tropic.buzz9362.workers.dev/feed",
        "lang": "en",
        "tld": "us",
        "categories": ["latest", "trending", "charts"],
    },
    {
        "slug": "hype",
        "feed_url": "https://hype-id.buzz9362.workers.dev/feed",
        "lang": "id",
        "tld": "co.id",
        "categories": ["latest", "trending", "charts"],
    },
    {
        "slug": "tinh",
        "feed_url": "https://tinh-tu.buzz9362.workers.dev/feed",
        "lang": "vi",
        "tld": "com.vn",
        "categories": ["latest", "trending", "charts"],
    },
]

# Hindi pass — only baked on explicit FORCE_APP=bollywood_hi (so a scheduled run
# never bakes Hindi against a worker that doesn't serve /feed?lang=hi yet). gTTS hi.
HINDI_APPS: list[dict[str, Any]] = [
    {
        "slug": "bollywood",
        "feed_url": "https://bollywood-today.buzz9362.workers.dev/feed?lang=hi",
        "lang": "hi",
        "tld": "co.in",
        "phonetics_slug": "bollywood_hi",
    },
]

MAX_TEXT_LEN = 4000      # Edge-TTS handles ~8k cleanly, cap at 4k for AAOS cadence
FAIR_USE_SNIPPET = 350   # match the app's Article.kt snippet(maxChars=350) for
                         # ALL_RIGHTS_RESERVED sources — the baked audio must not
                         # reproduce more of a publisher's text than the app shows.
MIN_TEXT_LEN = 20        # below this, the article is just a stub — skip
FEED_TIMEOUT_S = 30
MAX_NEW_BAKES_PER_APP = 30   # cap so one app can't exhaust the GHA timeout

# Jun 9 2026 — per-app pronunciation tables (copied from each app's
# assets/phonetics_en.csv). gTTS ignores the in-app CSV, so apply the same
# respellings here before synthesis. Tuned for Google TTS English.
import re as _re
PHONETICS = {
    "bollywood": "phonetics/bollywood_en.csv",
    "bollywood_hi": "phonetics/bollywood_hi.csv",
}
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

def apply_phonetics(text: str, slug: str) -> str:
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

def text_for(article: dict) -> str:
    title = clean_text(article.get("title", ""))
    summary = clean_text(article.get("summary", ""))
    source = clean_text(article.get("source", ""))
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

def bake_app(app: dict[str, Any]) -> tuple[int, int]:
    """Returns (baked_count, skipped_count) for logging."""
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

        items = data.get("items", [])
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
            text = apply_phonetics(text, slug)
            if len(text) < MIN_TEXT_LEN:
                print(f"[{slug}] skipping {aid[:30]}: text too short ({len(text)} chars)")
                continue

            try:
                mp3 = synth_to_mp3(text, lang, tld)
                upload(key, mp3)
                baked += 1
                print(f"[{slug}] baked {aid[:40]}... -> {key} ({len(mp3)} bytes)")
            except Exception as e:
                print(f"[{slug}] bake failed for {aid[:30]}: {e}")
                traceback.print_exc()
                continue

            if not force and baked >= MAX_NEW_BAKES_PER_APP:
                print(f"[{slug}] hit per-app bake cap ({MAX_NEW_BAKES_PER_APP}); stopping")
                return baked, skipped

    return baked, skipped

# ---------- Hindi pass -----------------------------------------------------

def bake_hindi(app: dict[str, Any]) -> tuple[int, int]:
    """Bake the Hindi feed with gTTS hi. Always overwrites (small set, explicit
    trigger only) so a voice/source change propagates."""
    slug = app["slug"]
    baked = 0
    try:
        r = requests.get(app["feed_url"], timeout=FEED_TIMEOUT_S)
        r.raise_for_status()
        items = r.json().get("items", [])
    except Exception as e:
        print(f"[{slug}/hi] feed fetch failed: {e}")
        return 0, 0
    print(f"[{slug}/hi] feed has {len(items)} items")
    for article in items:
        aid = article.get("id")
        if not aid:
            continue
        # Amar Ujala gives clean Hindi title + summary, so read the full text like
        # the English path; phonetics_hi transliterates any Latin names to Devanagari.
        text = apply_phonetics(text_for(article), app["phonetics_slug"])
        if len(text) < MIN_TEXT_LEN:
            continue
        try:
            mp3 = synth_to_mp3(text, app["lang"], app["tld"])
            upload(article_key(aid), mp3)
            baked += 1
            print(f"[{slug}/hi] baked {aid[:40]} -> {article_key(aid)} ({len(mp3)} bytes)")
        except Exception as e:
            print(f"[{slug}/hi] bake failed for {aid[:30]}: {e}")
            traceback.print_exc()
    return baked, 0

# ---------- Main -----------------------------------------------------------

def main() -> int:
    started = time.monotonic()
    total_baked = 0
    total_skipped = 0
    for app in APPS:
        b, s = bake_app(app)
        total_baked += b
        total_skipped += s
    # Hindi pass only on explicit trigger (worker must serve /feed?lang=hi first).
    if FORCE_APP in ("bollywood_hi", "all_hi"):
        for app in HINDI_APPS:
            b, s = bake_hindi(app)
            total_baked += b
            total_skipped += s
    elapsed = time.monotonic() - started
    print(f"\nSummary: {total_baked} baked, {total_skipped} already-cached, {elapsed:.1f}s")
    return 0

if __name__ == "__main__":
    sys.exit(main())
