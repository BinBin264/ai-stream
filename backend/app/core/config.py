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

    OPENAI_API_KEY: str = ""
    OPENAI_COMMENT_MODEL: str = ""
    OPENAI_STRATEGY_MODEL: str = ""
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_MODERATION_MODEL: str = ""
    OPENAI_TTS_MODEL: str = ""
    OPENAI_STORE_RESPONSES: bool = False

    TOKEN_ENCRYPTION_KEY: str = ""
    PII_HASH_SALT: str = "change-me-local-salt"

    DEFAULT_RESERVATION_TTL_MINUTES: int = 10
    MAX_ORDER_QUANTITY_PER_ITEM: int = 10
    ORDER_HIGH_VALUE_REVIEW_THRESHOLD_VND: int = 3_000_000
    LOW_STOCK_THRESHOLD: int = 3

    AI_ENABLED: bool = True
    AI_AUTO_REPLY_ENABLED: bool = False
    AI_SPEECH_ENABLED: bool = True
    AI_HUMAN_HANDOVER_CONFIDENCE_THRESHOLD: float = 0.75
    AI_MAX_REPLY_LENGTH: int = 300
    AI_AVATAR_BASE_URL: str = "http://host.docker.internal:8000"
    AI_AVATAR_API_TOKEN: str = ""

    MEDIA_ENABLED: bool = True
    MEDIA_PROVIDER: str = "ffmpeg"
    MEDIA_RENDER_PROVIDER: str = "local"
    MEDIA_RENDER_BASE_URL: str = ""
    MEDIA_RENDER_API_TOKEN: str = ""
    DEFAULT_RENDER_PROFILE_ID: str = "00000000-0000-0000-0000-000000000701"
    TTS_PROVIDER: str = "elevenlabs"
    ELEVENLABS_API_KEY: str = ""
    ELEVENLABS_VOICE_ID: str = ""
    ELEVENLABS_MODEL_ID: str = "eleven_multilingual_v2"
    ELEVENLABS_OUTPUT_FORMAT: str = "mp3_44100_128"
    AVATAR_RUNTIME_PROVIDER: str = "musetalk"
    AVATAR_RUNTIME_BASE_URL: str = ""
    AVATAR_RUNTIME_API_TOKEN: str = ""
    STREAM_COMMENTS: str = "stream:comments"
    STREAM_SPEECH: str = "stream:speech"
    STREAM_AVATAR: str = "stream:avatar"
    STREAM_PLAYOUT: str = "stream:playout"
    REDIS_GROUP_COMMENTS: str = "comment-workers"
    REDIS_GROUP_SPEECH: str = "speech-workers"
    REDIS_GROUP_AVATAR: str = "avatar-workers"
    REDIS_GROUP_PLAYOUT: str = "playout-workers"
    MEDIA_OUTPUT_DIR: str = "/app/media"
    RTMP_OUTPUT_ENABLED: bool = False
    RTMPS_URL: str = ""
    RTMPS_STREAM_KEY: str = ""
    IDLE_VIDEO_PATH: str = "/app/media/idle.mp4"

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
        if self.AI_ENABLED and self.OPENAI_COMMENT_MODEL and not self.OPENAI_API_KEY:
            missing.append("OPENAI_API_KEY")
        if not self.TOKEN_ENCRYPTION_KEY:
            missing.append("TOKEN_ENCRYPTION_KEY")
        if self.PII_HASH_SALT == "change-me-local-salt":
            missing.append("PII_HASH_SALT")
        if missing:
            raise RuntimeError(f"Missing production configuration: {', '.join(sorted(set(missing)))}")


settings = Settings()
settings.validate_runtime()
