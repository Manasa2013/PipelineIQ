"""
PipelineIQ Configuration Module.

Loads environment variables and provides typed configuration
for the entire application.
"""

import os
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ── App ──────────────────────────────────────────────────────────
    APP_NAME: str = "PipelineIQ"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ── Server ────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # ── CORS ──────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ]

    # ── Database (SQLite) ─────────────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./pipelineiq.db"
    DATABASE_ECHO: bool = False

    # ── OpenRouter ────────────────────────────────────────────────────
    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL: str = "mistralai/mistral-7b-instruct:free"
    OPENROUTER_MAX_TOKENS: int = 1024
    OPENROUTER_TEMPERATURE: float = 0.7

    # ── Email ────────────────────────────────────────────────────────────
    EMAIL_PROVIDER: str = "simulated"  # "simulated" | "smtp" | "sendgrid" | "gmail"

    # ── LangChain / LangGraph ─────────────────────────────────────────
    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_API_KEY: Optional[str] = None
    LANGCHAIN_PROJECT: str = "pipelineiq"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    """Return a cached singleton of the application settings."""
    return Settings()