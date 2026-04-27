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
from ai_dotfiles.core.dependencies import resolve_transitive
from ai_dotfiles.core.elements import Element, ElementType
from ai_dotfiles.core.errors import AiDotfilesError, ConfigError, MissingDependencyError
from ai_dotfiles.core.gitignore import collect_managed_paths, sync_gitignore
from ai_dotfiles.core.mcp_apply import rebuild_claude_config
from ai_dotfiles.core.runtime import (
    ProvisionResult,
    bin_dir_on_path,
    provision_domain_runtime,
)
from ai_dotfiles.core.settings_ownership import (
    delete_settings_ownership,
    load_settings_ownership,
    save_settings_ownership,
)
from ai_dotfiles.core.settings_ownership import (
    is_empty as settings_ownership_is_empty,
)


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
@click.option(
    "--strict-deps",
    is_flag=True,
    help=(
        "Refuse to install if the manifest is missing any transitive "
        "dependencies. Without this flag, missing deps are auto-added "
        "to the manifest and a warning is printed."
    ),
)
def install(
    is_global: bool, prune: bool, no_gitignore: bool, strict_deps: bool
) -> None:
    """Install packages from the manifest (project by default, or global)."""
    try:
        if is_global:
            _install_global(prune=prune, strict_deps=strict_deps)
        else:
            _install_project(
                prune=prune, no_gitignore=no_gitignore, strict_deps=strict_deps
            )
    except AiDotfilesError as exc:
        ui.error(str(exc))
        raise SystemExit(exc.exit_code) from exc


def _expand_manifest_deps(
    manifest_path: Path,
    catalog: Path,
    *,
    strict_deps: bool,
) -> list[str]:
    """Verify (and optionally repair) transitive deps of the manifest.

    Reads the current manifest, expands transitive deps, and:
      * raises :class:`MissingDependencyError` if ``strict_deps`` is set
        and the closure contains entries not in the manifest;
      * otherwise, appends missing entries to the manifest and warns
        once per pulled-in element.

    Returns the post-expansion list of packages.
    """
    packages = manifest.get_packages(manifest_path)
    if not packages:
        return packages

    parsed = elements.parse_elements(packages)
    for element in parsed:
        elements.validate_element_exists(element, catalog)

    expanded = resolve_transitive(catalog, parsed)
    existing_set = set(packages)
    missing = [el for el in expanded if el.raw not in existing_set]
    if not missing:
        return packages

    if strict_deps:
        names = ", ".join(el.raw for el in missing)
        raise MissingDependencyError(
            f"Manifest is missing transitive dependencies: {names}. "
            "Add them with 'ai-dotfiles add', or rerun without --strict-deps "
            "to auto-add them."
        )

    for el in missing:
        ui.warn(
            f"Pulling in {el.raw} (required by an entry already in the "
            "manifest); adding it to the manifest."
        )
    manifest.add_packages(manifest_path, [el.raw for el in missing])
    return manifest.get_packages(manifest_path)


def _install_project(
    *,
    prune: bool = False,
    no_gitignore: bool = False,
    strict_deps: bool = False,
) -> None:
    root = paths.find_project_root()
    if root is None or not paths.project_manifest_path(root).is_file():
        raise ConfigError("ai-dotfiles.json not found. Run 'ai-dotfiles init' first.")

    manifest_path = paths.project_manifest_path(root)

    ui.info(f"Installing from {manifest_path.name}...")

    catalog = paths.catalog_dir()
    backup = paths.backup_dir()
    claude_dir = paths.project_claude_dir(root)
    claude_dir.mkdir(parents=True, exist_ok=True)

    packages = _expand_manifest_deps(manifest_path, catalog, strict_deps=strict_deps)

    parsed: list[Element] = []
    linked_items: list[str] = []
    fragment_count = 0
    settings_written = False

    any_shim = False
    if packages:
        parsed = elements.parse_elements(packages)
        for element in parsed:
            elements.validate_element_exists(element, catalog)

        for element in parsed:
            linked_items.extend(_link_element(element, claude_dir, catalog, backup))

        any_shim = _provision_runtimes(parsed, catalog)

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
    _maybe_print_path_hint(any_shim)


def _install_global(*, prune: bool = False, strict_deps: bool = False) -> None:
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
    packages = _expand_manifest_deps(
        manifest_path, paths.catalog_dir(), strict_deps=strict_deps
    )

    linked_items: list[str] = []
    parsed: list[Element] = []
    settings_written = False
    fragment_count = 0

    any_shim = False
    if packages:
        catalog = paths.catalog_dir()
        parsed = elements.parse_elements(packages)
        for element in parsed:
            elements.validate_element_exists(element, catalog)

        for element in parsed:
            linked_items.extend(_link_element(element, claude_dir, catalog, backup))

        any_shim = _provision_runtimes(parsed, catalog)

        fragments = settings_merge.collect_domain_fragments(packages, catalog)
        fragment_count = len(fragments)
        # Always rebuild settings.json with ownership-aware merge so
        # stale entries from prior installs get cleaned up and user
        # edits are preserved.
        settings_path = claude_dir / "settings.json"
        existing: dict[str, object] = {}
        if settings_path.is_file() and not settings_path.is_symlink():
            existing = settings_merge.load_fragment(settings_path)
        prev_ownership = load_settings_ownership(claude_dir)
        user_base = settings_merge.strip_owned(existing, prev_ownership)
        assembled = settings_merge.assemble_settings(fragments, base=user_base)
        new_ownership = settings_merge.collect_fragment_contributions(fragments)
        if assembled:
            if settings_path.is_symlink():
                settings_path.unlink()
            settings_merge.write_settings(assembled, settings_path)
            settings_written = True
        elif settings_path.exists() or settings_path.is_symlink():
            settings_path.unlink()
        if settings_ownership_is_empty(new_ownership):
            delete_settings_ownership(claude_dir)
        else:
            save_settings_ownership(claude_dir, new_ownership)

    if prune:
        _report_pruned(claude_dir, storage)

    _print_summary(
        parsed,
        linked_items,
        settings_written,
        fragment_count,
        extra_global=len(global_messages),
    )
    _maybe_print_path_hint(any_shim)


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


def _provision_runtimes(parsed: list[Element], catalog: Path) -> bool:
    """Provision venv + shims for every domain in ``parsed``.

    Returns True if any shim was created/updated, so the caller knows to
    print the PATH hint once.
    """
    any_shim = False
    for element in parsed:
        if element.type is not ElementType.DOMAIN:
            continue
        try:
            result = provision_domain_runtime(catalog, element.name)
        except AiDotfilesError as exc:
            ui.warn(f"@{element.name}: runtime provisioning failed — {exc}")
            continue
        _report_provision_result(element.name, result)
        if result.shims_created or result.shims_updated:
            any_shim = True
    return any_shim


def _report_provision_result(domain_name: str, result: ProvisionResult) -> None:
    if result.python_packages and result.venv_path is not None:
        pkg_count = len(result.python_packages)
        noun = "package" if pkg_count == 1 else "packages"
        ui.info(
            f"  @{domain_name}: venv {result.venv_path.name} ready "
            f"({pkg_count} {noun})"
        )
    for name in result.shims_created:
        ui.info(f"  @{domain_name}: bin/{name} -> {paths.bin_dir() / name}")
    for name in result.shims_updated:
        ui.info(f"  @{domain_name}: bin/{name} updated")
    for name, reason in result.shims_skipped:
        ui.warn(f"  @{domain_name}: bin/{name} skipped — {reason}")
    for tool in result.missing_cli:
        ui.warn(
            f"  @{domain_name}: CLI tool '{tool}' is required but not on PATH — "
            "install it via your system package manager."
        )


def _maybe_print_path_hint(any_shim: bool) -> None:
    if not any_shim or bin_dir_on_path():
        return
    bin_path = paths.bin_dir()
    ui.warn(
        f"{bin_path} is not on PATH. Add this to your shell rc to use the "
        f"installed commands:\n"
        f'  export PATH="{bin_path}:$PATH"'
    )


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
