from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, loaded from environment variables / .env."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Database — set either DATABASE_URL, or the DB_* parts below.
    DATABASE_URL: str | None = None
    DB_DRIVER: str = "mysql+asyncmy"
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_NAME: str = "tender-fetching"
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

    @model_validator(mode="after")
    def assemble_database_url(self) -> "Settings":
        if self.DATABASE_URL:
            return self
        user = quote_plus(self.DB_USER)
        if self.DB_PASSWORD:
            auth = f"{user}:{quote_plus(self.DB_PASSWORD)}@"
        else:
            auth = f"{user}@"
        self.DATABASE_URL = (
            f"{self.DB_DRIVER}://{auth}{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
