# Live Operations Runbook

## Start Local Demo

```bash
docker compose up -d postgres
docker exec -i dtp-stream-postgres psql -U stream_user -d stream_db -f - < backend/db/schema.sql
docker compose up -d redis backend frontend
```

Open `http://localhost:3100`.

## Test Video Without Facebook Graph API

Set manual RTMPS in `.env`:

```env
FACEBOOK_ENABLED=false
RTMPS_URL=rtmps://...
RTMPS_STREAM_KEY=...
```

Create a live session and click `Preview`. The backend will create
`/app/media/idle.mp4` automatically if it is missing.

## Test Facebook Graph API Live Creation

Set:

```env
FACEBOOK_ENABLED=true
META_GRAPH_API_VERSION=v23.0
META_PAGE_ID=
META_PAGE_ACCESS_TOKEN=
```

Then create a live session. If Meta returns a stream URL, FFmpeg will use that
stream target.

## Test Product Catalog Sync

```bash
curl -X POST http://localhost:8100/api/products/pancake/shops \
  -H 'content-type: application/json' \
  -d '{"shop_id":"<shop_id>","api_key":"<api_key>","shop_name":"Demo Shop"}'

curl -X POST http://localhost:8100/api/products/pancake/sync \
  -H 'content-type: application/json' \
  -d '{"pancake_shop_id":"<uuid-from-first-response>"}'

curl http://localhost:8100/api/products
```

## Test Avatar Render Profiles

```bash
curl http://localhost:8100/api/media/ai-profiles
curl http://localhost:8100/api/media/avatar-models
curl http://localhost:8100/api/media/render-profiles
```

Create a render job:

```bash
curl -X POST http://localhost:8100/api/media/render-jobs \
  -H 'content-type: application/json' \
  -d '{"input_text":"Dạ mẫu này đang có màu đỏ size M, chất cotton mềm mát ạ."}'
```

Without `MEDIA_RENDER_BASE_URL`, the job remains queued in Postgres. With a
Modal/local GPU endpoint configured, the backend posts to `/render`.

The default render profile is `upper_body`: EchoMimicV2 should generate
lip-sync plus hand/upper-body motion. MuseTalk is only a fallback lip-sync
model and should not be treated as the main streamer avatar engine.

## Emergency Controls

- Set `FACEBOOK_ENABLED=false` to stop Graph API live creation.
- Set `AI_SPEECH_ENABLED=false` to stop speech queueing.
- Clear `MEDIA_RENDER_BASE_URL` to stop submitting jobs to GPU inference.
- Stop FFmpeg for a session with `POST /api/live/{live_id}/stop`.
