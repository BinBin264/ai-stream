# Meta Facebook Integration

Current code:

- `GET /api/facebook/webhook` validates the verify token.
- `POST /api/facebook/webhook` reads raw body, verifies
  `x-hub-signature-256` when `WEBHOOK_SIGNATURE_REQUIRED=true`, hashes payload,
  dedupes delivery, extracts comment events, and enqueues comments.
- `POST /api/facebook/dev-comment` is local-only scaffolding for testing without
  Meta credentials.
- When `FACEBOOK_ENABLED=true`, live creation calls Graph API:
  `POST /{page_id}/live_videos`, then uses returned `secure_stream_url` or
  `stream_url` for FFmpeg.
- When `FACEBOOK_ENABLED=false`, live streaming uses manual `RTMPS_URL` and
  `RTMPS_STREAM_KEY`.

Production work:

- Store Page access tokens encrypted at rest.
- Implement OAuth callback and managed Page connection.
- Implement Graph API comment reply adapter with retry rules.
- Keep Graph version from `META_GRAPH_API_VERSION`.
- Do not expose Page tokens, signed stream URLs, or webhook payloads to frontend.

## Required Meta Setup

```env
FACEBOOK_ENABLED=true
META_GRAPH_API_VERSION=v23.0
META_PAGE_ID=
META_PAGE_ACCESS_TOKEN=
```

The Page token needs permissions approved for creating Page live videos. Meta
Live Video API behavior can vary by app mode, permissions, and Graph API
version, so provider fields stay isolated in `services/meta/client.py`.
