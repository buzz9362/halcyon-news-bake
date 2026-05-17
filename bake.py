"""
halcyon-news-bake — pre-bake Edge-TTS MP3s for the 6 Halcyon Audio news apps
so the Android Automotive OS flavors play real audio URLs through ExoPlayer
(no system TTS dependency, no MainActivity wake-up, no audio-focus shims).

Architecture:
  1. For each app, fetch its Cloudflare Worker feed across all categories.
  2. For each article, compute a stable MP3 key = sha256(article.id)[:32] + ".mp3".
  3. If the key already exists in R2, skip. Otherwise, synthesize with Edge-TTS
     in the app's primary language and upload to R2 with a long Cache-Control.
  4. Public URL pattern: https://pub-<r2-hash>.r2.dev/<key>
     The app predicts the same URL deterministically and hands it to ExoPlayer.

Runs on GitHub Actions (free unlimited minutes on public repo). Cron schedule
fires every 15 minutes past the hour. Single bake run is bounded by the workflow
timeout-minutes setting (60).
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import sys
import time
import traceback
from io import BytesIO
from typing import Any

import boto3
import edge_tts
import requests
from botocore.exceptions import ClientError

# ---------- Configuration --------------------------------------------------

R2_ACCESS_KEY = os.environ["R2_ACCESS_KEY_ID"]
R2_SECRET_KEY = os.environ["R2_SECRET_ACCESS_KEY"]
R2_ENDPOINT = os.environ["R2_ENDPOINT_URL"]
R2_BUCKET = os.environ.get("R2_BUCKET", "halcyon-news-tts")

# Per-app primary language + Edge-TTS voice. Bake server speaks the article
# title + summary in this voice. The phone in-app path keeps using real-time
# system TTS for language switches; AAOS uses these pre-baked MP3s only.
APPS: list[dict[str, Any]] = [
    {
        "slug": "kpop",
        "feed_url": "https://kpop-today.buzz9362.workers.dev/feed",
        "voice": "en-US-AndrewNeural",
        "categories": ["latest", "trending", "charts"],
    },
    {
        "slug": "bollywood",
        "feed_url": "https://bollywood-today.buzz9362.workers.dev/feed",
        "voice": "en-US-AndrewNeural",
        "categories": ["latest", "trending", "charts"],
    },
    {
        "slug": "anime",
        "feed_url": "https://anime-brief.buzz9362.workers.dev/feed",
        "voice": "en-US-AndrewNeural",
        "categories": ["latest", "trending", "charts"],
    },
    {
        "slug": "tropic",
        "feed_url": "https://kpop-tropic.buzz9362.workers.dev/feed",
        "voice": "en-US-AndrewNeural",
        "categories": ["latest", "trending", "charts"],
    },
    {
        "slug": "hype",
        "feed_url": "https://hype-id.buzz9362.workers.dev/feed",
        "voice": "id-ID-ArdiNeural",
        "categories": ["latest", "trending", "charts"],
    },
    {
        "slug": "tinh",
        "feed_url": "https://tinh-tu.buzz9362.workers.dev/feed",
        "voice": "vi-VN-NamMinhNeural",
        "categories": ["latest", "trending", "charts"],
    },
]

MAX_TEXT_LEN = 4000      # Edge-TTS handles ~8k cleanly, cap at 4k for AAOS cadence
MIN_TEXT_LEN = 20        # below this, the article is just a stub — skip
FEED_TIMEOUT_S = 30
MAX_NEW_BAKES_PER_APP = 30   # cap so one app can't exhaust the GHA timeout

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
        body_parts.append(summary)
    body = " ".join(body_parts).strip()
    return body[:MAX_TEXT_LEN]

async def synth_to_mp3(text: str, voice: str) -> bytes:
    communicate = edge_tts.Communicate(text, voice)
    buf = BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    return buf.getvalue()

# ---------- Per-app bake loop ----------------------------------------------

def bake_app(app: dict[str, Any]) -> tuple[int, int]:
    """Returns (baked_count, skipped_count) for logging."""
    slug = app["slug"]
    voice = app["voice"]
    feed_url = app["feed_url"]
    baked = 0
    skipped = 0
    seen_ids: set[str] = set()

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
                if r2_exists(key):
                    skipped += 1
                    continue
            except Exception as e:
                print(f"[{slug}] head_object failed for {aid[:30]}: {e}")
                continue

            text = text_for(article)
            if len(text) < MIN_TEXT_LEN:
                print(f"[{slug}] skipping {aid[:30]}: text too short ({len(text)} chars)")
                continue

            try:
                mp3 = asyncio.run(synth_to_mp3(text, voice))
                upload(key, mp3)
                baked += 1
                print(f"[{slug}] baked {aid[:40]}... -> {key} ({len(mp3)} bytes)")
            except Exception as e:
                print(f"[{slug}] bake failed for {aid[:30]}: {e}")
                traceback.print_exc()
                continue

            if baked >= MAX_NEW_BAKES_PER_APP:
                print(f"[{slug}] hit per-app bake cap ({MAX_NEW_BAKES_PER_APP}); stopping")
                return baked, skipped

    return baked, skipped

# ---------- Main -----------------------------------------------------------

def main() -> int:
    started = time.monotonic()
    total_baked = 0
    total_skipped = 0
    for app in APPS:
        b, s = bake_app(app)
        total_baked += b
        total_skipped += s
    elapsed = time.monotonic() - started
    print(f"\nSummary: {total_baked} baked, {total_skipped} already-cached, {elapsed:.1f}s")
    return 0

if __name__ == "__main__":
    sys.exit(main())
