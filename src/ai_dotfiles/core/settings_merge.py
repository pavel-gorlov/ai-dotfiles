"""Assemble settings.json by deep-merging settings.fragment.json files.

Each connected domain may ship a ``settings.fragment.json``. This module
merges those fragments into a single ``settings.json`` suitable for Claude
Code.

Merge rules:
  * ``hooks``: per event key (e.g. ``PostToolUse``), arrays are
    concatenated. Base entries come first, overlay entries appended.
  * Any other top-level key: overlay overwrites base.
  * Meta keys ``_domain`` and ``_description`` are stripped from output.

Fragments are merged in deterministic order (sorted by path) so that the
output is reproducible regardless of filesystem iteration order.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_dotfiles.core.elements import ElementType, parse_element
from ai_dotfiles.core.errors import ConfigError

_META_KEYS: tuple[str, ...] = ("_domain", "_description")


def load_fragment(path: Path) -> dict[str, Any]:
    """Load a ``settings.fragment.json`` file.

    Returns an empty dict if the file does not exist. Raises
    :class:`ConfigError` on invalid JSON.
    """
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in fragment {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Cannot read fragment {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Fragment {path} must contain a JSON object at top level")
    return data


def strip_meta(fragment: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``fragment`` without the meta keys."""
    return {k: v for k, v in fragment.items() if k not in _META_KEYS}


def deep_merge_hooks(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Merge two settings dicts, concatenating hook arrays by event.

    Non-hook keys: ``overlay`` overwrites ``base`` (later wins).
    ``hooks`` key: per-event arrays concatenated (base first, overlay next).
    Returns a new dict; inputs are not mutated.
    """
    result: dict[str, Any] = {}

    # Copy base keys except hooks (we handle hooks separately).
    for key, value in base.items():
        if key == "hooks":
            continue
        result[key] = value

    # Overlay non-hook keys overwrite.
    for key, value in overlay.items():
        if key == "hooks":
            continue
        result[key] = value

    base_hooks = base.get("hooks")
    overlay_hooks = overlay.get("hooks")

    if base_hooks is None and overlay_hooks is None:
        return result

    merged_hooks: dict[str, list[Any]] = {}
    if isinstance(base_hooks, dict):
        for event, entries in base_hooks.items():
            if isinstance(entries, list):
                merged_hooks[event] = list(entries)
            else:
                merged_hooks[event] = [entries]
    if isinstance(overlay_hooks, dict):
        for event, entries in overlay_hooks.items():
            existing = merged_hooks.setdefault(event, [])
            if isinstance(entries, list):
                existing.extend(entries)
            else:
                existing.append(entries)

    result["hooks"] = merged_hooks
    return result


def assemble_settings(
    fragments: list[Path], base: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Load, strip meta, and merge all fragments in deterministic order.

    Fragments are sorted by path so the output is reproducible. If
    ``base`` is provided, merging starts from that dict; otherwise from
    an empty dict.
    """
    result: dict[str, Any] = dict(base) if base is not None else {}
    for path in sorted(fragments):
        fragment = load_fragment(path)
        cleaned = strip_meta(fragment)
        result = deep_merge_hooks(result, cleaned)
    return result


def write_settings(settings: dict[str, Any], target: Path) -> None:
    """Write ``settings`` as JSON to ``target``.

    Uses indent=2 and a trailing newline. Parent directories are created
    if missing.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2)
        fh.write("\n")


def collect_domain_fragments(packages: list[str], catalog: Path) -> list[Path]:
    """Collect ``settings.fragment.json`` paths from domain packages.

    Only ``@domain`` specifiers contribute fragments. Standalone items
    (``skill:``, ``agent:``, ``rule:``) are ignored. Missing fragment
    files are silently skipped — a domain without a fragment is valid.
    """
    fragments: list[Path] = []
    for spec in packages:
        try:
            element = parse_element(spec)
        except Exception:  # noqa: BLE001 - ignore non-domain parse failures
            continue
        if element.type is not ElementType.DOMAIN:
            continue
        fragment_path = catalog / element.name / "settings.fragment.json"
        if fragment_path.exists():
            fragments.append(fragment_path)
    return fragments
