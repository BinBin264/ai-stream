# DTP AI Stream

AI livestream backend/frontend for Facebook Live commerce.

The phase test folders have been removed from the source tree. The repository is now oriented around the runtime app:

```text
backend/
├── app/          FastAPI app, services, workers
├── avatars/      production avatar assets, e.g. model_01
├── db/           Postgres schema
├── Dockerfile
└── requirements.txt
```

Generated media should not be committed. In Docker it is written to the `media_data` volume mounted at `/app/media`.

## Run

```bash
cp .env.example .env
docker compose up -d postgres redis backend frontend
```

Open:

```text
Frontend: http://localhost:3100
Backend:  http://localhost:8100
Health:   http://localhost:8100/health
```

Apply the database schema:

```bash
docker exec -i dtp-stream-postgres psql -U stream_user -d stream_db -f - < backend/db/schema.sql
```

## Live Runtime Shape

Current live flow:

```text
Create live
→ start broadcaster
→ FFmpeg loops IDLE_VIDEO_PATH to RTMPS
→ Facebook webhook receives comments
→ comments enter Redis queue
→ workers process AI/speech/avatar jobs
→ completed avatar video is published to playout.queue
```

Default idle video:

```env
IDLE_VIDEO_PATH=/app/avatars/model_01/idle_base.mp4
```

Required avatar asset:

```text
backend/avatars/model_01/idle_base.mp4
```

## Workers

Run the full stack:

```bash
docker compose up -d
```

Relevant services:

```text
comment-worker   Facebook/comment queue processing
speech-worker    TTS queue processing
avatar-worker    avatar render queue processing
playout-worker   playout queue consumer
```

## Facebook Live

For manual RTMPS:

```env
FACEBOOK_ENABLED=false
RTMPS_URL=rtmps://...
RTMPS_STREAM_KEY=...
```

For Facebook Graph API:

```env
FACEBOOK_ENABLED=true
META_GRAPH_API_VERSION=v23.0
META_PAGE_ID=
META_PAGE_ACCESS_TOKEN=
META_VERIFY_TOKEN=
META_WEBHOOK_SECRET=
```

Start a live session from the frontend or API, then call start/go-live through the app.

## Product Sync

Save Pancake credentials:

```bash
curl -X POST http://localhost:8100/api/products/pancake/shops \
  -H 'content-type: application/json' \
  -d '{"shop_id":"<pancake_shop_id>","api_key":"<pancake_api_key>","shop_name":"Demo Shop"}'
```

Sync products:

```bash
curl -X POST http://localhost:8100/api/products/pancake/sync \
  -H 'content-type: application/json' \
  -d '{"pancake_shop_id":"<uuid-from-pancake_shops>"}'
```

## Next Runtime Work

The remaining integration work is live playout runtime:

```text
idle loop running
→ receive completed avatar talking segment
→ queue by priority
→ insert talking segment into live output
→ return to idle loop
```

Current `playout-worker` still needs to be upgraded from queue acknowledgement to real playout control. The old phase validation folders are intentionally removed.
