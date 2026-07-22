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
``.codex/config.toml`` is a **shared** file. Three writers contribute to
it: the settings writer (this module's ``[ai_dotfiles]`` table, ADR
ai-1-5), the MCP writer (this module's ``[mcp_servers]`` table, ai-15),
and the user, who may hand-author their own tables and their own MCP
servers. Each ai-dotfiles writer owns exactly *one* top-level table and
round-trips the file through :mod:`tomllib` -> modify only its table ->
:mod:`tomli_w`, so unrelated tables survive untouched.

* ``[ai_dotfiles]`` — wholly ai-dotfiles-owned. ``strip_managed`` drops
  it entirely on ``remove``.
* ``[mcp_servers]`` — *partly* owned: a domain's ``mcp.fragment.json``
  servers are ai-dotfiles-owned, but the user may add their own server
  entries to the same table. Ownership is tracked in a sidecar file
  (:mod:`ai_dotfiles.core.codex_mcp_ownership`) so ``remove`` strips
  only domain-contributed servers and leaves the user's intact.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import tomli_w
import tomllib

from ai_dotfiles.core.codex_mcp_ownership import (
    delete_mcp_ownership,
    load_mcp_ownership,
    save_mcp_ownership,
)
from ai_dotfiles.core.errors import ConfigError, LinkError
from ai_dotfiles.core.mcp_merge import assemble_mcp_servers
from ai_dotfiles.core.settings_merge import load_fragment

__all__ = [
    "CONFIG_FILENAME",
    "MANAGED_TABLE",
    "MCP_TABLE",
    "ConfigResult",
    "McpResult",
    "add_mcp_servers",
    "build_managed_table",
    "build_mcp_table",
    "config_path",
    "config_state",
    "ensure_project_doc_fallback",
    "render_config_toml",
    "strip_codex_mcp",
    "strip_managed",
    "translate_fragment",
    "translate_mcp_server",
    "write_codex_config",
    "write_codex_mcp",
]

# The settings table this module owns inside ``config.toml``. Everything
# else in the file (``[mcp_servers]``, user tables) is left untouched on
# every settings write.
MANAGED_TABLE = "ai_dotfiles"

# The MCP table. Codex reads MCP servers from ``[mcp_servers.<name>]``
# sub-tables of ``config.toml`` (whereas the Claude target writes a JSON
# ``mcpServers`` object into ``.mcp.json``). Domain-contributed servers
# are ai-dotfiles-owned; user-authored servers in the same table survive.
MCP_TABLE = "mcp_servers"

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


def config_path(codex_dir: Path) -> Path:
    """Return the Codex config path inside ``codex_dir``.

    ``codex_dir`` is the directory holding ``config.toml`` — project
    scope passes :func:`ai_dotfiles.core.paths.project_codex_dir`
    (``<root>/.codex``), the global scope passes
    :func:`ai_dotfiles.core.paths.codex_home` (``$CODEX_HOME``).
    """
    return codex_dir / CONFIG_FILENAME


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
    codex_dir: Path,
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
    path = config_path(codex_dir)
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


def config_state(
    codex_dir: Path,
    settings_fragment_paths: list[tuple[str, Path]],
    mcp_fragment_paths: list[tuple[str, Path]],
) -> str:
    """Return the drift state of the managed ``config.toml`` regions.

    The ``config.toml`` analogue of
    :func:`ai_dotfiles.core.codex_install.is_stale` — but ``config.toml``
    carries no source-sha header, so drift is detected by *recomputing* the
    expected managed content from the current fragments and comparing it to
    what is on disk. Two regions are checked:

    * the managed ``[ai_dotfiles]`` table vs
      :func:`build_managed_table` over the settings fragments;
    * the domain-owned ``[mcp_servers.*]`` entries (those recorded in the
      ownership sidecar) vs :func:`build_mcp_table` over the MCP fragments.

    Returns one of:

    * ``"absent"`` — nothing is expected and nothing managed is on disk
      (the manifest contributes no Codex config; nothing to report);
    * ``"stale"``  — an on-disk managed region differs from the freshly
      computed expectation (a fragment changed, or a manual edit drifted);
    * ``"ok"``     — every managed region matches the current fragments.

    Raises:
        ConfigError: if the on-disk ``config.toml`` is malformed.
    """
    expected_managed, _ = build_managed_table(settings_fragment_paths)
    expected_servers, _ = build_mcp_table(mcp_fragment_paths)

    existing = _parse_existing(config_path(codex_dir))

    actual_managed_raw = existing.get(MANAGED_TABLE, {})
    actual_managed = actual_managed_raw if isinstance(actual_managed_raw, dict) else {}

    ownership = load_mcp_ownership(codex_dir)
    existing_mcp_raw = existing.get(MCP_TABLE, {})
    existing_mcp = existing_mcp_raw if isinstance(existing_mcp_raw, dict) else {}
    actual_owned = {
        name: existing_mcp[name] for name in ownership if name in existing_mcp
    }

    if (
        not expected_managed
        and not expected_servers
        and not actual_managed
        and not ownership
    ):
        return "absent"

    if expected_managed == actual_managed and expected_servers == actual_owned:
        return "ok"
    return "stale"


def ensure_project_doc_fallback(codex_dir: Path, filename: str = "CLAUDE.md") -> bool:
    """Ensure Codex reads ``filename`` as a project-doc fallback.

    Adds ``filename`` to the top-level ``project_doc_fallback_filenames``
    array of ``.codex/config.toml`` so Codex reads it (e.g. ``CLAUDE.md``)
    in any directory that has no ``AGENTS.md`` — keeping the canonical
    instructions in ``CLAUDE.md`` with no rendered copy or symlink. The
    managed ``[ai_dotfiles]`` block and every other table are preserved.
    Returns ``True`` if the file was changed, ``False`` if the entry was
    already present.

    Note: Codex honours a project-scoped ``.codex/config.toml`` only once
    the project is *trusted*; on a fresh checkout the fallback takes effect
    after the user accepts the trust prompt.

    Raises:
        ConfigError: if the existing ``config.toml`` is malformed.
        LinkError: if the file cannot be written.
    """
    path = config_path(codex_dir)
    existing = _parse_existing(path)
    current = existing.get("project_doc_fallback_filenames")
    items = [str(x) for x in current] if isinstance(current, list) else []
    if filename in items:
        return False

    items.append(filename)
    existing["project_doc_fallback_filenames"] = items
    managed_raw = existing.get(MANAGED_TABLE, {})
    managed = managed_raw if isinstance(managed_raw, dict) else {}
    text = render_config_toml(existing, managed)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise LinkError(f"Failed to write Codex config {path}: {exc}") from exc
    return True


def strip_managed(codex_dir: Path) -> bool:
    """Remove only the managed ``[ai_dotfiles]`` table from ``config.toml``.

    The ``remove``-side analogue of :func:`write_codex_config`. User
    content and unrelated tables (``[mcp_servers]`` …) are preserved; a
    file left empty after the strip is deleted. Returns ``True`` if the
    file was rewritten or deleted, ``False`` if there was nothing to do.

    Raises:
        ConfigError: if the existing ``config.toml`` is malformed.
        LinkError: if the file cannot be rewritten.
    """
    path = config_path(codex_dir)
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


# ── MCP: mcp.fragment.json -> [mcp_servers] (ai-15) ───────────────────


class McpResult:
    """Outcome of a Codex ``[mcp_servers]`` write.

    ``status`` is ``"created"``, ``"updated"`` or ``"removed"``.
    ``collisions`` lists server names a domain declared that the user
    had already hand-authored in ``[mcp_servers]`` — the user version is
    kept and the command layer turns this into a warning.
    """

    __slots__ = ("collisions", "status")

    def __init__(self, status: str, collisions: list[str] | None = None) -> None:
        self.status = status
        self.collisions: list[str] = collisions or []

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return f"McpResult(status={self.status!r}, collisions={self.collisions!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, McpResult):
            return NotImplemented
        return self.status == other.status and self.collisions == other.collisions


def translate_mcp_server(server: dict[str, Any]) -> dict[str, Any]:
    """Translate one ``.mcp.json`` server entry for the Codex target.

    The Claude ``.mcp.json`` server shape (``command``, ``args``,
    ``env``, ``type``, ``url`` …) and the Codex ``[mcp_servers.<name>]``
    TOML shape use the *same* keys — the only structural difference is
    the container format (JSON object vs TOML table). The translation is
    therefore a faithful copy, with one constraint: TOML has no ``null``,
    so keys whose value is ``None`` are dropped (a ``null`` in a fragment
    means "unset", which is exactly an absent TOML key).
    """
    return {k: v for k, v in server.items() if v is not None}


def build_mcp_table(
    fragment_paths: list[tuple[str, Path]],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    """Assemble the domain-owned ``[mcp_servers]`` servers from fragments.

    ``fragment_paths`` is a list of ``(domain_name, mcp_fragment_path)``
    in caller-supplied (topological) order — the same shape
    :func:`ai_dotfiles.core.mcp_merge.collect_mcp_fragments` produces.

    Returns ``(servers, ownership)``: the per-server TOML-ready dicts to
    write under ``[mcp_servers]`` and a ``server_name -> [domain, ...]``
    ownership map for the next strip cycle.
    """
    raw_servers, ownership = assemble_mcp_servers(fragment_paths)
    servers = {name: translate_mcp_server(cfg) for name, cfg in raw_servers.items()}
    return servers, ownership


def _merge_mcp_servers(
    existing_mcp: dict[str, Any],
    domain_servers: dict[str, dict[str, Any]],
    previous_ownership: dict[str, list[str]],
) -> tuple[dict[str, Any], list[str]]:
    """Compose the final ``[mcp_servers]`` table.

    Mirrors :func:`ai_dotfiles.core.mcp_merge.merge_with_existing_mcp`:

    * user-authored servers (in ``existing_mcp`` but not in
      ``previous_ownership``) are preserved verbatim;
    * previously domain-owned servers missing from ``domain_servers``
      are dropped;
    * ``domain_servers`` is applied on top, but a first-time collision
      with a user-authored name keeps the user version.

    Returns ``(merged_table, collisions)``.
    """
    merged: dict[str, Any] = {}
    collisions: list[str] = []

    for name, cfg in existing_mcp.items():
        if name not in previous_ownership:
            # User-authored — preserve.
            merged[name] = cfg

    for name, cfg in domain_servers.items():
        if name in existing_mcp and name not in previous_ownership:
            # First-time collision: the user owns this name. Keep theirs.
            collisions.append(name)
            continue
        merged[name] = cfg

    return merged, collisions


def write_codex_mcp(
    codex_dir: Path,
    fragment_paths: list[tuple[str, Path]],
) -> McpResult:
    """Write the domain-owned servers into ``[mcp_servers]`` of config.toml.

    The Codex-side analogue of
    :func:`ai_dotfiles.core.mcp_apply.rebuild_claude_config`'s MCP half.
    Translates every domain ``mcp.fragment.json`` into the
    ``[mcp_servers]`` table of ``<root>/.codex/config.toml``, preserving
    user-authored servers and any unrelated table (``[ai_dotfiles]`` …).
    Domain-contributed server names are recorded in a sidecar ownership
    file so a later :func:`strip_codex_mcp` drops exactly those.

    When no fragment declares a server the domain-owned servers are
    stripped; if that empties the ``[mcp_servers]`` table it is removed,
    and if that empties the file it is deleted.

    Raises:
        ConfigError: if an existing ``config.toml`` or ownership file is
            malformed.
        LinkError: if the file cannot be written.
    """
    domain_servers, new_ownership = build_mcp_table(fragment_paths)
    path = config_path(codex_dir)
    existing = _parse_existing(path)
    previous_ownership = load_mcp_ownership(codex_dir)

    existing_mcp_raw = existing.get(MCP_TABLE, {})
    existing_mcp: dict[str, Any] = (
        dict(existing_mcp_raw) if isinstance(existing_mcp_raw, dict) else {}
    )
    had_mcp = bool(existing_mcp)

    merged, collisions = _merge_mcp_servers(
        existing_mcp, domain_servers, previous_ownership
    )

    new_config = {k: v for k, v in existing.items() if k != MCP_TABLE}
    if merged:
        new_config[MCP_TABLE] = merged

    existed = path.is_file()
    text = tomli_w.dumps(new_config).strip()
    text = text + "\n" if text else ""

    try:
        if text:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        elif existed:
            path.unlink()
    except OSError as exc:
        raise LinkError(f"Failed to write Codex MCP config {path}: {exc}") from exc

    # Persist or clear ownership symmetric to the config write. Only
    # names that actually landed in the merged table count as owned.
    effective_ownership = {
        name: domains
        for name, domains in new_ownership.items()
        if name in merged and name not in collisions
    }
    if effective_ownership:
        save_mcp_ownership(codex_dir, effective_ownership)
    else:
        delete_mcp_ownership(codex_dir)

    if not merged.keys() & domain_servers.keys():
        status = "removed" if had_mcp and previous_ownership else "updated"
    elif not (had_mcp and previous_ownership):
        status = "created"
    else:
        status = "updated"
    return McpResult(status, collisions)


def add_mcp_servers(
    codex_dir: Path, servers: dict[str, dict[str, Any]]
) -> tuple[list[str], list[str]]:
    """Add user-authored MCP servers to ``[mcp_servers]`` of config.toml.

    Used by ``ai-dotfiles migrate`` to carry a project's own ``.mcp.json``
    servers (those not owned by any domain) to the Codex target. Existing
    entries — domain-owned or user — are never overwritten: a name already in
    ``[mcp_servers]`` is skipped. These servers are deliberately **not**
    recorded in the domain ownership sidecar, so from Codex's side they look
    user-authored and a later :func:`write_codex_mcp`/:func:`strip_codex_mcp`
    preserves them. The managed ``[ai_dotfiles]`` block is kept.

    Returns ``(added, skipped)``.

    Raises:
        ConfigError: if the existing config.toml is malformed.
        LinkError: if the file cannot be written.
    """
    path = config_path(codex_dir)
    existing = _parse_existing(path)
    mcp_raw = existing.get(MCP_TABLE, {})
    mcp = dict(mcp_raw) if isinstance(mcp_raw, dict) else {}

    added: list[str] = []
    skipped: list[str] = []
    for name, cfg in servers.items():
        if name in mcp:
            skipped.append(name)
            continue
        mcp[name] = cfg
        added.append(name)

    if not added:
        return added, skipped

    existing[MCP_TABLE] = mcp
    managed_raw = existing.get(MANAGED_TABLE, {})
    managed = managed_raw if isinstance(managed_raw, dict) else {}
    text = render_config_toml(existing, managed)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise LinkError(f"Failed to write Codex MCP config {path}: {exc}") from exc
    return added, skipped


def strip_codex_mcp(codex_dir: Path) -> bool:
    """Drop only domain-owned servers from ``[mcp_servers]`` of config.toml.

    The ``remove``-side analogue of :func:`write_codex_mcp`. User-authored
    servers in ``[mcp_servers]`` and unrelated tables (``[ai_dotfiles]``
    …) are preserved; a ``[mcp_servers]`` table left empty is removed and
    a file left empty is deleted. Returns ``True`` if the file was
    rewritten or deleted, ``False`` if there was nothing to do.

    Raises:
        ConfigError: if the existing ``config.toml`` or ownership file is
            malformed.
        LinkError: if the file cannot be rewritten.
    """
    path = config_path(codex_dir)
    previous_ownership = load_mcp_ownership(codex_dir)
    if not path.is_file() or not previous_ownership:
        delete_mcp_ownership(codex_dir)
        return False

    existing = _parse_existing(path)
    existing_mcp_raw = existing.get(MCP_TABLE, {})
    existing_mcp: dict[str, Any] = (
        dict(existing_mcp_raw) if isinstance(existing_mcp_raw, dict) else {}
    )
    surviving = {
        name: cfg
        for name, cfg in existing_mcp.items()
        if name not in previous_ownership
    }

    new_config = {k: v for k, v in existing.items() if k != MCP_TABLE}
    if surviving:
        new_config[MCP_TABLE] = surviving

    text = tomli_w.dumps(new_config).strip()
    text = text + "\n" if text else ""
    try:
        if text:
            path.write_text(text, encoding="utf-8")
        else:
            path.unlink()
    except OSError as exc:
        raise LinkError(
            f"Failed to strip managed MCP servers from {path}: {exc}"
        ) from exc
    delete_mcp_ownership(codex_dir)
    return True
