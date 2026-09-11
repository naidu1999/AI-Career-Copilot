from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application settings
    APP_NAME: str = "Karna OS"
    VERSION: str = "0.1.0"

    # OpenRouter settings
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = ""

    # Supabase settings
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""

    # Qdrant settings
    QDRANT_URL: str = ""
    QDRANT_API_KEY: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()