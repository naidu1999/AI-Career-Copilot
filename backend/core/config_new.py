from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Karna OS"
    APP_VERSION: str = "1.1.0"
    APP_ENV: str = "development"
    DATABASE_PATH: str = "data/karna_os.db"
    UPLOAD_DIR: str = "data/uploads"
    MAX_UPLOAD_MB: int = 10
    SUPABASE_URL: str = ""
    SUPABASE_PUBLISHABLE_KEY: str = ""
    SUPABASE_SECRET_KEY: str = ""
    SUPABASE_DATABASE_URL: str = ""
    AI_PROVIDER: str = "rules"
    AI_BASE_URL: str = "http://localhost:11434/v1"
    AI_API_KEY: str = "ollama"
    AI_MODEL: str = ""
    AI_TIMEOUT_SECONDS: int = 60
    AI_ROUTING_PRESET: str = "free_first"
    AI_ALLOW_PAID: bool = False
    AI_MAX_ATTEMPTS: int = 4
    AI_LOCAL_FALLBACK: bool = True
    AI_CIRCUIT_FAILURES: int = 3
    AI_CIRCUIT_COOLDOWN_SECONDS: int = 300
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = ""
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = ""
    GEMINI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GEMINI_MODEL: str = ""
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"
    OLLAMA_MODEL: str = ""
    ADZUNA_APP_ID: str = ""
    ADZUNA_APP_KEY: str = ""
    JOOBLE_API_KEY: str = ""
    USAJOBS_API_KEY: str = ""
    USAJOBS_EMAIL: str = ""
    SCRAPINGDOG_API_KEY: str = ""
    BACKUP_DIR: str = "data/backups"
    BACKUP_DAILY_RETENTION: int = 7
    BACKUP_WEEKLY_RETENTION: int = 4
    BACKUP_MONTHLY_RETENTION: int = 6
    SECONDARY_DATABASE_URL: str = ""
    CLOUD_SYNC_ENABLED: bool = False
    RATE_LIMIT_PER_MINUTE: int = 120
    INACTIVITY_DELETION_ENABLED: bool = False
    SCAN_ENABLED: bool = True
    SCAN_HOUR_LOCAL: int = 8
    DEFAULT_FRESHNESS_HOURS: int = 48
    QUALIFIED_SCORE: float = 70
    REVIEW_SCORE: float = 55
    TIMEZONE: str = "Asia/Kolkata"
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    PUBLIC_BASE_URL: str = ""
    TRUST_PROXY_HEADERS: bool = False
    CRON_SECRET: str = ""
    DEPLOYMENT_MODE: str = "local"
    SESSION_COOKIE_NAME: str = "karna_session"
    REFRESH_COOKIE_NAME: str = "karna_refresh"
    SESSION_COOKIE_SECURE: bool = True
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def database_file(self) -> Path:
        return Path(self.DATABASE_PATH)

    @property
    def upload_path(self) -> Path:
        return Path(self.UPLOAD_DIR)


settings = Settings()

