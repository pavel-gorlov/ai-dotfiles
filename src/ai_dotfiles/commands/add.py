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
from ai_dotfiles.core.elements import (
    Element,
    ElementType,
    parse_elements,
    resolve_source_path,
    resolve_target_paths,
    validate_element_exists,
)
from ai_dotfiles.core.errors import AiDotfilesError, ConfigError
from ai_dotfiles.core.mcp_apply import rebuild_claude_config
from ai_dotfiles.core.paths import (
    backup_dir,
    catalog_dir,
    claude_global_dir,
    find_project_root,
    global_manifest_path,
    project_claude_dir,
    project_manifest_path,
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


def _link_element(element: Element, claude_dir: Path, catalog: Path) -> None:
    """Create symlinks for a single element into ``claude_dir``."""
    pairs = resolve_target_paths(element, claude_dir, catalog)
    for source, target in pairs:
        symlinks.safe_symlink(source, target, backup_dir())


def _rebuild_settings(manifest_path: Path, claude_dir: Path, catalog: Path) -> None:
    """Reassemble ``settings.json`` from all domain fragments in the manifest.

    Used for the global scope, where MCP is not (yet) wired up.
    """
    packages = manifest.get_packages(manifest_path)
    fragments = collect_domain_fragments(packages, catalog)
    settings = assemble_settings(fragments)
    write_settings(settings, claude_dir / "settings.json")


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
def add(packages: tuple[str, ...], is_global: bool) -> None:
    """Add PACKAGES to the manifest and link them into the Claude dir."""
    try:
        elements = parse_elements(list(packages))

        catalog = catalog_dir()
        for element in elements:
            validate_element_exists(element, catalog)

        manifest_path, claude_dir, project_root = _resolve_scope(is_global)
        claude_dir.mkdir(parents=True, exist_ok=True)

        raw_items = [element.raw for element in elements]
        added = manifest.add_packages(manifest_path, raw_items)
        added_set = set(added)

        manifest_name = manifest_path.name

        if not added:
            ui.info(f"All packages already installed in {manifest_name}")
            return

        ui.info(f"Added to {manifest_name}:")
        for element in elements:
            if element.raw in added_set:
                source = resolve_source_path(element, catalog)
                _ = source  # source already validated above
                _link_element(element, claude_dir, catalog)
                ui.success(element.raw)
            else:
                ui.info(f"  ~ {element.raw} (already installed)")

        has_domain = any(el.type is ElementType.DOMAIN for el in elements)
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

    except AiDotfilesError as exc:
        ui.error(str(exc))
        sys.exit(exc.exit_code)
