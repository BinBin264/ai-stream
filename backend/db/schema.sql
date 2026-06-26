CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    external_product_id TEXT,
    source TEXT NOT NULL DEFAULT 'pancake',
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    display_id TEXT,
    custom_id TEXT,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    category TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, code)
);

CREATE TABLE IF NOT EXISTS pancake_shops (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    shop_id TEXT NOT NULL,
    shop_name TEXT,
    encrypted_api_key TEXT,
    sync_status TEXT NOT NULL DEFAULT 'not_synced',
    last_synced_at TIMESTAMPTZ,
    last_sync_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, shop_id)
);

CREATE TABLE IF NOT EXISTS product_variants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    external_variation_id TEXT,
    sku_code TEXT NOT NULL,
    display_id TEXT,
    custom_id TEXT,
    color TEXT NOT NULL DEFAULT '',
    size TEXT NOT NULL DEFAULT '',
    attributes_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    price_vnd INTEGER NOT NULL CHECK (price_vnd >= 0),
    compare_at_price_vnd INTEGER CHECK (compare_at_price_vnd IS NULL OR compare_at_price_vnd >= 0),
    barcode TEXT,
    image_url TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, sku_code, color, size)
);

CREATE TABLE IF NOT EXISTS inventory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    product_variant_id UUID NOT NULL REFERENCES product_variants(id) ON DELETE CASCADE,
    on_hand_quantity INTEGER NOT NULL DEFAULT 0 CHECK (on_hand_quantity >= 0),
    reserved_quantity INTEGER NOT NULL DEFAULT 0 CHECK (reserved_quantity >= 0),
    safety_stock_quantity INTEGER NOT NULL DEFAULT 0 CHECK (safety_stock_quantity >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, product_variant_id)
);

CREATE TABLE IF NOT EXISTS facebook_pages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    page_id TEXT NOT NULL,
    page_name TEXT NOT NULL,
    encrypted_page_access_token TEXT,
    webhook_status TEXT NOT NULL DEFAULT 'not_connected',
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, page_id)
);

CREATE TABLE IF NOT EXISTS live_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    facebook_page_id UUID REFERENCES facebook_pages(id) ON DELETE SET NULL,
    external_live_video_id TEXT,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    media_provider TEXT NOT NULL DEFAULT 'ffmpeg',
    settings_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE live_sessions ADD COLUMN IF NOT EXISTS current_product_id UUID REFERENCES products(id) ON DELETE SET NULL;
ALTER TABLE live_sessions ADD COLUMN IF NOT EXISTS current_segment_id UUID;
ALTER TABLE live_sessions ADD COLUMN IF NOT EXISTS segment_offset_ms INTEGER NOT NULL DEFAULT 0;
ALTER TABLE live_sessions ADD COLUMN IF NOT EXISTS previous_action TEXT;
ALTER TABLE live_sessions ADD COLUMN IF NOT EXISTS interrupted_by UUID;
ALTER TABLE live_sessions ADD COLUMN IF NOT EXISTS director_state_json JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS live_session_products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    live_session_id UUID NOT NULL REFERENCES live_sessions(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    product_variant_id UUID REFERENCES product_variants(id) ON DELETE SET NULL,
    display_order INTEGER NOT NULL DEFAULT 0,
    is_featured BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (live_session_id, product_id, product_variant_id)
);

ALTER TABLE live_session_products ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE TABLE IF NOT EXISTS live_script_segments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    live_session_id UUID NOT NULL REFERENCES live_sessions(id) ON DELETE CASCADE,
    live_session_product_id UUID REFERENCES live_session_products(id) ON DELETE CASCADE,
    product_id UUID REFERENCES products(id) ON DELETE SET NULL,
    segment_type TEXT NOT NULL,
    display_order INTEGER NOT NULL,
    speech_text TEXT NOT NULL,
    motion_code TEXT NOT NULL DEFAULT 'talk_calm',
    overlay_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    audio_url TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (live_session_id, display_order, segment_type, product_id)
);

CREATE TABLE IF NOT EXISTS live_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    live_session_id UUID REFERENCES live_sessions(id) ON DELETE SET NULL,
    facebook_page_id TEXT,
    external_comment_id TEXT,
    external_parent_comment_id TEXT,
    external_viewer_id_hash TEXT,
    viewer_name TEXT,
    message TEXT NOT NULL,
    normalized_message TEXT,
    intent TEXT,
    processing_status TEXT NOT NULL DEFAULT 'queued',
    priority INTEGER NOT NULL DEFAULT 0,
    ai_reply TEXT,
    raw_payload_reference TEXT,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (live_session_id, external_comment_id)
);

ALTER TABLE live_comments ADD COLUMN IF NOT EXISTS facebook_page_id TEXT;
ALTER TABLE live_comments ADD COLUMN IF NOT EXISTS external_parent_comment_id TEXT;
ALTER TABLE live_comments ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 0;
ALTER TABLE live_comments ADD COLUMN IF NOT EXISTS raw_payload_reference TEXT;

CREATE TABLE IF NOT EXISTS ai_response_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    live_session_id UUID REFERENCES live_sessions(id) ON DELETE SET NULL,
    live_comment_id UUID REFERENCES live_comments(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    prompt TEXT,
    response_text TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS speech_queue_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    live_session_id UUID REFERENCES live_sessions(id) ON DELETE SET NULL,
    live_comment_id UUID REFERENCES live_comments(id) ON DELETE SET NULL,
    text TEXT NOT NULL,
    voice TEXT NOT NULL DEFAULT 'default',
    priority TEXT NOT NULL DEFAULT 'P4',
    status TEXT NOT NULL DEFAULT 'queued',
    audio_url TEXT,
    error_message TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    scheduled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE speech_queue_items ADD COLUMN IF NOT EXISTS audio_url TEXT;
ALTER TABLE speech_queue_items ADD COLUMN IF NOT EXISTS error_message TEXT;
ALTER TABLE speech_queue_items ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE speech_queue_items ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;
ALTER TABLE speech_queue_items ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;
ALTER TABLE speech_queue_items ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE TABLE IF NOT EXISTS ai_model_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    llm_provider TEXT NOT NULL DEFAULT 'gemini',
    llm_model TEXT NOT NULL DEFAULT 'gemini-2.5-flash-lite',
    tts_provider TEXT NOT NULL DEFAULT 'elevenlabs',
    tts_model TEXT NOT NULL DEFAULT 'eleven_multilingual_v2',
    voice_name TEXT NOT NULL DEFAULT 'default',
    language TEXT NOT NULL DEFAULT 'vi',
    temperature NUMERIC(3,2) NOT NULL DEFAULT 0.60,
    max_tokens INTEGER NOT NULL DEFAULT 700,
    system_prompt TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, name)
);

CREATE TABLE IF NOT EXISTS avatar_models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    source_image_url TEXT,
    source_image_path TEXT,
    animation_scope TEXT NOT NULL DEFAULT 'upper_body',
    lip_sync_model TEXT NOT NULL DEFAULT 'musetalk',
    fallback_lip_sync_model TEXT NOT NULL DEFAULT 'musetalk',
    motion_model TEXT NOT NULL DEFAULT 'motion-pack',
    gesture_model TEXT NOT NULL DEFAULT 'motion-pack',
    body_motion_model TEXT NOT NULL DEFAULT 'motion-pack',
    supports_hand_gesture BOOLEAN NOT NULL DEFAULT true,
    supports_body_motion BOOLEAN NOT NULL DEFAULT true,
    render_provider TEXT NOT NULL DEFAULT 'local',
    gpu_profile TEXT NOT NULL DEFAULT 'external-runtime',
    quality_preset TEXT NOT NULL DEFAULT 'motion_pack_realtime',
    render_endpoint TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, name)
);

ALTER TABLE avatar_models ADD COLUMN IF NOT EXISTS animation_scope TEXT NOT NULL DEFAULT 'upper_body';
ALTER TABLE avatar_models ADD COLUMN IF NOT EXISTS fallback_lip_sync_model TEXT NOT NULL DEFAULT 'musetalk';
ALTER TABLE avatar_models ADD COLUMN IF NOT EXISTS gesture_model TEXT NOT NULL DEFAULT 'motion-pack';
ALTER TABLE avatar_models ADD COLUMN IF NOT EXISTS body_motion_model TEXT NOT NULL DEFAULT 'motion-pack';
ALTER TABLE avatar_models ADD COLUMN IF NOT EXISTS supports_hand_gesture BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE avatar_models ADD COLUMN IF NOT EXISTS supports_body_motion BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE avatar_models ALTER COLUMN animation_scope SET DEFAULT 'upper_body';
ALTER TABLE avatar_models ALTER COLUMN lip_sync_model SET DEFAULT 'musetalk';
ALTER TABLE avatar_models ALTER COLUMN fallback_lip_sync_model SET DEFAULT 'musetalk';
ALTER TABLE avatar_models ALTER COLUMN motion_model SET DEFAULT 'motion-pack';
ALTER TABLE avatar_models ALTER COLUMN gesture_model SET DEFAULT 'motion-pack';
ALTER TABLE avatar_models ALTER COLUMN body_motion_model SET DEFAULT 'motion-pack';
ALTER TABLE avatar_models ALTER COLUMN supports_hand_gesture SET DEFAULT true;
ALTER TABLE avatar_models ALTER COLUMN supports_body_motion SET DEFAULT true;
ALTER TABLE avatar_models ALTER COLUMN render_provider SET DEFAULT 'local';
ALTER TABLE avatar_models ALTER COLUMN gpu_profile SET DEFAULT 'external-runtime';
ALTER TABLE avatar_models ALTER COLUMN quality_preset SET DEFAULT 'motion_pack_realtime';

CREATE TABLE IF NOT EXISTS render_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    ai_model_profile_id UUID REFERENCES ai_model_profiles(id) ON DELETE SET NULL,
    avatar_model_id UUID REFERENCES avatar_models(id) ON DELETE SET NULL,
    target_width INTEGER NOT NULL DEFAULT 1280,
    target_height INTEGER NOT NULL DEFAULT 720,
    target_fps INTEGER NOT NULL DEFAULT 25,
    video_bitrate_kbps INTEGER NOT NULL DEFAULT 2500,
    audio_bitrate_kbps INTEGER NOT NULL DEFAULT 128,
    segment_seconds INTEGER NOT NULL DEFAULT 6,
    max_render_seconds INTEGER NOT NULL DEFAULT 120,
    stream_strategy TEXT NOT NULL DEFAULT 'segment_queue',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, name)
);

CREATE TABLE IF NOT EXISTS avatar_motion_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    avatar_model_id UUID NOT NULL REFERENCES avatar_models(id) ON DELETE CASCADE,
    motion_code TEXT NOT NULL,
    video_url TEXT NOT NULL,
    loopable BOOLEAN NOT NULL DEFAULT false,
    neutral_start BOOLEAN NOT NULL DEFAULT true,
    neutral_end BOOLEAN NOT NULL DEFAULT true,
    duration_ms INTEGER,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (avatar_model_id, motion_code)
);

CREATE TABLE IF NOT EXISTS media_render_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    live_session_id UUID REFERENCES live_sessions(id) ON DELETE SET NULL,
    live_comment_id UUID REFERENCES live_comments(id) ON DELETE SET NULL,
    render_profile_id UUID REFERENCES render_profiles(id) ON DELETE SET NULL,
    speech_queue_item_id UUID REFERENCES speech_queue_items(id) ON DELETE SET NULL,
    input_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    priority TEXT NOT NULL DEFAULT 'P3',
    audio_url TEXT,
    motion_code TEXT,
    overlay_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    video_url TEXT,
    error_message TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE media_render_jobs ADD COLUMN IF NOT EXISTS speech_queue_item_id UUID REFERENCES speech_queue_items(id) ON DELETE SET NULL;
ALTER TABLE media_render_jobs ADD COLUMN IF NOT EXISTS motion_code TEXT;
ALTER TABLE media_render_jobs ADD COLUMN IF NOT EXISTS overlay_json JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE media_render_jobs ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 0;


CREATE INDEX IF NOT EXISTS idx_products_tenant_source ON products(tenant_id, source);
CREATE INDEX IF NOT EXISTS idx_products_external_product_id ON products(external_product_id);
CREATE INDEX IF NOT EXISTS idx_pancake_shops_tenant_shop ON pancake_shops(tenant_id, shop_id);
CREATE INDEX IF NOT EXISTS idx_variants_external_variation_id ON product_variants(external_variation_id);
CREATE INDEX IF NOT EXISTS idx_live_sessions_status ON live_sessions(status);
CREATE INDEX IF NOT EXISTS idx_live_session_products_queue ON live_session_products(live_session_id, display_order);
CREATE INDEX IF NOT EXISTS idx_live_script_segments_queue ON live_script_segments(live_session_id, status, display_order);
CREATE INDEX IF NOT EXISTS idx_live_comments_status ON live_comments(processing_status);
CREATE INDEX IF NOT EXISTS idx_speech_queue_status ON speech_queue_items(status);
CREATE INDEX IF NOT EXISTS idx_media_render_jobs_status ON media_render_jobs(status, priority);
CREATE INDEX IF NOT EXISTS idx_render_profiles_tenant_status ON render_profiles(tenant_id, status);

INSERT INTO tenants (id, name, status)
VALUES ('00000000-0000-0000-0000-000000000001', 'Demo Store', 'active')
ON CONFLICT (id) DO NOTHING;

INSERT INTO ai_model_profiles (
    id, tenant_id, name, llm_provider, llm_model, tts_provider, tts_model,
    voice_name, language, temperature, max_tokens, system_prompt
)
VALUES (
    '00000000-0000-0000-0000-000000000501',
    '00000000-0000-0000-0000-000000000001',
    'default-vietnamese-live-sales',
    'gemini',
    'gemini-2.5-flash-lite',
    'elevenlabs',
    'eleven_multilingual_v2',
    'default',
    'vi',
    0.60,
    700,
    'Bạn là host livestream bán hàng tiếng Việt. Nói ngắn, tự nhiên, bám dữ liệu sản phẩm và không bịa giá/tồn kho.'
)
ON CONFLICT (tenant_id, name) DO NOTHING;

INSERT INTO avatar_models (
    id, tenant_id, name, source_image_path, animation_scope, lip_sync_model, fallback_lip_sync_model,
    motion_model, gesture_model, body_motion_model, supports_hand_gesture,
    supports_body_motion, render_provider, gpu_profile, quality_preset
)
VALUES (
    '00000000-0000-0000-0000-000000000601',
    '00000000-0000-0000-0000-000000000001',
    'default-motion-pack-streamer',
    '/app/model_images/model-green-background.jpg',
    'upper_body',
    'musetalk',
    'musetalk',
    'motion-pack',
    'motion-pack',
    'motion-pack',
    true,
    true,
    'local',
    'external-runtime',
    'motion_pack_realtime'
)
ON CONFLICT (id) DO UPDATE
SET name = EXCLUDED.name,
    source_image_path = EXCLUDED.source_image_path,
    animation_scope = EXCLUDED.animation_scope,
    lip_sync_model = EXCLUDED.lip_sync_model,
    fallback_lip_sync_model = EXCLUDED.fallback_lip_sync_model,
    motion_model = EXCLUDED.motion_model,
    gesture_model = EXCLUDED.gesture_model,
    body_motion_model = EXCLUDED.body_motion_model,
    supports_hand_gesture = EXCLUDED.supports_hand_gesture,
    supports_body_motion = EXCLUDED.supports_body_motion,
    render_provider = EXCLUDED.render_provider,
    gpu_profile = EXCLUDED.gpu_profile,
    quality_preset = EXCLUDED.quality_preset,
    updated_at = now();

INSERT INTO avatar_models (
    id, tenant_id, name, source_image_path, animation_scope, lip_sync_model, fallback_lip_sync_model,
    motion_model, gesture_model, body_motion_model, supports_hand_gesture,
    supports_body_motion, render_provider, gpu_profile, quality_preset
)
VALUES (
    '00000000-0000-0000-0000-000000000602',
    '00000000-0000-0000-0000-000000000001',
    'half-body-white-background',
    '/app/model_images/half-model-ai-white-backgorund.jpeg',
    'upper_body',
    'musetalk',
    'musetalk',
    'motion-pack',
    'motion-pack',
    'motion-pack',
    true,
    true,
    'local',
    'external-runtime',
    'motion_pack_realtime'
)
ON CONFLICT (id) DO UPDATE
SET name = EXCLUDED.name,
    source_image_path = EXCLUDED.source_image_path,
    animation_scope = EXCLUDED.animation_scope,
    lip_sync_model = EXCLUDED.lip_sync_model,
    fallback_lip_sync_model = EXCLUDED.fallback_lip_sync_model,
    motion_model = EXCLUDED.motion_model,
    gesture_model = EXCLUDED.gesture_model,
    body_motion_model = EXCLUDED.body_motion_model,
    supports_hand_gesture = EXCLUDED.supports_hand_gesture,
    supports_body_motion = EXCLUDED.supports_body_motion,
    render_provider = EXCLUDED.render_provider,
    gpu_profile = EXCLUDED.gpu_profile,
    quality_preset = EXCLUDED.quality_preset,
    updated_at = now();

INSERT INTO avatar_motion_assets (
    tenant_id, avatar_model_id, motion_code, video_url, loopable, neutral_start, neutral_end
)
VALUES
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000601', 'idle_center', '/app/media/motions/idle_center.mp4', true, true, true),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000601', 'talk_calm', '/app/media/motions/talk_calm.mp4', true, true, true),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000601', 'talk_happy', '/app/media/motions/talk_happy.mp4', true, true, true),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000601', 'talk_excited', '/app/media/motions/talk_excited.mp4', true, true, true),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000601', 'point_left', '/app/media/motions/point_left.mp4', false, true, true),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000601', 'point_right', '/app/media/motions/point_right.mp4', false, true, true),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000601', 'present_product', '/app/media/motions/present_product.mp4', false, true, true),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000601', 'wave', '/app/media/motions/wave.mp4', false, true, true),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000601', 'thank_customer', '/app/media/motions/thank_customer.mp4', false, true, true),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000601', 'order_confirmed', '/app/media/motions/order_confirmed.mp4', false, true, true)
ON CONFLICT (avatar_model_id, motion_code) DO NOTHING;

INSERT INTO render_profiles (
    id, tenant_id, name, ai_model_profile_id, avatar_model_id,
    target_width, target_height, target_fps, video_bitrate_kbps,
    audio_bitrate_kbps, segment_seconds, max_render_seconds, stream_strategy
)
VALUES (
    '00000000-0000-0000-0000-000000000701',
    '00000000-0000-0000-0000-000000000001',
    'default-local-motion-pack',
    '00000000-0000-0000-0000-000000000501',
    '00000000-0000-0000-0000-000000000601',
    1280,
    720,
    25,
    2500,
    128,
    6,
    120,
    'segment_queue'
)
ON CONFLICT (id) DO UPDATE
SET name = EXCLUDED.name,
    ai_model_profile_id = EXCLUDED.ai_model_profile_id,
    avatar_model_id = EXCLUDED.avatar_model_id,
    target_width = EXCLUDED.target_width,
    target_height = EXCLUDED.target_height,
    target_fps = EXCLUDED.target_fps,
    video_bitrate_kbps = EXCLUDED.video_bitrate_kbps,
    audio_bitrate_kbps = EXCLUDED.audio_bitrate_kbps,
    segment_seconds = EXCLUDED.segment_seconds,
    max_render_seconds = EXCLUDED.max_render_seconds,
    stream_strategy = EXCLUDED.stream_strategy,
    updated_at = now();

-- Phase 3: Automated Avatar Render Pipeline
CREATE TABLE IF NOT EXISTS avatar_render_jobs (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                UUID NOT NULL REFERENCES tenants(id),
    avatar_id                TEXT NOT NULL,
    input_text               TEXT NOT NULL,
    voice_id                 TEXT,
    language                 TEXT NOT NULL DEFAULT 'vi',
    status                   TEXT NOT NULL DEFAULT 'queued',
    audio_path               TEXT,
    audio_normalized_path    TEXT,
    video_path               TEXT,
    metadata_path            TEXT,
    quality_report_path      TEXT,
    audio_duration_seconds   DOUBLE PRECISION,
    render_duration_seconds  DOUBLE PRECISION,
    error_code               TEXT,
    error_message            TEXT,
    retry_count              INTEGER NOT NULL DEFAULT 0,
    live_session_id          UUID REFERENCES live_sessions(id),
    source_comment_id        UUID,
    runtime_provider         TEXT,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at               TIMESTAMPTZ,
    completed_at             TIMESTAMPTZ,
    failed_at                TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_avatar_render_jobs_status ON avatar_render_jobs(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_avatar_render_jobs_tenant ON avatar_render_jobs(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_avatar_render_jobs_live_session ON avatar_render_jobs(live_session_id) WHERE live_session_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS playout_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    live_session_id TEXT,
    avatar_id TEXT NOT NULL,
    idle_video_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'stopped',
    output_mode TEXT NOT NULL DEFAULT 'local_preview',
    output_path TEXT,
    active_segment_id UUID,
    started_at TIMESTAMPTZ,
    stopped_at TIMESTAMPTZ,
    last_heartbeat_at TIMESTAMPTZ,
    last_output_update_at TIMESTAMPTZ,
    runtime_owner_id TEXT,
    lease_expires_at TIMESTAMPTZ,
    restart_count INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_playout_sessions_status CHECK (
        status IN ('stopped', 'starting', 'idle', 'playing_talking', 'stopping', 'failed')
    ),
    CONSTRAINT chk_playout_sessions_output_mode CHECK (
        output_mode IN ('local_preview', 'file_output')
    )
);

ALTER TABLE playout_sessions ADD COLUMN IF NOT EXISTS last_output_update_at TIMESTAMPTZ;
ALTER TABLE playout_sessions ADD COLUMN IF NOT EXISTS runtime_owner_id TEXT;
ALTER TABLE playout_sessions ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;
ALTER TABLE playout_sessions ADD COLUMN IF NOT EXISTS restart_count INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS playout_segments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    playout_session_id UUID NOT NULL REFERENCES playout_sessions(id) ON DELETE CASCADE,
    avatar_render_job_id UUID REFERENCES avatar_render_jobs(id) ON DELETE SET NULL,
    source_video_path TEXT,
    segment_type TEXT NOT NULL DEFAULT 'talking',
    priority TEXT NOT NULL DEFAULT 'P2',
    status TEXT NOT NULL DEFAULT 'queued',
    queue_position INTEGER NOT NULL,
    idempotency_key TEXT,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    queued_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    error_code TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_playout_segments_type CHECK (segment_type IN ('talking')),
    CONSTRAINT chk_playout_segments_status CHECK (
        status IN ('queued', 'ready', 'playing', 'completed', 'cancelled', 'failed')
    ),
    CONSTRAINT chk_playout_segments_priority CHECK (priority IN ('P0', 'P1', 'P2', 'P3', 'P4'))
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_playout_sessions_active_segment'
    ) THEN
        ALTER TABLE playout_sessions
            ADD CONSTRAINT fk_playout_sessions_active_segment
            FOREIGN KEY (active_segment_id)
            REFERENCES playout_segments(id)
            ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_playout_sessions_tenant_status ON playout_sessions(tenant_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_playout_sessions_live_session ON playout_sessions(live_session_id) WHERE live_session_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_playout_sessions_recovery ON playout_sessions(status, lease_expires_at, restart_count);
CREATE INDEX IF NOT EXISTS idx_playout_segments_session_status ON playout_segments(playout_session_id, status);
CREATE INDEX IF NOT EXISTS idx_playout_segments_queue ON playout_segments(
    playout_session_id,
    status,
    priority,
    queue_position,
    created_at
);
CREATE INDEX IF NOT EXISTS idx_playout_segments_avatar_render_job ON playout_segments(avatar_render_job_id) WHERE avatar_render_job_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_playout_segments_idempotency
    ON playout_segments(playout_session_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;
