"""Read/write the ``.source`` metadata file next to vendored items.

The file is plain text, one ``key: value`` per line, with required keys
written in a fixed order:

    vendor: ...
    origin: ...
    tool: ...
    fetched: YYYY-MM-DD
    license: ...

``license`` is written as ``unknown`` if the caller passes ``None`` or
an empty string.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ai_dotfiles.core.errors import ConfigError
from ai_dotfiles.vendors.base import SourceMeta

SOURCE_FILENAME = ".source"

_REQUIRED_KEYS: tuple[str, ...] = ("vendor", "origin", "tool", "fetched", "license")


def _today_utc_iso() -> str:
    return datetime.now(tz=timezone.utc).date().isoformat()


def write(
    target: Path,
    *,
    vendor: str,
    origin: str,
    tool: str,
    license: str | None,
) -> None:
    """Write a ``.source`` file inside ``target`` directory.

    Args:
        target: Directory of the vendored item (e.g. ``catalog/skills/foo/``).
            Must already exist.
        vendor: Vendor plugin name (e.g. ``"github"``).
        origin: Origin identifier (e.g. ``"github:owner/repo/subpath"``).
        tool: Tool used to fetch (typically ``"ai-dotfiles vendor"``).
        license: SPDX id or similar; ``None`` / ``""`` becomes ``"unknown"``.

    Raises:
        ValueError: If any required string argument is empty.
    """
    if not vendor:
        raise ValueError("vendor must be a non-empty string")
    if not origin:
        raise ValueError("origin must be a non-empty string")
    if not tool:
        raise ValueError("tool must be a non-empty string")

    normalized_license = license if license else "unknown"

    lines = [
        f"vendor: {vendor}",
        f"origin: {origin}",
        f"tool: {tool}",
        f"fetched: {_today_utc_iso()}",
        f"license: {normalized_license}",
    ]
    content = "\n".join(lines) + "\n"
    (target / SOURCE_FILENAME).write_text(content, encoding="utf-8")


def read(target: Path) -> SourceMeta | None:
    """Read a ``.source`` file from ``target`` directory.

    Args:
        target: Directory that may contain a ``.source`` file.

    Returns:
        Parsed :class:`SourceMeta`, or ``None`` if the file is missing.

    Raises:
        ConfigError: If the file exists but is malformed (missing required
            keys, empty values, or lines that are not ``key: value``).
    """
    path = target / SOURCE_FILENAME
    if not path.exists():
        return None

    raw = path.read_text(encoding="utf-8")
    values: dict[str, str] = {}

    for lineno, raw_line in enumerate(raw.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if ":" not in line:
            raise ConfigError(
                f"Malformed .source at {path} (line {lineno}): expected 'key: value'"
            )
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if not key:
            raise ConfigError(f"Malformed .source at {path} (line {lineno}): empty key")
        values[key] = value

    missing = [k for k in _REQUIRED_KEYS if k not in values]
    if missing:
        raise ConfigError(
            f"Malformed .source at {path}: missing keys {', '.join(missing)}"
        )

    empty = [k for k in _REQUIRED_KEYS if not values[k]]
    if empty:
        raise ConfigError(
            f"Malformed .source at {path}: empty values for {', '.join(empty)}"
        )

    return SourceMeta(
        vendor=values["vendor"],
        origin=values["origin"],
        tool=values["tool"],
        fetched=values["fetched"],
        license=values["license"],
    )
