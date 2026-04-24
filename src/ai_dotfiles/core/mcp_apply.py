"""Apply domain MCP fragments to ``<project>/.mcp.json`` + ``settings.json``.

Single entry point used by ``add``, ``remove`` and ``install``. It:

1. Reads the manifest and collects ``mcp.fragment.json`` files from
   currently-installed domains.
2. Merges them with the user's existing ``.mcp.json`` (preserving
   user-authored servers, dropping stale domain-owned ones).
3. Updates ``settings.json`` with ``mcp__<server>__*`` permissions and
   an ``enabledMcpjsonServers`` allowlist covering only domain-owned
   servers.
4. Backs up the previous ``.mcp.json`` before every mutation.
5. Writes or deletes ``.mcp.json`` and the ownership state file.

The module takes a ``warn`` callable so it can run without importing
``ai_dotfiles.ui`` (keeping ``core`` UI-free).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ai_dotfiles.core import manifest
from ai_dotfiles.core.mcp_merge import (
    assemble_mcp_servers,
    backup_mcp_json,
    collect_mcp_fragments,
    derive_mcp_permissions,
    detect_collisions,
    load_mcp_fragment,
    merge_with_existing_mcp,
    warn_missing_npm_requires,
    warn_unset_env_vars,
    write_mcp_json,
)
from ai_dotfiles.core.mcp_ownership import (
    delete_ownership,
    load_ownership,
    save_ownership,
)
from ai_dotfiles.core.settings_merge import (
    assemble_settings,
    collect_domain_fragments,
    load_fragment,
    write_settings,
)


def rebuild_claude_config(
    *,
    manifest_path: Path,
    claude_dir: Path,
    catalog: Path,
    project_root: Path,
    backup_root: Path,
    warn: Callable[[str], None],
) -> bool:
    """Rebuild ``settings.json`` and ``.mcp.json`` from domain fragments.

    Returns ``True`` if either file was written or deleted. The caller
    decides whether to log a summary based on the return value and the
    presence of domain specifiers in the manifest.
    """
    packages = manifest.get_packages(manifest_path)

    settings_fragments = collect_domain_fragments(packages, catalog)
    settings = assemble_settings(settings_fragments)

    mcp_fragments = collect_mcp_fragments(packages, catalog)
    new_servers, new_ownership = assemble_mcp_servers(mcp_fragments)

    mcp_path = project_root / ".mcp.json"
    previous_ownership = load_ownership(claude_dir)
    existing = load_mcp_fragment(mcp_path) if mcp_path.exists() else {}

    for name in detect_collisions(new_servers, existing, previous_ownership):
        warn(
            f"MCP server '{name}' already exists in .mcp.json (user-owned). "
            "Keeping user version."
        )

    merged = merge_with_existing_mcp(new_servers, existing, previous_ownership)
    effective_servers = merged.get("mcpServers", {})

    # Capture user-authored enabledMcpjsonServers entries before we rewrite
    # settings. An entry is user-authored if it is NOT in the previous
    # ownership map (either a manual edit, or a domain the user removed
    # but whose allowlist line they chose to keep — rare, but honoured).
    settings_path = claude_dir / "settings.json"
    prior_owned_names = set(previous_ownership.keys())
    user_allowlist: list[str] = []
    if settings_path.exists():
        existing_settings = load_fragment(settings_path)
        prior_list = existing_settings.get("enabledMcpjsonServers")
        if isinstance(prior_list, list):
            user_allowlist = [
                n
                for n in prior_list
                if isinstance(n, str) and n not in prior_owned_names
            ]

    domain_owned = [name for name in effective_servers if name in new_ownership]
    if domain_owned:
        perms = settings.setdefault("permissions", {}).setdefault("allow", [])
        for perm in derive_mcp_permissions(domain_owned):
            if perm not in perms:
                perms.append(perm)
        combined = list(user_allowlist)
        for name in domain_owned:
            if name not in combined:
                combined.append(name)
        settings["enabledMcpjsonServers"] = combined
    elif user_allowlist:
        # Nothing domain-owned left, but user-authored entries survive.
        settings["enabledMcpjsonServers"] = user_allowlist

    if settings:
        write_settings(settings, settings_path)
    elif settings_path.exists() or settings_path.is_symlink():
        # No fragments at all -> drop generated settings.json.
        settings_path.unlink()

    # Write order matters for crash recovery. Two files (.mcp.json and the
    # ownership map) are updated together but cannot be made atomic across
    # both. We pick an order that is self-healing on the next run:
    #
    #   * On upsert: ownership FIRST, then .mcp.json. If the .mcp.json write
    #     fails mid-flight, the next rebuild sees a server it owns that is
    #     absent from .mcp.json — merge_with_existing_mcp will simply add
    #     it from new_servers.
    #   * On delete: .mcp.json FIRST, then ownership. If the ownership
    #     delete fails, the next rebuild sees ownership for servers that
    #     are no longer declared — merge drops them.
    mcp_changed = False
    if effective_servers:
        save_ownership(claude_dir, new_ownership)
        if mcp_path.exists():
            backup_mcp_json(mcp_path, backup_root, project_root.name)
        write_mcp_json(merged, mcp_path)
        warn_unset_env_vars(effective_servers, warn)
        warn_missing_npm_requires(mcp_fragments, project_root, warn)
        mcp_changed = True
    else:
        if mcp_path.exists():
            backup_mcp_json(mcp_path, backup_root, project_root.name)
            mcp_path.unlink()
            mcp_changed = True
        delete_ownership(claude_dir)

    return bool(settings) or mcp_changed
