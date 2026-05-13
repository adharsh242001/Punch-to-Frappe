"""Minimal .env reader/writer that preserves comments and ordering."""
from pathlib import Path


def read_env(path: Path) -> dict[str, str]:
    """Return key/value pairs from a .env file. Missing file = empty dict."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = _strip_quotes(value.strip())
    return values


def update_env(path: Path, updates: dict[str, str]) -> None:
    """
    Write *updates* into *path*, preserving existing comments and ordering.
    Keys not already present are appended at the end.
    """
    existing_lines: list[str] = []
    if path.exists():
        existing_lines = path.read_text(encoding="utf-8").splitlines()

    seen: set[str] = set()
    new_lines: list[str] = []

    for raw_line in existing_lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(raw_line)
            continue
        key, _, _old_value = stripped.partition("=")
        key = key.strip()
        if key in updates:
            new_lines.append(f"{key}={_quote_if_needed(updates[key])}")
            seen.add(key)
        else:
            new_lines.append(raw_line)

    for key, value in updates.items():
        if key in seen:
            continue
        new_lines.append(f"{key}={_quote_if_needed(value)}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _quote_if_needed(value: str) -> str:
    if value == "" or any(ch in value for ch in (" ", "#", "\t")):
        return f'"{value}"'
    return value
