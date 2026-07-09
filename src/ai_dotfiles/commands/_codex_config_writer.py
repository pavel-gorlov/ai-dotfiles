"""Shared command-layer helper: write ``.codex/config.toml`` from a manifest.

Both ``install`` and ``add`` must translate the full set of installed
domains' ``settings.fragment.json`` / ``mcp.fragment.json`` into the
managed regions of ``<root>/.codex/config.toml``. The translation logic
lives in :mod:`ai_dotfiles.core.codex_config`; this module is the thin
command-layer wrapper that turns its structured results into the
user-facing ``ui`` messages — keeping the two callers byte-identical.

The critical contract: the ``codex_config`` writers round-trip the
*whole* managed region, not a per-domain delta. Callers must pass the
full set of packages currently in the manifest, so writing for a
newly-added domain does not drop a sibling domain's managed
``[ai_dotfiles]`` / ``[mcp_servers]`` content.
"""

from __future__ import annotations

from pathlib import Path

from ai_dotfiles import ui
from ai_dotfiles.core import codex_config, codex_hooks, settings_merge
from ai_dotfiles.core.mcp_merge import collect_mcp_fragments


def _codex_fragment_pairs(packages: list[str], catalog: Path) -> list[tuple[str, Path]]:
    """Pair each domain ``settings.fragment.json`` with its domain name.

    Reuses :func:`settings_merge.collect_domain_fragments` (topological
    order) and derives the domain name from the fragment's parent
    directory — the catalog layout is ``catalog/<domain>/settings...``.
    """
    fragments = settings_merge.collect_domain_fragments(packages, catalog)
    return [(path.parent.name, path) for path in fragments]


def write_codex_config(packages: list[str], project_root: Path, catalog: Path) -> None:
    """Translate domain fragments into ``.codex/config.toml`` (ADR ai-1-5).

    Permissions / sandbox keys land in the managed config region;
    ``hooks`` have no Codex equivalent and are skipped with an explicit
    fail-loud message naming each domain that carried them.
    """
    result = codex_config.write_codex_config(
        project_root, _codex_fragment_pairs(packages, catalog)
    )
    if result.status == "created":
        ui.success("config.toml (managed region created)")
    elif result.status == "updated":
        ui.success("config.toml (managed region updated)")
    # ``hooks`` have no place in config.toml's [ai_dotfiles] table, but they
    # are no longer dropped — write_codex_hooks emits them to
    # .codex/hooks.json. See :func:`write_codex_hooks`.


def write_codex_hooks(packages: list[str], project_root: Path, catalog: Path) -> None:
    """Emit domain hooks into ``.codex/hooks.json`` (Codex hook harness).

    Domain ``settings.fragment.json`` ``hooks`` are translated to Codex's
    lifecycle-hook format. Events with no Codex twin are reported.
    """
    result = codex_hooks.write_codex_hooks(
        project_root, _codex_fragment_pairs(packages, catalog)
    )
    if result.status == "created":
        ui.success("hooks.json (managed hooks created)")
    elif result.status == "updated":
        ui.success("hooks.json (managed hooks updated)")
    elif result.status == "removed":
        ui.info("hooks.json (managed hooks removed)")
    for domain_name, events in sorted(result.skipped_events.items()):
        joined = ", ".join(events)
        ui.warn(
            f"@{domain_name}: hook event(s) '{joined}' have no Codex twin — "
            f"skipped for the Codex target."
        )


def write_codex_mcp(packages: list[str], project_root: Path, catalog: Path) -> None:
    """Translate domain ``mcp.fragment.json`` files into ``[mcp_servers]``.

    The Codex-target counterpart of the ``.mcp.json`` rebuild — domain
    MCP servers land in the ``[mcp_servers]`` table of
    ``.codex/config.toml``, sharing the file with the ``[ai_dotfiles]``
    settings region. A server name a domain declares but the user has
    already hand-authored is left as the user's and reported.
    """
    result = codex_config.write_codex_mcp(
        project_root, collect_mcp_fragments(packages, catalog)
    )
    if result.status == "created":
        ui.success("config.toml ([mcp_servers] created)")
    elif result.status == "updated":
        ui.success("config.toml ([mcp_servers] updated)")
    for name in sorted(result.collisions):
        ui.warn(
            f"MCP server '{name}' already exists in .codex/config.toml "
            f"(user-owned). Keeping user version."
        )
