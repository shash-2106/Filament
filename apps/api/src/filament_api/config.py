"""Application configuration management using Pydantic Settings."""

from functools import lru_cache
from typing import List, Literal
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for Filament API.

    Environment variables override default values.
    Production requirements are strictly validated at application startup.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # Core Environment
    ENVIRONMENT: Literal["development", "staging", "production", "test"] = Field(
        default="development",
        description="Deployment runtime environment",
    )
    DEBUG: bool = Field(default=False, description="Debug mode")
    LOG_LEVEL: str = Field(default="INFO", description="Standard logging level")

    # API Server Configuration
    API_HOST: str = Field(default="127.0.0.1", description="Host to bind API server")
    API_PORT: int = Field(default=8000, description="Port to bind API server")
    API_V1_PREFIX: str = Field(default="/api/v1", description="URL prefix for v1 API routes")
    PROJECT_NAME: str = Field(default="Filament API", description="Project display title")
    VERSION: str = Field(default="0.1.0", description="API semantic version")
    CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        description="Allowed CORS origin URLs for frontend clients",
    )

    # Database Configuration (PostgreSQL / Supabase via asyncpg)
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/filament_dev",
        description="Async SQLAlchemy database connection string",
    )
    DATABASE_POOL_SIZE: int = Field(default=10, ge=1, le=50, description="Connection pool size")
    DATABASE_MAX_OVERFLOW: int = Field(default=20, ge=0, le=50, description="Connection pool max overflow")
    DATABASE_POOL_TIMEOUT: int = Field(default=30, description="Connection pool timeout in seconds")
    DATABASE_ECHO: bool = Field(default=False, description="Log raw SQL statements")

    # Authentication & Security
    AUTH_SECRET_KEY: str = Field(
        default="replace_with_a_secure_random_key_for_local_dev",
        description="Secret key for signing internal tokens",
    )
    AUTH_TOKEN_EXPIRE_MINUTES: int = Field(default=60, description="Token expiration window")

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: object) -> List[str]:
        if isinstance(v, str):
            return [i.strip() for i in v.split(",") if i.strip()]
        if isinstance(v, list):
            return [str(i).strip() for i in v if str(i).strip()]
        return ["http://localhost:5173", "http://127.0.0.1:5173"]

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        """Enforces security boundaries for production deployments."""
        if self.ENVIRONMENT == "production":
            if self.AUTH_SECRET_KEY == "replace_with_a_secure_random_key_for_local_dev":
                raise ValueError("AUTH_SECRET_KEY must be changed from default placeholder in production.")
            if "localhost" in self.DATABASE_URL or "filament_dev" in self.DATABASE_URL:
                raise ValueError("Production DATABASE_URL cannot reference local dev database.")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retrieve cached application settings instance."""
    return Settings()

