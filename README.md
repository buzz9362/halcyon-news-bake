# halcyon-news-bake

Pre-bakes Microsoft Edge-TTS MP3s for the 6 Halcyon Audio news apps so the
Android Automotive OS flavors play real audio URLs through ExoPlayer — no
system-TTS dependency, no MainActivity wake-up, no audio-focus workarounds.

## How it works

1. Hourly GitHub Actions cron fetches each app's Cloudflare Worker feed.
2. For each article, computes a stable MP3 key: `sha256(article.id)[:32].mp3`.
3. Uses Edge-TTS to synthesize the headline + summary in the app's primary
   language (en for KPop / Bollywood / Anime / Tropic; id for Hype; vi for Tinh).
4. Uploads to the `halcyon-news-tts` R2 bucket with a 30-day immutable cache.

The Android apps construct the public URL deterministically:
```
https://pub-fcb63a0a41b446ea825306ef86fc224f.r2.dev/<sha256(id)[:32]>.mp3
```
and hand it to ExoPlayer via `MediaItem.setUri(...)`.

## Required GitHub Secrets

- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_ENDPOINT_URL`  (e.g. `https://<account-id>.r2.cloudflarestorage.com`)

## Manual bake

`gh workflow run bake.yml`

## Local dev

```
pip install -r requirements.txt
R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=... R2_ENDPOINT_URL=... python bake.py
```
