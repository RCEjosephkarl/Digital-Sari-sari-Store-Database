"""Environment-driven configuration and canonical filesystem paths.

All tunables come from environment variables (loaded from a local ``.env`` if
present), so the same code runs identically on a laptop, in CI, or in the cloud.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

# Project root = two levels up from this file (src/sarisari/config.py -> repo root).
ROOT_DIR = Path(__file__).resolve().parents[2]

# Load .env from the project root if it exists (never overrides real env vars).
load_dotenv(ROOT_DIR / ".env")


def _env_date(name: str, default: str) -> date:
    return date.fromisoformat(os.getenv(name, default))


@dataclass(frozen=True)
class Settings:
    """Resolved project settings."""

    # --- paths ---------------------------------------------------------------
    root_dir: Path = ROOT_DIR
    csv_dir: Path = field(
        default_factory=lambda: ROOT_DIR / os.getenv("SARISARI_CSV_DIR", "data/csv")
    )
    schema_sql: Path = ROOT_DIR / "schema.sql"

    # --- database ------------------------------------------------------------
    # Empty string => fall back to a local pgserver instance (see db.py).
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "").strip())
    pgdata_dir: Path = field(
        default_factory=lambda: ROOT_DIR / os.getenv("PGDATA_DIR", ".pgdata")
    )

    # --- synthesis -----------------------------------------------------------
    target_rows: int = field(default_factory=lambda: int(os.getenv("SARISARI_TARGET_ROWS", "676767")))
    seed: int = field(default_factory=lambda: int(os.getenv("SARISARI_SEED", "20110628")))
    start_date: date = field(default_factory=lambda: _env_date("SARISARI_START_DATE", "2011-01-01"))
    end_date: date = field(default_factory=lambda: _env_date("SARISARI_END_DATE", "2026-06-28"))

    def ensure_dirs(self) -> None:
        self.csv_dir.mkdir(parents=True, exist_ok=True)


# A single shared instance most callers can import directly.
settings = Settings()
