"""``ai-dotfiles install`` — symlink creation and settings assembly.

Thin wrapper over the ``core`` modules. Two modes:

* ``ai-dotfiles install`` — project install: reads ``ai-dotfiles.json`` at
  the project root, links packages into ``<root>/.claude/``, and writes
  ``<root>/.claude/settings.json`` from domain fragments.
* ``ai-dotfiles install -g`` — global install: links ``~/.ai-dotfiles/global/``
  files into ``~/.claude/``, then reads ``global.json`` and links its
  packages into ``~/.claude/``.
"""

from __future__ import annotations

from pathlib import Path

import click

from ai_dotfiles import ui
from ai_dotfiles.core import elements, manifest, paths, settings_merge, symlinks
from ai_dotfiles.core.elements import Element, ElementType
from ai_dotfiles.core.errors import AiDotfilesError, ConfigError
from ai_dotfiles.core.gitignore import collect_managed_paths, sync_gitignore
from ai_dotfiles.core.mcp_apply import rebuild_claude_config


@click.command("install")
@click.option(
    "-g",
    "--global",
    "is_global",
    is_flag=True,
    help="Install the global manifest instead of the project one.",
)
@click.option(
    "--prune",
    is_flag=True,
    help=(
        "After linking, remove stale symlinks that point into ai-dotfiles "
        "storage but no longer resolve (e.g. after renaming or deleting a "
        "catalog element)."
    ),
)
@click.option(
    "--no-gitignore",
    is_flag=True,
    help="Do not touch .gitignore even if the project manages vendored "
    "symlink paths.",
)
def install(is_global: bool, prune: bool, no_gitignore: bool) -> None:
    """Install packages from the manifest (project by default, or global)."""
    try:
        if is_global:
            _install_global(prune=prune)
        else:
            _install_project(prune=prune, no_gitignore=no_gitignore)
    except AiDotfilesError as exc:
        ui.error(str(exc))
        raise SystemExit(exc.exit_code) from exc


def _install_project(*, prune: bool = False, no_gitignore: bool = False) -> None:
    root = paths.find_project_root()
    if root is None or not paths.project_manifest_path(root).is_file():
        raise ConfigError("ai-dotfiles.json not found. Run 'ai-dotfiles init' first.")

    manifest_path = paths.project_manifest_path(root)
    packages = manifest.get_packages(manifest_path)

    ui.info(f"Installing from {manifest_path.name}...")

    catalog = paths.catalog_dir()
    backup = paths.backup_dir()
    claude_dir = paths.project_claude_dir(root)
    claude_dir.mkdir(parents=True, exist_ok=True)

    parsed: list[Element] = []
    linked_items: list[str] = []
    fragment_count = 0
    settings_written = False

    if packages:
        parsed = elements.parse_elements(packages)
        for element in parsed:
            elements.validate_element_exists(element, catalog)

        for element in parsed:
            linked_items.extend(_link_element(element, claude_dir, catalog, backup))

        fragments = settings_merge.collect_domain_fragments(packages, catalog)
        fragment_count = len(fragments)

    # Always regenerate settings + MCP, even on an empty manifest, so any
    # stale state left by a crashed `add` / `remove` gets cleaned up.
    rebuild_claude_config(
        manifest_path=manifest_path,
        claude_dir=claude_dir,
        catalog=catalog,
        project_root=root,
        backup_root=backup,
        warn=ui.warn,
    )
    settings_written = (claude_dir / "settings.json").exists()

    if prune:
        _report_pruned(claude_dir, paths.storage_root())

    _maybe_sync_gitignore(
        project_root=root,
        claude_dir=claude_dir,
        manifest_path=manifest_path,
        no_gitignore=no_gitignore,
    )

    if not packages:
        ui.info("Nothing to install.")
        return

    _print_summary(parsed, linked_items, settings_written, fragment_count)


def _install_global(*, prune: bool = False) -> None:
    storage = paths.storage_root()
    if not storage.is_dir():
        raise ConfigError(
            f"Storage not found: {storage}. Run 'ai-dotfiles init -g' first."
        )

    claude_dir = paths.claude_global_dir()
    claude_dir.mkdir(parents=True, exist_ok=True)
    backup = paths.backup_dir()
    global_dir = paths.global_dir()

    ui.info("Installing global configuration...")

    global_messages: list[str] = []
    if global_dir.is_dir():
        global_messages = symlinks.link_global_files(global_dir, claude_dir, backup)
        for msg in global_messages:
            ui.success(msg)

    manifest_path = paths.global_manifest_path()
    packages = manifest.get_packages(manifest_path)

    linked_items: list[str] = []
    parsed: list[Element] = []
    settings_written = False
    fragment_count = 0

    if packages:
        catalog = paths.catalog_dir()
        parsed = elements.parse_elements(packages)
        for element in parsed:
            elements.validate_element_exists(element, catalog)

        for element in parsed:
            linked_items.extend(_link_element(element, claude_dir, catalog, backup))

        fragments = settings_merge.collect_domain_fragments(packages, catalog)
        fragment_count = len(fragments)
        if fragments:
            # Merge into existing global settings.json if present to avoid
            # clobbering settings linked in from global/.
            settings_path = claude_dir / "settings.json"
            base = None
            if settings_path.is_file() and not settings_path.is_symlink():
                base = settings_merge.load_fragment(settings_path)
            assembled = settings_merge.assemble_settings(fragments, base=base)
            if assembled:
                # Remove a symlinked settings.json so we don't write through.
                if settings_path.is_symlink():
                    settings_path.unlink()
                settings_merge.write_settings(assembled, settings_path)
                settings_written = True

    if prune:
        _report_pruned(claude_dir, storage)

    _print_summary(
        parsed,
        linked_items,
        settings_written,
        fragment_count,
        extra_global=len(global_messages),
    )


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
    if not manifest.get_flag(paths.global_manifest_path(), "manage_gitignore", True):
        return
    managed = collect_managed_paths(claude_dir, paths.storage_root())
    sync_gitignore(project_root, managed)


def _report_pruned(claude_dir: Path, storage: Path) -> None:
    """Run prune_dangling and print one line per removed symlink."""
    removed = symlinks.prune_dangling(claude_dir, storage)
    if not removed:
        return
    ui.info(
        f"Pruned {len(removed)} dangling symlink{'s' if len(removed) != 1 else ''}:"
    )
    for label in removed:
        ui.info(f"  - {label}")


def _link_element(
    element: Element, claude_dir: Path, catalog: Path, backup: Path
) -> list[str]:
    """Link a single element and return human-readable entries."""
    entries: list[str] = []
    if element.type is ElementType.DOMAIN:
        source = elements.resolve_source_path(element, catalog)
        messages = symlinks.link_domain(source, claude_dir, backup)
        count = len(messages)
        ui.success(f"@{element.name} ({count} item{'s' if count != 1 else ''})")
        entries.append(f"@{element.name}")
        return entries

    pairs = elements.resolve_target_paths(element, claude_dir, catalog)
    for source, target in pairs:
        symlinks.link_standalone(source, target, backup)
    ui.success(element.raw)
    entries.append(element.raw)
    return entries


def _print_summary(
    parsed: list[Element],
    linked_items: list[str],
    settings_written: bool,
    fragment_count: int,
    extra_global: int = 0,
) -> None:
    if settings_written:
        noun = "fragment" if fragment_count == 1 else "fragments"
        ui.info(f"  Settings: merged {fragment_count} domain {noun} -> settings.json")
    pkg_count = len(parsed)
    if pkg_count == 0 and extra_global == 0:
        ui.info("Nothing to install.")
        return
    if pkg_count == 0:
        ui.info(f"Linked {extra_global} global file{'s' if extra_global != 1 else ''}.")
        return
    ui.info(f"Installed {pkg_count} package{'s' if pkg_count != 1 else ''}.")
