"""Translate domain ``settings.fragment.json`` into ``.codex/config.toml``.

The Claude target assembles a project ``settings.json`` from every
connected domain's ``settings.fragment.json`` (see
:mod:`ai_dotfiles.core.settings_merge`). The Codex target has no
``settings.json`` — its project config is ``.codex/config.toml``.

This module is the Codex-side counterpart of ``settings_merge``: it
reads the same fragments, translates the keys that have a Codex
``config.toml`` equivalent, and writes them into ``.codex/config.toml``.

Translation map (ADR ai-1-5):

* ``permissions`` — the catalog allow/deny/ask lists land under the
  managed ``[ai_dotfiles.permissions]`` table. Codex has no
  glob-per-command permission model, so the lists are surfaced as-is
  for Codex tooling / the user rather than rewritten.
* ``sandbox`` — a fragment-declared sandbox object lands under the
  managed ``[ai_dotfiles.sandbox]`` table.
* ``hooks`` — Codex has *no* hook harness. Hooks are **not** written;
  the domains that ship them are collected and returned so the command
  layer can print an explicit, fail-loud skip message.

Composability — the critical constraint
----------------------------------------
``.codex/config.toml`` is a **shared** file. ai-15 will write an
``[mcp_servers]`` table into the same file, and the user may hand-author
their own tables. This writer therefore owns exactly *one* top-level
table — ``[ai_dotfiles]`` — delimited by marker comments. Every write
round-trips the file through :mod:`tomllib` -> modify only the
``ai_dotfiles`` key -> :mod:`tomli_w`, so unrelated tables survive
untouched. ``strip_managed`` is the ``remove``-side analogue: it drops
only the ``[ai_dotfiles]`` table and leaves the rest of the file
(user content, ``[mcp_servers]`` …) byte-faithful modulo re-serialise.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import tomli_w
import tomllib

from ai_dotfiles.core.errors import ConfigError, LinkError
from ai_dotfiles.core.settings_merge import load_fragment

__all__ = [
    "CONFIG_FILENAME",
    "MANAGED_TABLE",
    "ConfigResult",
    "build_managed_table",
    "config_path",
    "render_config_toml",
    "strip_managed",
    "translate_fragment",
    "write_codex_config",
]

# The single top-level table this module owns inside ``config.toml``.
# Everything else in the file (``[mcp_servers]``, user tables) is left
# untouched on every write.
MANAGED_TABLE = "ai_dotfiles"

# The project-scoped Codex config filename.
CONFIG_FILENAME = "config.toml"

# Marker comments wrapping the managed table. ``tomli-w`` emits no
# comments, so they are added as raw text around the serialised table;
# they make the managed region visible to a human reading the file.
_MANAGED_BEGIN = "# >>> ai-dotfiles managed (config) — do not edit by hand >>>"
_MANAGED_END = "# <<< ai-dotfiles managed (config) <<<"

# Keys inside ``permissions`` carried through verbatim.
_PERMISSION_KEYS: tuple[str, ...] = ("allow", "deny", "ask")

# settings.fragment.json keys with no Codex config.toml equivalent.
# Codex has no hook harness — see ADR ai-1-5.
_UNTRANSLATABLE_KEYS: tuple[str, ...] = ("hooks",)


class ConfigResult:
    """Outcome of a Codex config write.

    ``status`` is ``"created"``, ``"updated"`` or ``"removed"``.
    ``skipped_keys`` maps a domain name to the untranslatable keys
    (notably ``hooks``) that domain's fragment carried — the command
    layer turns this into an explicit fail-loud skip message.
    """

    __slots__ = ("skipped_keys", "status")

    def __init__(
        self, status: str, skipped_keys: dict[str, list[str]] | None = None
    ) -> None:
        self.status = status
        self.skipped_keys: dict[str, list[str]] = skipped_keys or {}

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return (
            f"ConfigResult(status={self.status!r}, "
            f"skipped_keys={self.skipped_keys!r})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ConfigResult):
            return NotImplemented
        return self.status == other.status and self.skipped_keys == other.skipped_keys


def config_path(project_root: Path) -> Path:
    """Return the project Codex config path (``<root>/.codex/config.toml``)."""
    return project_root / ".codex" / CONFIG_FILENAME


def _concat_dedup(values: list[Any]) -> list[str]:
    """Return the string items of ``values``, first-seen order, no dupes."""
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        if isinstance(item, str) and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def translate_fragment(
    fragment: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Translate one ``settings.fragment.json`` dict for the Codex target.

    Returns ``(translated, skipped)`` where ``translated`` holds only the
    keys with a Codex ``config.toml`` equivalent (``permissions``,
    ``sandbox``) and ``skipped`` lists the untranslatable keys the
    fragment carried (notably ``hooks``). A fragment with neither
    translatable nor skipped keys yields ``({}, [])``.
    """
    translated: dict[str, Any] = {}

    perms = fragment.get("permissions")
    if isinstance(perms, dict):
        out_perms: dict[str, Any] = {}
        for key in _PERMISSION_KEYS:
            value = perms.get(key)
            if isinstance(value, list):
                items = _concat_dedup(value)
                if items:
                    out_perms[key] = items
        if out_perms:
            translated["permissions"] = out_perms

    sandbox = fragment.get("sandbox")
    if isinstance(sandbox, dict) and sandbox:
        translated["sandbox"] = dict(sandbox)

    skipped = [key for key in _UNTRANSLATABLE_KEYS if key in fragment]
    return translated, skipped


def _merge_translated(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Merge two translated dicts — permission lists concat+dedup."""
    result: dict[str, Any] = {}

    base_perms = base.get("permissions") or {}
    overlay_perms = overlay.get("permissions") or {}
    if base_perms or overlay_perms:
        merged_perms: dict[str, Any] = {}
        for key in _PERMISSION_KEYS:
            items = _concat_dedup(
                list(base_perms.get(key, [])) + list(overlay_perms.get(key, []))
            )
            if items:
                merged_perms[key] = items
        if merged_perms:
            result["permissions"] = merged_perms

    # ``sandbox`` — overlay wins (last domain in topo order).
    sandbox = overlay.get("sandbox", base.get("sandbox"))
    if isinstance(sandbox, dict) and sandbox:
        result["sandbox"] = dict(sandbox)

    return result


def build_managed_table(
    fragment_paths: list[tuple[str, Path]],
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """Assemble the managed ``[ai_dotfiles]`` table from domain fragments.

    ``fragment_paths`` is a list of ``(domain_name, fragment_path)`` in
    caller-supplied (topological) order — the same order
    :func:`ai_dotfiles.core.settings_merge.collect_domain_fragments`
    produces, just paired with the owning domain so skips can be
    attributed.

    Returns ``(managed_table, skipped_by_domain)``: the dict to write
    under ``[ai_dotfiles]`` (empty if nothing translatable), and a map
    of domain name -> untranslatable keys it carried.
    """
    managed: dict[str, Any] = {}
    skipped_by_domain: dict[str, list[str]] = {}
    for domain_name, path in fragment_paths:
        fragment = load_fragment(path)
        translated, skipped = translate_fragment(fragment)
        if translated:
            managed = _merge_translated(managed, translated)
        if skipped:
            skipped_by_domain[domain_name] = skipped
    return managed, skipped_by_domain


def _parse_existing(path: Path) -> dict[str, Any]:
    """Load an existing ``config.toml`` (empty dict if absent).

    Raises :class:`ConfigError` on malformed TOML so a hand-broken
    config fails loud rather than being silently overwritten.
    """
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Cannot read {path}: {exc}") from exc


def render_config_toml(existing: dict[str, Any], managed: dict[str, Any]) -> str:
    """Render the full ``config.toml`` text — managed table + everything else.

    ``existing`` is the parsed current file; its ``ai_dotfiles`` table
    (if any) is dropped and replaced by ``managed``. Every other
    top-level table (``[mcp_servers]``, user tables) is preserved. The
    managed table is serialised inside marker comments so a human can
    see which region ai-dotfiles owns.

    If ``managed`` is empty the managed table is omitted entirely; the
    function then renders only the surviving user content.
    """
    other = {k: v for k, v in existing.items() if k != MANAGED_TABLE}

    other_text = tomli_w.dumps(other).strip() if other else ""

    if not managed:
        return other_text + "\n" if other_text else ""

    managed_text = tomli_w.dumps({MANAGED_TABLE: managed}).strip()
    block = f"{_MANAGED_BEGIN}\n{managed_text}\n{_MANAGED_END}"

    if other_text:
        return f"{other_text}\n\n{block}\n"
    return f"{block}\n"


def write_codex_config(
    project_root: Path,
    fragment_paths: list[tuple[str, Path]],
) -> ConfigResult:
    """Write the managed Codex config region from domain fragments.

    Translates every fragment's permissions / sandbox keys into the
    managed ``[ai_dotfiles]`` table of ``<root>/.codex/config.toml``,
    leaving any unrelated table (e.g. a future ``[mcp_servers]``)
    intact. Untranslatable keys (``hooks``) are not written; the
    domains that carried them are reported in
    :attr:`ConfigResult.skipped_keys`.

    When no fragment is translatable the managed table is stripped;
    if that empties the file it is deleted.

    Raises:
        ConfigError: if an existing ``config.toml`` is malformed.
        LinkError: if the file cannot be written.
    """
    managed, skipped = build_managed_table(fragment_paths)
    path = config_path(project_root)
    existing = _parse_existing(path)
    had_managed = MANAGED_TABLE in existing
    existed = path.is_file()

    text = render_config_toml(existing, managed)

    try:
        if text:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        elif existed:
            path.unlink()
    except OSError as exc:
        raise LinkError(f"Failed to write Codex config {path}: {exc}") from exc

    if not managed:
        status = "removed" if had_managed else "updated"
    elif not had_managed:
        status = "created"
    else:
        status = "updated"
    return ConfigResult(status, skipped)


def strip_managed(project_root: Path) -> bool:
    """Remove only the managed ``[ai_dotfiles]`` table from ``config.toml``.

    The ``remove``-side analogue of :func:`write_codex_config`. User
    content and unrelated tables (``[mcp_servers]`` …) are preserved; a
    file left empty after the strip is deleted. Returns ``True`` if the
    file was rewritten or deleted, ``False`` if there was nothing to do.

    Raises:
        ConfigError: if the existing ``config.toml`` is malformed.
        LinkError: if the file cannot be rewritten.
    """
    path = config_path(project_root)
    if not path.is_file():
        return False
    existing = _parse_existing(path)
    if MANAGED_TABLE not in existing:
        return False

    text = render_config_toml(existing, {})
    try:
        if text:
            path.write_text(text, encoding="utf-8")
        else:
            path.unlink()
    except OSError as exc:
        raise LinkError(f"Failed to strip managed config from {path}: {exc}") from exc
    return True
