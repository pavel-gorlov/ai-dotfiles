"""Assemble settings.json by deep-merging settings.fragment.json files.

Each connected domain may ship a ``settings.fragment.json``. This module
merges those fragments into a single ``settings.json`` suitable for Claude
Code.

Merge rules:
  * ``hooks``: per event key (e.g. ``PostToolUse``), arrays are
    concatenated. Base entries come first, overlay entries appended.
  * Any other top-level key: overlay overwrites base.

Fragments contain pure Claude Code config — no domain metadata. Domain
metadata (name, description, dependencies, host requirements) lives in
``catalog/<domain>/domain.json`` and is read via
:mod:`ai_dotfiles.core.domain_meta`.

Domains are merged in topological order (deps first) so that layered
domains compose correctly; see :func:`collect_domain_fragments`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ai_dotfiles.core.elements import ElementType, parse_element
from ai_dotfiles.core.errors import ConfigError


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
    """Return a shallow copy of ``fragment``.

    Historically this stripped underscored meta keys (``_domain`` etc.)
    that lived inside ``settings.fragment.json``. Those keys have moved
    to ``domain.json``; the function is kept as a no-op for callers
    that still want defensive copying.
    """
    return dict(fragment)


# Keys inside ``permissions`` whose values are lists that should be
# concat-deduped across base and overlay instead of overwritten.
_PERMISSION_LIST_KEYS: tuple[str, ...] = ("allow", "deny", "ask")


def _concat_dedup(base: list[Any], overlay: list[Any]) -> list[Any]:
    """Return ``base + overlay`` preserving first-seen order, no duplicates.

    Uses a set-of-seen for items that hash; falls back to ``in`` for
    unhashable items so we never crash on dict entries.
    """
    result: list[Any] = []
    seen_hashable: set[Any] = set()
    for item in list(base) + list(overlay):
        try:
            if item in seen_hashable:
                continue
            seen_hashable.add(item)
        except TypeError:
            if item in result:
                continue
        result.append(item)
    return result


def _merge_permissions(
    base: dict[str, Any] | None, overlay: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Merge two ``permissions`` dicts.

    For each of ``allow`` / ``deny`` / ``ask``: concat+dedup lists.
    Any other subkey: overlay wins. Returns ``None`` if both inputs
    are ``None``.
    """
    if base is None and overlay is None:
        return None
    result: dict[str, Any] = {}
    base = base if isinstance(base, dict) else {}
    overlay = overlay if isinstance(overlay, dict) else {}
    for key, value in base.items():
        if key in _PERMISSION_LIST_KEYS:
            continue
        result[key] = value
    for key, value in overlay.items():
        if key in _PERMISSION_LIST_KEYS:
            continue
        result[key] = value
    for key in _PERMISSION_LIST_KEYS:
        base_list = base.get(key)
        overlay_list = overlay.get(key)
        if base_list is None and overlay_list is None:
            continue
        base_seq = base_list if isinstance(base_list, list) else []
        overlay_seq = overlay_list if isinstance(overlay_list, list) else []
        result[key] = _concat_dedup(base_seq, overlay_seq)
    return result


def _merge_hooks(
    base: dict[str, Any] | None, overlay: dict[str, Any] | None
) -> dict[str, list[Any]] | None:
    """Merge two ``hooks`` dicts by concatenating per-event arrays."""
    if base is None and overlay is None:
        return None
    merged: dict[str, list[Any]] = {}
    if isinstance(base, dict):
        for event, entries in base.items():
            if isinstance(entries, list):
                merged[event] = list(entries)
            else:
                merged[event] = [entries]
    if isinstance(overlay, dict):
        for event, entries in overlay.items():
            existing = merged.setdefault(event, [])
            if isinstance(entries, list):
                existing.extend(entries)
            else:
                existing.append(entries)
    return merged


def deep_merge_settings(
    base: dict[str, Any], overlay: dict[str, Any]
) -> dict[str, Any]:
    """Merge two settings dicts.

    Rules:
      * ``hooks`` — per-event arrays concatenated (base first, overlay next).
      * ``permissions.allow`` / ``permissions.deny`` / ``permissions.ask`` —
        concat+dedup (preserves first-seen order so the output is stable).
      * ``permissions`` subkeys other than the three above — overlay wins.
      * Any other top-level key — overlay overwrites base.

    Returns a new dict; inputs are not mutated.
    """
    special = {"hooks", "permissions"}
    result: dict[str, Any] = {}
    for key, value in base.items():
        if key in special:
            continue
        result[key] = value
    for key, value in overlay.items():
        if key in special:
            continue
        result[key] = value

    merged_perms = _merge_permissions(
        base.get("permissions"), overlay.get("permissions")
    )
    if merged_perms is not None:
        result["permissions"] = merged_perms

    merged_hooks = _merge_hooks(base.get("hooks"), overlay.get("hooks"))
    if merged_hooks is not None:
        result["hooks"] = merged_hooks

    return result


# Backwards-compat alias — older name used before permissions-merge extension.
deep_merge_hooks = deep_merge_settings


def assemble_settings(
    fragments: list[Path], base: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Load, strip meta, and merge all fragments in caller-supplied order.

    The caller is responsible for ordering — typically obtained from
    :func:`collect_domain_fragments`, which returns domain fragments in
    topological order so layered domains merge with deps first. If
    ``base`` is provided, merging starts from that dict; otherwise from
    an empty dict.
    """
    result: dict[str, Any] = dict(base) if base is not None else {}
    for path in fragments:
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


def hook_signature(entry: Any) -> str:
    """Return a stable SHA-256 signature for a hook entry.

    Used by settings ownership tracking to identify which hook objects
    were inserted by ai-dotfiles, so we can strip them out on the next
    rebuild without disturbing user-authored hooks.
    """
    payload = json.dumps(entry, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def collect_fragment_contributions(
    fragments: list[Path],
) -> dict[str, list[str]]:
    """Return what assemble_settings would inject for the given fragments.

    Reads all fragments in caller-supplied order and reports the set of
    strings they would add to ``permissions.{allow,deny,ask}`` plus the
    signatures of every hook entry. Dedup preserves first-seen order so
    ownership matches what ``assemble_settings`` actually emits.
    """
    allow: list[str] = []
    deny: list[str] = []
    ask: list[str] = []
    sigs: list[str] = []
    seen_allow: set[str] = set()
    seen_deny: set[str] = set()
    seen_ask: set[str] = set()
    seen_sigs: set[str] = set()
    for path in fragments:
        fragment = strip_meta(load_fragment(path))
        perms = fragment.get("permissions") or {}
        if isinstance(perms, dict):
            for key, target, seen in (
                ("allow", allow, seen_allow),
                ("deny", deny, seen_deny),
                ("ask", ask, seen_ask),
            ):
                items = perms.get(key)
                if not isinstance(items, list):
                    continue
                for item in items:
                    if isinstance(item, str) and item not in seen:
                        seen.add(item)
                        target.append(item)
        hooks = fragment.get("hooks")
        if isinstance(hooks, dict):
            for entries in hooks.values():
                if isinstance(entries, list):
                    iterable: list[Any] = entries
                else:
                    iterable = [entries]
                for entry in iterable:
                    sig = hook_signature(entry)
                    if sig not in seen_sigs:
                        seen_sigs.add(sig)
                        sigs.append(sig)
    return {
        "permissions_allow": allow,
        "permissions_deny": deny,
        "permissions_ask": ask,
        "hooks_signatures": sigs,
    }


def strip_owned(
    settings: dict[str, Any], owned: dict[str, list[str]]
) -> dict[str, Any]:
    """Return a copy of ``settings`` with previously-owned entries removed.

    Strips strings listed in ``owned['permissions_allow']`` etc. from
    ``settings.permissions.{allow,deny,ask}``, and removes hook entries
    whose signature appears in ``owned['hooks_signatures']``. Empty
    permission/hook containers are pruned so the resulting dict
    accurately represents user-only content.
    """
    if not owned:
        return dict(settings)

    result: dict[str, Any] = dict(settings)

    perms_in = result.get("permissions")
    if isinstance(perms_in, dict):
        new_perms: dict[str, Any] = {}
        for key, value in perms_in.items():
            new_perms[key] = value
        for key, owned_key in (
            ("allow", "permissions_allow"),
            ("deny", "permissions_deny"),
            ("ask", "permissions_ask"),
        ):
            owned_set = set(owned.get(owned_key, []))
            if not owned_set:
                continue
            value = new_perms.get(key)
            if not isinstance(value, list):
                continue
            kept = [v for v in value if not (isinstance(v, str) and v in owned_set)]
            if kept:
                new_perms[key] = kept
            else:
                new_perms.pop(key, None)
        if new_perms:
            result["permissions"] = new_perms
        else:
            result.pop("permissions", None)

    hooks_in = result.get("hooks")
    owned_sigs = set(owned.get("hooks_signatures", []))
    if isinstance(hooks_in, dict) and owned_sigs:
        new_hooks: dict[str, Any] = {}
        for event, entries in hooks_in.items():
            if isinstance(entries, list):
                kept = [e for e in entries if hook_signature(e) not in owned_sigs]
            else:
                kept = [entries] if hook_signature(entries) not in owned_sigs else []
            if kept:
                new_hooks[event] = kept
        if new_hooks:
            result["hooks"] = new_hooks
        else:
            result.pop("hooks", None)

    return result


def collect_domain_fragments(packages: list[str], catalog: Path) -> list[Path]:
    """Collect ``settings.fragment.json`` paths from domain packages.

    Only ``@domain`` specifiers contribute fragments. Standalone items
    (``skill:``, ``agent:``, ``rule:``) are ignored. Missing fragment
    files are silently skipped — a domain without a fragment is valid.

    Domains are topologically sorted (deps first) so layered fragments
    merge in the right order regardless of how the manifest is written.
    """
    from ai_dotfiles.core.dependencies import topological_sort

    domain_elements = []
    for spec in packages:
        try:
            element = parse_element(spec)
        except Exception:  # noqa: BLE001 - ignore non-domain parse failures
            continue
        if element.type is not ElementType.DOMAIN:
            continue
        domain_elements.append(element)

    ordered = topological_sort(catalog, domain_elements)

    fragments: list[Path] = []
    for element in ordered:
        fragment_path = catalog / element.name / "settings.fragment.json"
        if fragment_path.exists():
            fragments.append(fragment_path)
    return fragments
