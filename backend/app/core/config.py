from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_URL: str = "http://localhost:3100"
    API_PREFIX: str = "/api"
    SECRET_KEY: str = "change-me"

    DATABASE_URL: str = "postgresql+asyncpg://stream_user:stream_password@postgres:5432/stream_db"
    REDIS_URL: str = "redis://redis:6379/0"

    META_APP_ID: str = ""
    META_APP_SECRET: str = ""
    META_GRAPH_API_VERSION: str = "v23.0"
    META_REDIRECT_URI: str = "http://localhost:8100/api/facebook/oauth/callback"
    META_VERIFY_TOKEN: str = "change-me-verify-token"
    META_WEBHOOK_SECRET: str = ""
    META_PAGE_ID: str = ""
    META_PAGE_ACCESS_TOKEN: str = ""
    FACEBOOK_ENABLED: bool = False
    WEBHOOK_SIGNATURE_REQUIRED: bool = False

    PANCAKE_POS_BASE_URL: str = "https://pos.pages.fm/api/v1"


    PII_HASH_SALT: str = "change-me-local-salt"

    DEFAULT_RESERVATION_TTL_MINUTES: int = 10
    MAX_ORDER_QUANTITY_PER_ITEM: int = 10
    ORDER_HIGH_VALUE_REVIEW_THRESHOLD_VND: int = 3_000_000

    AI_SPEECH_ENABLED: bool = True
    AI_HUMAN_HANDOVER_CONFIDENCE_THRESHOLD: float = 0.75
    AI_AVATAR_BASE_URL: str = "http://host.docker.internal:8000"

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    GEMINI_ENABLED: bool = True

    MODAL_TTS_URL: str = ""
    MODAL_AVATAR_URL: str = ""
    MODAL_API_TOKEN: str = ""

    MEDIA_ENABLED: bool = True
    DEFAULT_RENDER_PROFILE_ID: str = "00000000-0000-0000-0000-000000000701"
    TTS_PROVIDER: str = "vixtts"
    VIXTTS_MODEL_DIR: str = "/app/models/vixtts"
    VIXTTS_SPEAKER_WAV: str = "/app/avatars/model_01/speaker_reference.wav"
    STREAM_COMMENTS: str = "stream:comments"
    STREAM_SPEECH: str = "stream:speech"
    REDIS_GROUP_COMMENTS: str = "comment-workers"
    REDIS_GROUP_SPEECH: str = "speech-workers"
    MEDIA_OUTPUT_DIR: str = "/app/media"
    SERVE_LOCAL_MEDIA: bool = True

    # Automated avatar render pipeline
    AVATAR_RENDER_STREAM: str = "avatar.render"
    AVATAR_FAILED_STREAM: str = "avatar.failed"
    PLAYOUT_QUEUE_STREAM: str = "playout.queue"
    PLAYOUT_SESSION_CONTROL_STREAM: str = "playout.session.control"
    PLAYOUT_SEGMENT_READY_STREAM: str = "playout.segment.ready"
    PLAYOUT_SEGMENT_FAILED_STREAM: str = "playout.segment.failed"
    PLAYOUT_RUNTIME_EVENTS_STREAM: str = "playout.runtime.events"
    PLAYOUT_RUNTIME_CONSUMER_GROUP: str = "dynamic-playout-workers"
    AVATAR_RENDER_CONSUMER_GROUP: str = "avatar-render-workers"
    AVATAR_RENDER_PROVIDER: str = "fake"   # fake | local
    AVATAR_RUNTIME_TIMEOUT_SECONDS: int = 1800
    AVATAR_RUNTIME_POLL_INTERVAL_SECONDS: int = 3
    AVATAR_RENDER_MAX_RETRIES: int = 1
    AVATAR_MAX_AUDIO_SECONDS: int = 30
    AVATAR_MAX_TEXT_LENGTH: int = 350
    AVATAR_MEDIA_ROOT: str = "media"

    # Local playout program assembly
    PLAYOUT_MEDIA_ROOT: str = "media/playout"
    PLAYOUT_MANIFEST_DIR: str = "media/playout/manifests"
    PLAYOUT_NORMALIZED_DIR: str = "media/playout/normalized"
    PLAYOUT_PROGRAM_DIR: str = "media/playout/programs"
    PLAYOUT_TARGET_WIDTH: int = 1080
    PLAYOUT_TARGET_HEIGHT: int = 1920
    PLAYOUT_TARGET_FPS: int = 25
    PLAYOUT_TARGET_VIDEO_CODEC: str = "libx264"
    PLAYOUT_TARGET_AUDIO_CODEC: str = "aac"
    PLAYOUT_TARGET_PIXEL_FORMAT: str = "yuv420p"
    PLAYOUT_TARGET_AUDIO_RATE: int = 48000
    PLAYOUT_TARGET_AUDIO_CHANNELS: int = 2
    PLAYOUT_DEFAULT_IDLE_LEAD_SECONDS: int = 8
    PLAYOUT_DEFAULT_IDLE_BETWEEN_SECONDS: int = 10
    PLAYOUT_DEFAULT_IDLE_TAIL_SECONDS: int = 10
    PLAYOUT_DEFAULT_TRANSITION: str = "cut"
    PLAYOUT_MAX_TARGET_DURATION_SECONDS: int = 180
    PLAYOUT_RUNTIME_ENABLED: bool = True
    PLAYOUT_RUNTIME_OUTPUT_MODE: str = "local_preview"
    PLAYOUT_VIDEO_CODEC: str = "libx264"
    PLAYOUT_AUDIO_CODEC: str = "aac"
    PLAYOUT_PIXEL_FORMAT: str = "yuv420p"
    PLAYOUT_AUDIO_SAMPLE_RATE: int = 48000
    PLAYOUT_AUDIO_CHANNELS: int = 2
    PLAYOUT_HLS_TIME_SECONDS: int = 2
    PLAYOUT_HLS_LIST_SIZE: int = 10
    PLAYOUT_HLS_DIRECTORY: str = "playout/live"
    PLAYOUT_IDLE_TRANSITION_POLICY: str = "next_loop_boundary"
    PLAYOUT_MAX_QUEUE_SIZE: int = 50
    PLAYOUT_MAX_RUNTIME_RESTARTS: int = 2
    PLAYOUT_RUNTIME_HEARTBEAT_SECONDS: int = 5
    PLAYOUT_SEGMENT_MAX_DURATION_SECONDS: int = 30

    RTMPS_URL: str = ""
    RTMPS_STREAM_KEY: str = ""
    IDLE_VIDEO_PATH: str = "/app/avatars/model_01/idle_base.mp4"

    LOG_LEVEL: str = "info"
    OTEL_ENABLED: bool = False

    def validate_runtime(self) -> None:
        if self.APP_ENV != "production":
            return
        missing: list[str] = []
        if self.SECRET_KEY == "change-me":
            missing.append("SECRET_KEY")
        if self.FACEBOOK_ENABLED:
            for key, value in {
                "META_APP_ID": self.META_APP_ID,
                "META_APP_SECRET": self.META_APP_SECRET,
                "META_VERIFY_TOKEN": self.META_VERIFY_TOKEN,
                "META_WEBHOOK_SECRET": self.META_WEBHOOK_SECRET,
            }.items():
                if not value:
                    missing.append(key)
        if self.PII_HASH_SALT == "change-me-local-salt":
            missing.append("PII_HASH_SALT")
        if missing:
            raise RuntimeError(f"Missing production configuration: {', '.join(sorted(set(missing)))}")


settings = Settings()
settings.validate_runtime()
