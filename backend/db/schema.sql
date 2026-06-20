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

CREATE TABLE IF NOT EXISTS live_session_products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    live_session_id UUID NOT NULL REFERENCES live_sessions(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    product_variant_id UUID REFERENCES product_variants(id) ON DELETE SET NULL,
    display_order INTEGER NOT NULL DEFAULT 0,
    is_featured BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (live_session_id, product_id, product_variant_id)
);

CREATE TABLE IF NOT EXISTS live_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    live_session_id UUID REFERENCES live_sessions(id) ON DELETE SET NULL,
    external_comment_id TEXT,
    external_viewer_id_hash TEXT,
    viewer_name TEXT,
    message TEXT NOT NULL,
    normalized_message TEXT,
    intent TEXT,
    processing_status TEXT NOT NULL DEFAULT 'queued',
    ai_reply TEXT,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (live_session_id, external_comment_id)
);

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
    scheduled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

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
    lip_sync_model TEXT NOT NULL DEFAULT 'echomimic-v2',
    fallback_lip_sync_model TEXT NOT NULL DEFAULT 'musetalk-v1.5',
    motion_model TEXT NOT NULL DEFAULT 'echomimic-v2',
    gesture_model TEXT NOT NULL DEFAULT 'echomimic-v2',
    body_motion_model TEXT NOT NULL DEFAULT 'echomimic-v2',
    supports_hand_gesture BOOLEAN NOT NULL DEFAULT true,
    supports_body_motion BOOLEAN NOT NULL DEFAULT true,
    render_provider TEXT NOT NULL DEFAULT 'modal',
    gpu_profile TEXT NOT NULL DEFAULT 'l4',
    quality_preset TEXT NOT NULL DEFAULT 'upper_body_balanced',
    render_endpoint TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, name)
);

ALTER TABLE avatar_models ADD COLUMN IF NOT EXISTS animation_scope TEXT NOT NULL DEFAULT 'upper_body';
ALTER TABLE avatar_models ADD COLUMN IF NOT EXISTS fallback_lip_sync_model TEXT NOT NULL DEFAULT 'musetalk-v1.5';
ALTER TABLE avatar_models ADD COLUMN IF NOT EXISTS gesture_model TEXT NOT NULL DEFAULT 'echomimic-v2';
ALTER TABLE avatar_models ADD COLUMN IF NOT EXISTS body_motion_model TEXT NOT NULL DEFAULT 'echomimic-v2';
ALTER TABLE avatar_models ADD COLUMN IF NOT EXISTS supports_hand_gesture BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE avatar_models ADD COLUMN IF NOT EXISTS supports_body_motion BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE avatar_models ALTER COLUMN animation_scope SET DEFAULT 'upper_body';
ALTER TABLE avatar_models ALTER COLUMN lip_sync_model SET DEFAULT 'echomimic-v2';
ALTER TABLE avatar_models ALTER COLUMN fallback_lip_sync_model SET DEFAULT 'musetalk-v1.5';
ALTER TABLE avatar_models ALTER COLUMN motion_model SET DEFAULT 'echomimic-v2';
ALTER TABLE avatar_models ALTER COLUMN gesture_model SET DEFAULT 'echomimic-v2';
ALTER TABLE avatar_models ALTER COLUMN body_motion_model SET DEFAULT 'echomimic-v2';
ALTER TABLE avatar_models ALTER COLUMN supports_hand_gesture SET DEFAULT true;
ALTER TABLE avatar_models ALTER COLUMN supports_body_motion SET DEFAULT true;
ALTER TABLE avatar_models ALTER COLUMN gpu_profile SET DEFAULT 'l4';
ALTER TABLE avatar_models ALTER COLUMN quality_preset SET DEFAULT 'upper_body_balanced';

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

CREATE TABLE IF NOT EXISTS media_render_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    live_session_id UUID REFERENCES live_sessions(id) ON DELETE SET NULL,
    live_comment_id UUID REFERENCES live_comments(id) ON DELETE SET NULL,
    render_profile_id UUID REFERENCES render_profiles(id) ON DELETE SET NULL,
    input_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    priority TEXT NOT NULL DEFAULT 'P3',
    audio_url TEXT,
    video_url TEXT,
    error_message TEXT,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_products_tenant_source ON products(tenant_id, source);
CREATE INDEX IF NOT EXISTS idx_products_external_product_id ON products(external_product_id);
CREATE INDEX IF NOT EXISTS idx_pancake_shops_tenant_shop ON pancake_shops(tenant_id, shop_id);
CREATE INDEX IF NOT EXISTS idx_variants_external_variation_id ON product_variants(external_variation_id);
CREATE INDEX IF NOT EXISTS idx_live_sessions_status ON live_sessions(status);
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
    id, tenant_id, name, animation_scope, lip_sync_model, fallback_lip_sync_model,
    motion_model, gesture_model, body_motion_model, supports_hand_gesture,
    supports_body_motion, render_provider, gpu_profile, quality_preset
)
VALUES (
    '00000000-0000-0000-0000-000000000601',
    '00000000-0000-0000-0000-000000000001',
    'default-upper-body-streamer',
    'upper_body',
    'echomimic-v2',
    'musetalk-v1.5',
    'echomimic-v2',
    'echomimic-v2',
    'echomimic-v2',
    true,
    true,
    'modal',
    'l4',
    'upper_body_balanced'
)
ON CONFLICT (id) DO UPDATE
SET name = EXCLUDED.name,
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

INSERT INTO render_profiles (
    id, tenant_id, name, ai_model_profile_id, avatar_model_id,
    target_width, target_height, target_fps, video_bitrate_kbps,
    audio_bitrate_kbps, segment_seconds, max_render_seconds, stream_strategy
)
VALUES (
    '00000000-0000-0000-0000-000000000701',
    '00000000-0000-0000-0000-000000000001',
    'default-balanced-modal',
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
SET ai_model_profile_id = EXCLUDED.ai_model_profile_id,
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
