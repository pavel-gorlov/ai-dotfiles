# Subtask 03: skip-list + `add` / `remove` / `install` wiring

Glue subtask. Imports subtask 01 + 02. Modifies five files. Must land
before subtask 04's integration tests.

## Goal

1. Teach the element/symlink system to skip `mcp.fragment.json` (so it
   is not linked into `.claude/`).
2. Replace each command's `_rebuild_settings` with a new local helper
   `_rebuild_claude_config` that rebuilds BOTH `settings.json` AND
   `.mcp.json` in one pass, coordinating the allowlist
   (`enabledMcpjsonServers`) and permissions across both files.

## File scope (exclusive)

- `src/ai_dotfiles/core/elements.py`         (skip-list only)
- `src/ai_dotfiles/core/symlinks.py`         (skip-list only)
- `src/ai_dotfiles/commands/add.py`
- `src/ai_dotfiles/commands/remove.py`
- `src/ai_dotfiles/commands/install.py`

## Do NOT touch

- `core/mcp_merge.py`, `core/mcp_ownership.py` — frozen (subtasks 01/02).
- `core/settings_merge.py` — leave untouched; we layer MCP on top of it
  at the command level, not inside settings_merge.
- `commands/*` other than the three above.
- Any test file — subtask 04 writes tests.

## Hard rules

- mypy `--strict`; absolute imports; `ui.warn` for warnings.
- Keep the three command-local `_rebuild_claude_config` helpers as
  parallel copies (mirror existing `_rebuild_settings` duplication
  — do not extract to a shared module here; scope is MVP minimal diff).
- `_install_global` does NOT call the new helper (MCP global scope is
  out of MVP). Leave the existing global path untouched.
- First-time collision in `.mcp.json` → call `ui.warn` with the exact
  text:
  `"MCP server '<name>' already exists in .mcp.json (user-owned). Keeping user version."`
- Allowlist behavior: auto-populate `enabledMcpjsonServers` with the
  list of DOMAIN-OWNED server names only; preserve user-authored entries
  in that array (if any).

## Skip-list changes (exact)

### `src/ai_dotfiles/core/elements.py:39`

```python
_DOMAIN_SKIP_FILES: frozenset[str] = frozenset(
    {"README.md", "settings.fragment.json", "mcp.fragment.json"}
)
```

### `src/ai_dotfiles/core/symlinks.py:17`

```python
_SKIP_NAMES: frozenset[str] = frozenset(
    {"README.md", "settings.fragment.json", "mcp.fragment.json"}
)
```

(If the actual constant name in `symlinks.py` differs, match whatever
is there — we verified `_DOMAIN_SKIP_FILES` in `elements.py` during
exploration; confirm at implementation time.)

## Helper sketch (same in all three command files)

```python
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


def _rebuild_claude_config(
    manifest_path: Path,
    claude_dir: Path,
    catalog: Path,
    project_root: Path,
) -> None:
    packages = manifest.get_packages(manifest_path)

    settings_fragments = collect_domain_fragments(packages, catalog)
    settings = assemble_settings(settings_fragments)

    mcp_fragments = collect_mcp_fragments(packages, catalog)
    new_servers, new_ownership = assemble_mcp_servers(mcp_fragments)

    mcp_path = project_root / ".mcp.json"
    previous_ownership = load_ownership(claude_dir)
    existing = load_mcp_fragment(mcp_path) if mcp_path.exists() else {}

    for name in detect_collisions(new_servers, existing, previous_ownership):
        ui.warn(
            f"MCP server '{name}' already exists in .mcp.json (user-owned). "
            f"Keeping user version."
        )

    merged = merge_with_existing_mcp(new_servers, existing, previous_ownership)
    effective_servers = merged.get("mcpServers", {})

    domain_owned = [n for n in effective_servers if n in new_ownership]
    if domain_owned:
        perms = settings.setdefault("permissions", {}).setdefault("allow", [])
        for perm in derive_mcp_permissions(domain_owned):
            if perm not in perms:
                perms.append(perm)
        existing_list = settings.get("enabledMcpjsonServers", [])
        if not isinstance(existing_list, list):
            existing_list = []
        combined = list(existing_list)
        for name in domain_owned:
            if name not in combined:
                combined.append(name)
        settings["enabledMcpjsonServers"] = combined
    else:
        prior_owned = set(previous_ownership.keys())
        current = settings.get("enabledMcpjsonServers")
        if isinstance(current, list):
            remaining = [n for n in current if n not in prior_owned]
            if remaining:
                settings["enabledMcpjsonServers"] = remaining
            else:
                settings.pop("enabledMcpjsonServers", None)

    write_settings(settings, claude_dir / "settings.json")

    if effective_servers:
        if mcp_path.exists():
            backup_mcp_json(mcp_path, backup_dir(), project_root.name)
        write_mcp_json(merged, mcp_path)
        save_ownership(claude_dir, new_ownership)
        warn_unset_env_vars(effective_servers, ui.warn)
        warn_missing_npm_requires(mcp_fragments, project_root, ui.warn)
    else:
        if mcp_path.exists():
            backup_mcp_json(mcp_path, backup_dir(), project_root.name)
            mcp_path.unlink()
        delete_ownership(claude_dir)
```

## Wiring per command

### `commands/add.py`

- Replace `_rebuild_settings` with the above (rename definition too).
- Threading `project_root`: `_resolve_scope` currently returns
  `(manifest_path, claude_dir)`. For the project branch, re-call
  `find_project_root()` at the callsite — simpler than changing the
  tuple shape. For the global branch the new helper must NOT be called;
  fall back to the existing `_rebuild_settings` behavior (i.e. keep
  calling just `assemble_settings` + `write_settings` for global).
- Suggestion: keep a small `_rebuild_settings_only` helper for the
  global branch, or branch inline.

### `commands/remove.py`

- Same rename and branch rule.

### `commands/install.py`

- Inside `_install_project`, after the existing settings merge block,
  call `_rebuild_claude_config`. (Alternatively, replace that block
  with the new helper — cleaner; the helper already calls
  `write_settings`.)
- `_install_global` is NOT modified.

## Import hygiene

- Do not import `ui` inside the core modules. Command modules pass
  `ui.warn` (or `ui.info`/`ui.error`) into the core functions.

## Definition of Done

1. `poetry run pytest -q` — existing suite stays green (no MCP
   integration tests yet — those come in 04, but existing `add_remove`,
   `install`, settings-merge tests must not regress).
2. `poetry run mypy src/` — clean
3. `poetry run ruff check src/ tests/` — clean
4. `poetry run black --check src/ tests/` — clean
5. `poetry run pre-commit run --all-files` — clean
6. Manual: in a throwaway project, `ai-dotfiles add @<some-existing-domain>`
   should continue to write the same `settings.json` as before
   (no `.mcp.json` side-effects when no domain has
   `mcp.fragment.json`).

Do NOT commit.
