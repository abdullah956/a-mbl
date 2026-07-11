"""Runtime configuration.

Everything lives under one data directory (SQLite file, key files, encrypted
evidence). The directory is created on first use and must stay out of Git.
Tests point A_MBL_DATA_DIR at a temporary directory.
"""

import os
from pathlib import Path

APP_NAME = "a-mbl"
API_PREFIX = "/v1"

ACCESS_TOKEN_MINUTES = 15
REFRESH_TOKEN_DAYS = 7
GUARDIAN_CODE_HOURS = 24
CASE_RETENTION_DAYS = 30

MAX_TEXT_CHARS = 5_000
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_DIMENSION = 6_000

# Confidence policy (stored with the model version; see docs/MOBILE_APP_ROADMAP.md §6.3)
NEEDS_REVIEW_BELOW = 0.70
ALERT_CONFIDENCE_AT_LEAST = 0.80

MIN_PASSWORD_CHARS = 8


def data_dir() -> Path:
    root = Path(os.environ.get("A_MBL_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
    root.mkdir(parents=True, exist_ok=True)
    (root / "evidence").mkdir(exist_ok=True)
    return root


def db_path() -> Path:
    return data_dir() / "a_mbl.sqlite3"
