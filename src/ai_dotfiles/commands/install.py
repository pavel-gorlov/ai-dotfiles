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


@click.command("install")
@click.option(
    "-g",
    "--global",
    "is_global",
    is_flag=True,
    help="Install the global manifest instead of the project one.",
)
def install(is_global: bool) -> None:
    """Install packages from the manifest (project by default, or global)."""
    try:
        if is_global:
            _install_global()
        else:
            _install_project()
    except AiDotfilesError as exc:
        ui.error(str(exc))
        raise SystemExit(exc.exit_code) from exc


def _install_project() -> None:
    root = paths.find_project_root()
    if root is None or not paths.project_manifest_path(root).is_file():
        raise ConfigError("ai-dotfiles.json not found. Run 'ai-dotfiles init' first.")

    manifest_path = paths.project_manifest_path(root)
    packages = manifest.get_packages(manifest_path)

    ui.info(f"Installing from {manifest_path.name}...")

    if not packages:
        ui.info("Nothing to install.")
        return

    catalog = paths.catalog_dir()
    backup = paths.backup_dir()
    claude_dir = paths.project_claude_dir(root)
    claude_dir.mkdir(parents=True, exist_ok=True)

    parsed = elements.parse_elements(packages)
    for element in parsed:
        elements.validate_element_exists(element, catalog)

    linked_items: list[str] = []
    for element in parsed:
        linked_items.extend(_link_element(element, claude_dir, catalog, backup))

    fragments = settings_merge.collect_domain_fragments(packages, catalog)
    settings_written = False
    if fragments:
        assembled = settings_merge.assemble_settings(fragments)
        if assembled:
            settings_merge.write_settings(assembled, claude_dir / "settings.json")
            settings_written = True

    _print_summary(parsed, linked_items, settings_written, len(fragments))


def _install_global() -> None:
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

    _print_summary(
        parsed,
        linked_items,
        settings_written,
        fragment_count,
        extra_global=len(global_messages),
    )


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
