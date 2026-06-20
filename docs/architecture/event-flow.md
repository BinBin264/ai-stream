# Event Flow

## Product Catalog Sync

```text
pancake_shops credentials
-> Pancake POS /shops/{shop_id}/products/variations
-> products
-> product_variants
-> inventory
```

Product sync is independent from Facebook live startup. Live sessions read the
synced catalog from Postgres.

## Live Startup

```text
create live session
-> if FACEBOOK_ENABLED=true: Graph API /{page_id}/live_videos
-> else: use manual RTMPS_URL and RTMPS_STREAM_KEY
-> start FFmpeg broadcaster
-> generate idle test video if missing
-> stream to RTMPS
```

## Webhook Thread

Webhook handlers must stay fast:

```text
raw body -> signature check -> parse JSON -> hash/dedupe
-> extract comment event -> enqueue -> return 200
```

The webhook thread must not call:

- OpenAI
- Facebook reply
- FFmpeg/avatar rendering
- any long-running media job

## Media Boundary

FFmpeg idle streaming is CPU-only. GPU is only needed when replacing the idle
video with generated avatar video.

## Avatar Render Job

```text
LLM/script text
-> ai_model_profiles decides LLM/TTS/voice
-> avatar_models decides source image, animation scope, lip/gesture/body models, GPU class
-> render_profiles decides resolution/FPS/bitrate/segment length
-> media_render_jobs queued
-> optional MEDIA_RENDER_BASE_URL /render
-> output video_url
-> future FFmpeg segment switcher
```

Recommended baseline:

```text
LLM: Gemini Flash Lite for short Vietnamese host script
TTS: ElevenLabs multilingual voice
Animation scope: upper_body
Lip-sync / gesture / body motion: EchoMimicV2
Fallback lip-sync only: MuseTalk v1.5
GPU: Modal L4 baseline, A10G for better throughput, T4 only for cheap tests
Output: 720p 25fps upper_body_balanced preset
```
