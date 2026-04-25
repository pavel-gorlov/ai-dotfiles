"""``ai-dotfiles add`` — append packages to manifest and link them.

Thin wrapper over ``core``:

1. Parse specifiers and validate they exist in the catalog.
2. Append to manifest (``add_packages`` skips duplicates).
3. Symlink newly added elements into the Claude dir.
4. Reassemble ``settings.json`` from ALL packages in the manifest.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from ai_dotfiles import ui
from ai_dotfiles.core import manifest, symlinks
from ai_dotfiles.core.completions import (
    complete_available_specifiers,
    make_completer,
)
from ai_dotfiles.core.dependencies import resolve_transitive
from ai_dotfiles.core.elements import (
    Element,
    ElementType,
    parse_elements,
    resolve_target_paths,
    validate_element_exists,
)
from ai_dotfiles.core.errors import AiDotfilesError, ConfigError
from ai_dotfiles.core.gitignore import collect_managed_paths, sync_gitignore
from ai_dotfiles.core.mcp_apply import rebuild_claude_config
from ai_dotfiles.core.paths import (
    backup_dir,
    catalog_dir,
    claude_global_dir,
    find_project_root,
    global_manifest_path,
    project_claude_dir,
    project_manifest_path,
    storage_root,
)
from ai_dotfiles.core.settings_merge import (
    assemble_settings,
    collect_domain_fragments,
    collect_fragment_contributions,
    load_fragment,
    strip_owned,
    write_settings,
)
from ai_dotfiles.core.settings_ownership import (
    delete_settings_ownership,
    load_settings_ownership,
    save_settings_ownership,
)
from ai_dotfiles.core.settings_ownership import (
    is_empty as settings_ownership_is_empty,
)


def _resolve_scope(is_global: bool) -> tuple[Path, Path, Path | None]:
    """Return ``(manifest_path, claude_dir, project_root)`` for the scope.

    ``project_root`` is ``None`` for the global scope.
    """
    if is_global:
        return global_manifest_path(), claude_global_dir(), None

    root = find_project_root()
    if root is None:
        raise ConfigError(
            "No project found. Run 'ai-dotfiles init' first or pass -g for global."
        )
    return project_manifest_path(root), project_claude_dir(root), root


def _link_element(element: Element, claude_dir: Path, catalog: Path) -> None:
    """Create symlinks for a single element into ``claude_dir``."""
    pairs = resolve_target_paths(element, claude_dir, catalog)
    for source, target in pairs:
        symlinks.safe_symlink(source, target, backup_dir())


def _rebuild_settings(manifest_path: Path, claude_dir: Path, catalog: Path) -> None:
    """Reassemble ``settings.json`` from fragments while preserving user edits.

    Used for the global scope (no MCP wiring). Strips entries that the
    previous rebuild owned (per ownership file), then merges current
    fragments into the user-only base, then records new ownership.
    """
    packages = manifest.get_packages(manifest_path)
    fragments = collect_domain_fragments(packages, catalog)
    settings_path = claude_dir / "settings.json"

    existing = (
        load_fragment(settings_path)
        if settings_path.is_file() and not settings_path.is_symlink()
        else {}
    )
    prev_ownership = load_settings_ownership(claude_dir)
    user_base = strip_owned(existing, prev_ownership)
    settings = assemble_settings(fragments, base=user_base)
    new_ownership = collect_fragment_contributions(fragments)

    if settings:
        if settings_path.is_symlink():
            settings_path.unlink()
        write_settings(settings, settings_path)
    elif settings_path.exists() or settings_path.is_symlink():
        settings_path.unlink()

    if settings_ownership_is_empty(new_ownership):
        delete_settings_ownership(claude_dir)
    else:
        save_settings_ownership(claude_dir, new_ownership)


def _maybe_sync_gitignore(
    *,
    project_root: Path | None,
    claude_dir: Path,
    manifest_path: Path,
    no_gitignore: bool,
) -> None:
    """Regenerate the managed .gitignore block unless opted out.

    No-op in the global scope or when the user disabled the feature via
    ``--no-gitignore`` or ``manage_gitignore: false`` in either the
    project or the global manifest (project precedence).
    """
    if project_root is None or no_gitignore:
        return
    if not manifest.get_flag(manifest_path, "manage_gitignore", True):
        return
    if not manifest.get_flag(global_manifest_path(), "manage_gitignore", True):
        return
    paths = collect_managed_paths(claude_dir, storage_root())
    sync_gitignore(project_root, paths)


@click.command()
@click.argument(
    "packages",
    nargs=-1,
    required=True,
    shell_complete=make_completer(complete_available_specifiers),
)
@click.option(
    "-g", "--global", "is_global", is_flag=True, help="Operate on global manifest."
)
@click.option(
    "--no-gitignore",
    is_flag=True,
    help="Do not touch .gitignore even if the project manages vendored "
    "symlink paths.",
)
def add(packages: tuple[str, ...], is_global: bool, no_gitignore: bool) -> None:
    """Add PACKAGES to the manifest and link them into the Claude dir."""
    try:
        user_elements = parse_elements(list(packages))

        catalog = catalog_dir()
        for element in user_elements:
            validate_element_exists(element, catalog)

        manifest_path, claude_dir, project_root = _resolve_scope(is_global)
        claude_dir.mkdir(parents=True, exist_ok=True)

        # Expand each user-supplied element to include its transitive deps,
        # in topological order (deps appear first). The user's explicit
        # ones come at the end of each subtree so the manifest reads
        # naturally — base layer first, leaf last.
        expanded = resolve_transitive(catalog, user_elements)
        explicit_set = {el.raw for el in user_elements}

        raw_items = [element.raw for element in expanded]
        added = manifest.add_packages(manifest_path, raw_items)
        added_set = set(added)

        manifest_name = manifest_path.name

        if not added:
            ui.info(f"All packages already installed in {manifest_name}")
            return

        ui.info(f"Added to {manifest_name}:")
        for element in expanded:
            if element.raw not in added_set:
                continue
            _link_element(element, claude_dir, catalog)
            if element.raw in explicit_set:
                ui.success(element.raw)
            else:
                ui.success(f"{element.raw} (pulled in as a dependency)")

        has_domain = any(el.type is ElementType.DOMAIN for el in expanded)
        if project_root is not None:
            rebuild_claude_config(
                manifest_path=manifest_path,
                claude_dir=claude_dir,
                catalog=catalog,
                project_root=project_root,
                backup_root=backup_dir(),
                warn=ui.warn,
            )
        else:
            _rebuild_settings(manifest_path, claude_dir, catalog)
        if has_domain:
            ui.info(f"Settings: rebuilt {claude_dir.name}/settings.json")

        _maybe_sync_gitignore(
            project_root=project_root,
            claude_dir=claude_dir,
            manifest_path=manifest_path,
            no_gitignore=no_gitignore,
        )

    except AiDotfilesError as exc:
        ui.error(str(exc))
        sys.exit(exc.exit_code)
