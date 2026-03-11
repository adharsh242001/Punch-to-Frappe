"""
Central configuration loaded from environment variables (.env file).
All values have sensible defaults; required values raise on missing.
"""
import json
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (two levels up from this file)
_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_ROOT / ".env")


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise EnvironmentError(f"Required environment variable '{name}' is not set.")
    return value


# ── Hikvision devices ────────────────────────────────────────────────────────
DEVICE_IPS: list[str] = [
    ip.strip()
    for ip in os.getenv("DEVICES", "").split(",")
    if ip.strip()
]
if not DEVICE_IPS:
    raise EnvironmentError("DEVICES must list at least one IP in .env")

DEVICE_USER: str = _require("DEVICE_USER")
DEVICE_PASS: str = _require("DEVICE_PASS")

# ── Polling ──────────────────────────────────────────────────────────────────
POLL_INTERVAL: int = int(os.getenv("POLL_INTERVAL", "10"))          # seconds
DEDUP_WINDOW: int = int(os.getenv("DEDUP_WINDOW", "30"))            # seconds

# ── Hikvision event filter ────────────────────────────────────────────────────
EVENT_MAJOR: int = int(os.getenv("EVENT_MAJOR", "5"))
EVENT_MINOR: int = int(os.getenv("EVENT_MINOR", "75"))

# ── Frappe HRMS ───────────────────────────────────────────────────────────────
HRMS_URL: str = _require("HRMS_URL").rstrip("/")
HRMS_API_KEY: str = _require("HRMS_API_KEY")
HRMS_API_SECRET: str = _require("HRMS_API_SECRET")

# ── Employee map ──────────────────────────────────────────────────────────────
_MAP_PATH = Path(os.getenv("EMPLOYEE_MAP", str(_ROOT / "employee_map.json")))

def load_employee_map() -> dict[str, str]:
    if not _MAP_PATH.exists():
        raise FileNotFoundError(f"employee_map.json not found at {_MAP_PATH}")
    with _MAP_PATH.open() as fh:
        return json.load(fh)

# ── Storage ───────────────────────────────────────────────────────────────────
STORE_PATH: Path = Path(os.getenv("STORE_PATH", str(_ROOT / "data" / "events.db")))
STORE_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── Retry queue ───────────────────────────────────────────────────────────────
RETRY_MAX_ATTEMPTS: int = int(os.getenv("RETRY_MAX_ATTEMPTS", "5"))
RETRY_BACKOFF_BASE: float = float(os.getenv("RETRY_BACKOFF_BASE", "2.0"))  # seconds

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE: str | None = os.getenv("LOG_FILE")   # None → stdout only
