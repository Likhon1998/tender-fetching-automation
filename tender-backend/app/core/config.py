from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, loaded from environment variables / .env."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Database
    DATABASE_URL: str
    DB_DISABLE_PREPARED_STATEMENTS: bool = False

    # JWT
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # App
    APP_NAME: str = "Tender Automation API"
    ENVIRONMENT: str = "development"
    CORS_ORIGINS: str = "http://localhost:3000"

    # Firecrawl scraping
    FIRECRAWL_API_KEY: str = ""
    FIRECRAWL_URL: str = "https://api.firecrawl.dev/v1/scrape"
    FIRECRAWL_WAIT_FOR_MS: int = 5000
    FIRECRAWL_TIMEOUT_MS: int = 120_000
    FIRECRAWL_MAX_RETRIES: int = 3
    FIRECRAWL_MAX_CONCURRENT: int = 3
    FIRECRAWL_DELAY_SECONDS: float = 1.0

    # Scheduling. Times entered in the interface are wall-clock times in this
    # zone, so a schedule set for 08:00 stays at 08:00 year round.
    TIMEZONE: str = "Asia/Dhaka"
    SCHEDULER_ENABLED: bool = True

    # Ingestion
    MAX_PAGES_PER_SITE: int = 5
    TENDER_CUTOFF_YEAR: int = 2026


    # Login throttling
    LOGIN_RATE_LIMIT_ATTEMPTS: int = 10
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 300

    # Admin seed
    ADMIN_USERNAME: str = "admin"
    ADMIN_EMAIL: str = "admin@example.com"
    ADMIN_FULL_NAME: str = "System Administrator"
    ADMIN_PASSWORD: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
