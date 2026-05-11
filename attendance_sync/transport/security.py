"""HMAC request signing for edge-to-server sync."""
import hashlib
import hmac
import time

SIGNATURE_HEADER = "X-Sync-Signature"
TIMESTAMP_HEADER = "X-Sync-Timestamp"
NODE_HEADER = "X-Sync-Node"
MAX_CLOCK_SKEW_SECONDS = 300


def sign_body(node_id: str, secret: str, timestamp: str, body: bytes) -> str:
    message = timestamp.encode("utf-8") + b"." + node_id.encode("utf-8") + b"." + body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def make_auth_headers(node_id: str, secret: str, body: bytes) -> dict[str, str]:
    timestamp = str(int(time.time()))
    return {
        NODE_HEADER: node_id,
        TIMESTAMP_HEADER: timestamp,
        SIGNATURE_HEADER: sign_body(node_id, secret, timestamp, body),
    }


def verify_auth_headers(
    *,
    node_id: str,
    timestamp: str,
    signature: str,
    body: bytes,
    allowed_secrets: dict[str, str],
) -> bool:
    secret = allowed_secrets.get(node_id)
    if not secret:
        return False

    try:
        request_time = int(timestamp)
    except ValueError:
        return False

    if abs(time.time() - request_time) > MAX_CLOCK_SKEW_SECONDS:
        return False

    expected = sign_body(node_id, secret, timestamp, body)
    return hmac.compare_digest(expected, signature)
