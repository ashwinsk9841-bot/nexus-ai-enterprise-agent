from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
import os
from pathlib import Path

# .env always lives next to the backend package (independent of CWD)
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(_BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "NEXUS Enterprise AI Intelligence & Operations Platform"
    APP_VERSION: str = "1.0.0"
    API_PREFIX: str = "/api"
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://nexus:nexus@localhost:5432/nexus",
    )
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Security
    SECRET_KEY: str = os.getenv(
        "SECRET_KEY", "nexus-dev-secret-change-in-production-2024"
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480")
    )

    # CORS — accepts comma-separated values or a JSON array
    CORS_ORIGINS: str = os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://localhost:8080,http://localhost:5173"
    )

    @property
    def cors_origin_list(self) -> list[str]:
        v = self.CORS_ORIGINS.strip()
        if v.startswith("["):
            try:
                import json

                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(o) for o in parsed]
            except ValueError:
                pass
        return [o.strip() for o in v.split(",") if o.strip()] or ["*"]

    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_EMBEDDING_MODEL: str = os.getenv(
        "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
    )

    # Additional AI providers (optional)
    NEXUS_AI_PROVIDER: str = os.getenv("NEXUS_AI_PROVIDER", "")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    LOCAL_AI_ENDPOINT: str = os.getenv("LOCAL_AI_ENDPOINT", "")
    LOCAL_AI_MODEL: str = os.getenv("LOCAL_AI_MODEL", "local-model")
    LOCAL_AI_API_KEY: str = os.getenv("LOCAL_AI_API_KEY", "")
    # Optional JSON map: agent key -> provider (e.g. {"finance":"openai","sales":"gemini"})
    NEXUS_AGENT_PROVIDER_MAP: str = os.getenv("NEXUS_AGENT_PROVIDER_MAP", "{}")
    # Optional: pin the provider used for the final NEXUS executive synthesis
    NEXUS_SYNTHESIS_PROVIDER: str = os.getenv("NEXUS_SYNTHESIS_PROVIDER", "")

    # Admin bootstrap
    NEXUS_ADMIN_EMAIL: str = os.getenv("NEXUS_ADMIN_EMAIL", "")
    NEXUS_ADMIN_PASSWORD_HASH: str = os.getenv("NEXUS_ADMIN_PASSWORD_HASH", "")

    # Accounts / security policy
    ALLOW_SIGNUP: bool = os.getenv("ALLOW_SIGNUP", "true").lower() == "true"
    LOGIN_MAX_ATTEMPTS: int = int(os.getenv("LOGIN_MAX_ATTEMPTS", "20"))
    LOGIN_WINDOW_MINUTES: int = int(os.getenv("LOGIN_WINDOW_MINUTES", "10"))
    SESSION_REMEMBER_DAYS: int = int(os.getenv("SESSION_REMEMBER_DAYS", "30"))
    APP_URL: str = os.getenv("APP_URL", "http://localhost:8000")

    # Demo mode
    DEMO_MODE: bool = os.getenv("DEMO_MODE", "true").lower() == "true"

    # Rate limiting
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    RATE_LIMIT_MAX_REQUESTS: int = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "100"))

    # Ops
    OPS_WINDOW_BACKEND_MINUTES: int = int(os.getenv("OPS_WINDOW_BACKEND_MINUTES", "60"))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()