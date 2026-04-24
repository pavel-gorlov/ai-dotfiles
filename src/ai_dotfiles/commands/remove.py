"""``ai-dotfiles remove`` — drop packages from manifest and unlink them."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from ai_dotfiles import ui
from ai_dotfiles.core import manifest, symlinks
from ai_dotfiles.core.completions import (
    complete_installed_specifiers,
    make_completer,
)
from ai_dotfiles.core.elements import (
    Element,
    ElementType,
    parse_elements,
    resolve_source_path,
    resolve_target_paths,
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
    write_settings,
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


def _unlink_element(element: Element, claude_dir: Path, catalog: Path) -> None:
    """Remove symlinks created for ``element``."""
    if element.type is ElementType.DOMAIN:
        source = resolve_source_path(element, catalog)
        if source.exists():
            symlinks.unlink_domain(source, claude_dir)
            return
        # Catalog entry missing — best-effort: walk known target paths.
        for _, target in resolve_target_paths(element, claude_dir, catalog):
            symlinks.unlink_standalone(target)
        return

    for _, target in resolve_target_paths(element, claude_dir, catalog):
        symlinks.unlink_standalone(target)


def _rebuild_settings(manifest_path: Path, claude_dir: Path, catalog: Path) -> None:
    """Reassemble ``settings.json`` from remaining domain fragments."""
    packages = manifest.get_packages(manifest_path)
    fragments = collect_domain_fragments(packages, catalog)
    settings_path = claude_dir / "settings.json"

    if not fragments:
        # No fragments left; remove any previously-generated file.
        if settings_path.exists() or settings_path.is_symlink():
            settings_path.unlink()
        return

    settings = assemble_settings(fragments)
    write_settings(settings, settings_path)


def _maybe_sync_gitignore(
    *,
    project_root: Path | None,
    claude_dir: Path,
    manifest_path: Path,
    no_gitignore: bool,
) -> None:
    """Regenerate the managed .gitignore block unless opted out."""
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
    shell_complete=make_completer(complete_installed_specifiers),
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
def remove(packages: tuple[str, ...], is_global: bool, no_gitignore: bool) -> None:
    """Remove PACKAGES from the manifest and unlink their elements."""
    try:
        elements = parse_elements(list(packages))

        catalog = catalog_dir()
        manifest_path, claude_dir, project_root = _resolve_scope(is_global)

        raw_items = [element.raw for element in elements]
        removed = manifest.remove_packages(manifest_path, raw_items)
        removed_set = set(removed)

        manifest_name = manifest_path.name

        if not removed:
            ui.warn(f"None of these packages were installed in {manifest_name}")
            return

        ui.info(f"Removed from {manifest_name}:")
        for element in elements:
            if element.raw in removed_set:
                _unlink_element(element, claude_dir, catalog)
                ui.info(f"  - {element.raw}")
            else:
                ui.info(f"  ~ {element.raw} (not installed)")

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
        had_domain = any(
            el.type is ElementType.DOMAIN for el in elements if el.raw in removed_set
        )
        if had_domain:
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
