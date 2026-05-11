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
# List of IPs or "ip:user:pass" strings
_DEVICES_RAW = os.getenv("DEVICES", "").split(",")
DEVICE_CONFIGS: list[dict[str, str]] = []

for entry in _DEVICES_RAW:
    parts = [p.strip() for p in entry.split(":") if p.strip()]
    if not parts:
        continue
    
    config = {"ip": parts[0]}
    if len(parts) >= 3:
        config["user"] = parts[1]
        config["pass"] = parts[2]
    else:
        # Fallback to global credentials
        config["user"] = os.getenv("DEVICE_USER", "")
        config["pass"] = os.getenv("DEVICE_PASS", "")
    
    DEVICE_CONFIGS.append(config)

DEVICE_IPS = [c["ip"] for c in DEVICE_CONFIGS]
DEVICE_USER: str = os.getenv("DEVICE_USER", "")
DEVICE_PASS: str = os.getenv("DEVICE_PASS", "")
HIKVISION_USE_HTTPS: bool = os.getenv("HIKVISION_USE_HTTPS", "true").lower() == "true"
HIKVISION_VERIFY_SSL: bool = os.getenv("HIKVISION_VERIFY_SSL", "false").lower() == "true"

# ── Device Friendly Names ────────────────────────────────────────────────────
# Map IP addresses to friendly names (e.g. 10.10.10.131:BIOMETRIC-01)
_DEVICE_NAMES_RAW = os.getenv("DEVICE_NAMES", "")
DEVICE_NAMES: dict[str, str] = {}
for entry in _DEVICE_NAMES_RAW.split(","):
    if ":" in entry:
        ip, name = entry.split(":", 1)
        DEVICE_NAMES[ip.strip()] = name.strip()

# ── Polling ──────────────────────────────────────────────────────────────────
POLL_INTERVAL: int = int(os.getenv("POLL_INTERVAL", "600"))         # seconds (10 mins)
DEDUP_WINDOW: int = int(os.getenv("DEDUP_WINDOW", "30"))            # seconds
FIRST_RUN_LOOKBACK_HOURS: int = int(os.getenv("FIRST_RUN_LOOKBACK_HOURS", "24"))

# ── Hikvision event filter ────────────────────────────────────────────────────
EVENT_MAJOR: int = int(os.getenv("EVENT_MAJOR", "5"))
EVENT_MINOR: int = int(os.getenv("EVENT_MINOR", "75"))

# ── Frappe HRMS ───────────────────────────────────────────────────────────────
HRMS_URL: str = _require("HRMS_URL").rstrip("/")
HRMS_API_KEY: str = _require("HRMS_API_KEY")
HRMS_API_SECRET: str = _require("HRMS_API_SECRET")

# ── Default Check-in Metadata ────────────────────────────────────────────────
DEFAULT_LOG_TYPE: str = os.getenv("DEFAULT_LOG_TYPE", "IN")
LATITUDE: str | None = os.getenv("LATITUDE")
LONGITUDE: str | None = os.getenv("LONGITUDE")

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

# ── Edge-to-server sync ───────────────────────────────────────────────────────
# Central server bind settings.
SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8080"))

# Comma-separated node_id:shared_secret values accepted by the central server.
# Example: SERVER_NODE_KEYS=pc-a:longSecretA,pc-b:longSecretB
_SERVER_NODE_KEYS_RAW = os.getenv("SERVER_NODE_KEYS", "")
SERVER_NODE_KEYS: dict[str, str] = {}
for entry in _SERVER_NODE_KEYS_RAW.split(","):
    if ":" in entry:
        node_id, secret = entry.split(":", 1)
        SERVER_NODE_KEYS[node_id.strip()] = secret.strip()

# Edge agent settings. Each PC uses its own node id and secret.
SYNC_SERVER_URL: str = os.getenv("SYNC_SERVER_URL", "").rstrip("/")
EDGE_NODE_ID: str = os.getenv("EDGE_NODE_ID", "")
EDGE_NODE_SECRET: str = os.getenv("EDGE_NODE_SECRET", "")
EDGE_BATCH_SIZE: int = int(os.getenv("EDGE_BATCH_SIZE", "200"))
EDGE_REQUEST_TIMEOUT: int = int(os.getenv("EDGE_REQUEST_TIMEOUT", "20"))

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE: str | None = os.getenv("LOG_FILE")   # None → stdout only
