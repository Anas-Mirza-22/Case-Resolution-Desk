"""Environment-based configuration. Single place for env access."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from . import constants as C


@dataclass(frozen=True)
class Settings:
    groq_api_key: str | None
    groq_model: str
    groq_timeout_seconds: float
    policies_dir: Path
    db_path: Path


def load_settings() -> Settings:
    """Load settings from environment, applying safe defaults."""
    load_dotenv()

    policies_dir = Path(os.getenv("POLICIES_DIR", str(C.DEFAULT_POLICIES_DIR)))
    db_path = Path(os.getenv("DB_PATH", str(C.DEFAULT_DB_PATH)))

    try:
        timeout = float(os.getenv("GROQ_TIMEOUT_SECONDS", "20"))
    except ValueError:
        timeout = 20.0

    return Settings(
        groq_api_key=os.getenv("GROQ_API_KEY") or None,
        groq_model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
        groq_timeout_seconds=timeout,
        policies_dir=policies_dir,
        db_path=db_path,
    )