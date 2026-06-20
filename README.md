# DTP AI Stream

AI livestream backend/frontend scaffold.

Current scope:

- sync product catalog from Pancake POS into Postgres
- create/manage a livestream session
- stream an idle video to RTMPS with FFmpeg
- receive Facebook webhook comments
- configure AI, TTS, avatar, GPU, and render quality profiles
- queue media render jobs for avatar speech and upper-body gesture inference

This source does not require a GPU for the basic stream test. GPU is only needed
for downstream avatar rendering, for example through Modal or a local GPU
service.

## Local Database

```bash
docker compose up -d postgres
docker exec -i dtp-stream-postgres psql -U stream_user -d stream_db -f - < backend/db/schema.sql
```

Connect from TablePlus/DBeaver:

```text
Host: 127.0.0.1
Port: 5434
Database: stream_db
User: stream_user
Password: stream_password
```

## Run App

```bash
docker compose up -d redis backend frontend
```

Open:

```text
http://localhost:3100
```

Backend health:

```bash
curl http://localhost:8100/health
```

## Product Sync From Pancake

1. Save Pancake shop credentials:

```bash
curl -X POST http://localhost:8100/api/products/pancake/shops \
  -H 'content-type: application/json' \
  -d '{"shop_id":"<pancake_shop_id>","api_key":"<pancake_api_key>","shop_name":"Demo Shop"}'
```

2. Copy the returned `shop.id`, then sync products:

```bash
curl -X POST http://localhost:8100/api/products/pancake/sync \
  -H 'content-type: application/json' \
  -d '{"pancake_shop_id":"<uuid-from-pancake_shops>"}'
```

3. Read catalog:

```bash
curl http://localhost:8100/api/products
```

## AI Avatar Quality Profiles

Quality is controlled by database profiles, not hard-coded constants:

```text
ai_model_profiles     LLM provider/model, TTS provider/model, voice, prompt
avatar_models         source image, animation scope, lip/gesture/body models, GPU profile
render_profiles       resolution, FPS, bitrate, segment length, strategy
media_render_jobs     text/audio/video render job lifecycle
```

Default profile:

```text
LLM: gemini / gemini-2.5-flash-lite
TTS: elevenlabs / eleven_multilingual_v2
Animation scope: upper_body
Lip-sync: echomimic-v2
Gesture/body motion: echomimic-v2
Fallback lip-sync only: musetalk-v1.5
GPU provider: modal
GPU class: l4
Video: 1280x720 @ 25fps, upper_body_balanced
```

This default is for a half-body livestream host that can move hands and upper
body while speaking. MuseTalk is kept only as a cheap lip-sync fallback; it is
not the core model for streamer-like motion.

Set render endpoint in `.env` when Modal or another GPU service is ready:

```env
MEDIA_RENDER_PROVIDER=modal
MEDIA_RENDER_BASE_URL=
MEDIA_RENDER_API_TOKEN=
DEFAULT_RENDER_PROFILE_ID=00000000-0000-0000-0000-000000000701
```

Create a render job:

```bash
curl -X POST http://localhost:8100/api/media/render-jobs \
  -H 'content-type: application/json' \
  -d '{"input_text":"Dạ mẫu này đang có màu đỏ size M, chất cotton mềm mát ạ."}'
```

## Stream Test Without Facebook Graph API

Set manual RTMPS values in `.env`:

```env
FACEBOOK_ENABLED=false
RTMPS_URL=rtmps://...
RTMPS_STREAM_KEY=...
```

Then create a live in the dashboard and click `Preview`. If
`IDLE_VIDEO_PATH=/app/media/idle.mp4` does not exist, the backend generates a
simple 720p idle clip with FFmpeg and loops it forever.

## Stream Test With Facebook Graph API

Set:

```env
FACEBOOK_ENABLED=true
META_GRAPH_API_VERSION=v23.0
META_PAGE_ID=
META_PAGE_ACCESS_TOKEN=
```

When a live session is created, `services/meta/client.py` calls Graph API
`/{page_id}/live_videos` and uses the returned stream URL for FFmpeg. The Page
token must have permissions for Page live video creation.

## Important Limits

- OAuth page connection is not implemented yet.
- Facebook comment reply API is not implemented yet.
- Page token encryption is a placeholder.
- Actual GPU inference needs `MEDIA_RENDER_BASE_URL`; without it, media jobs stay
  queued in Postgres.
- Order/cart/payment tables are intentionally not in the current DB scope.
