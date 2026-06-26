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

Set up modal:

```bash
cd /Users/dtp03/Documents/ai-stream/ai-stream

python3 -m venv .venv
source .venv/bin/activate

pip install modal
modal setup
```
copy url modal to .env

after that run: 

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

Required avatar asset. Put the real file here manually; generated media outputs should not be committed:

```text
backend/avatars/model_01/idle_base.mp4
```

## Dynamic Local Playout

Dynamic playout is the local runtime layer for avatar video:

```text
start playout session
→ idle_base.mp4 loops into local HLS preview
→ enqueue talking MP4 or submit script text
→ runtime plays one talking segment
→ runtime returns automatically to idle
```

Out of scope here:

```text
Facebook Live creation
RTMP/RTMPS push
Meta webhook/comment ingestion
product recommendation
GPU rendering inside playout
```

Apply schema after pulling changes:

```bash
docker exec -i dtp-stream-postgres psql -U stream_user -d stream_db -f - < backend/db/schema.sql
```

Start runtime services:

```bash
docker compose up -d backend redis postgres avatar-worker dynamic-playout-worker
```

Create a playout session:

```bash
curl -X POST http://localhost:8100/api/playout-sessions \
  -H "Content-Type: application/json" \
  -d '{
    "avatar_id": "model_01",
    "live_session_id": "live_001",
    "output_mode": "local_preview"
  }'
```

Start idle loop runtime:

```bash
curl -X POST http://localhost:8100/api/playout-sessions/<SESSION_ID>/start
```

Enqueue an existing talking MP4 under `/app/media`:

```bash
curl -X POST http://localhost:8100/api/playout-sessions/<SESSION_ID>/segments \
  -H "Content-Type: application/json" \
  -d '{
    "source_video_path": "renders/avatar-renders/<JOB_ID>.mp4",
    "priority": "P1",
    "idempotency_key": "segment-001"
  }'
```

Submit text and let the avatar render pipeline create the talking MP4:

```bash
curl -X POST http://localhost:8100/api/playout-sessions/<SESSION_ID>/scripts \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Dạ mẫu A01 hiện còn màu đen size L ạ.",
    "priority": "P1",
    "idempotency_key": "script-001"
  }'
```

Check health:

```bash
curl http://localhost:8100/api/playout-sessions/<SESSION_ID>/health
```

Stop gracefully:

```bash
curl -X POST http://localhost:8100/api/playout-sessions/<SESSION_ID>/stop \
  -H "Content-Type: application/json" \
  -d '{"force": false}'
```

Local HLS output is written inside the backend media volume:

```text
/app/media/playout/live/<SESSION_ID>/index.m3u8
```

When `SERVE_LOCAL_MEDIA=true`, development preview URL:

```text
http://localhost:8100/media/playout/live/<SESSION_ID>/index.m3u8
```

Lifecycle events are published to Redis stream `playout.runtime.events`:

```json
{"event_type":"playout.session.starting","session_id":"..."}
{"event_type":"playout.session.idle","session_id":"..."}
{"event_type":"playout.segment.playing","session_id":"...","segment_id":"..."}
{"event_type":"playout.segment.completed","session_id":"...","segment_id":"..."}
{"event_type":"playout.session.stopped","session_id":"..."}
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
dynamic-playout-worker   dynamic local HLS playout runtime
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

The remaining integration work for the next phase is Facebook RTMPS publishing:

```text
local HLS playout
→ RTMPS output sink
→ Facebook Live stream key handling
→ dashboard preview/control
```

Known limitations:

- local preview writes HLS chunks; it does not push RTMP/RTMPS yet
- `force=true` requests immediate stop, but a running FFmpeg clip append may finish its current append first
- local MuseTalk runtime is still a placeholder unless an external/local runtime is wired in
