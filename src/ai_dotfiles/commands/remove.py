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
from ai_dotfiles.core.dependencies import find_reverse_deps
from ai_dotfiles.core.elements import (
    Element,
    ElementType,
    parse_element,
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


def _check_reverse_deps(
    manifest_path: Path,
    catalog: Path,
    targets: list[Element],
) -> None:
    """Refuse to remove ``targets`` if other manifest entries depend on them.

    A target is exempt from the check when it is itself one of the
    other targets in the same call (removing the dependent and the dep
    together is fine).
    """
    raw_packages = manifest.get_packages(manifest_path)
    if not raw_packages:
        return
    target_set = {el.raw for el in targets}
    parsed_packages: list[Element] = []
    for spec in raw_packages:
        try:
            parsed_packages.append(parse_element(spec))
        except Exception:  # noqa: BLE001 - skip malformed manifest entries
            continue
    blockers: dict[str, list[str]] = {}
    for target in targets:
        dependents = find_reverse_deps(catalog, parsed_packages, target)
        # An entry that the user is also removing in the same call doesn't
        # block — they're tearing down the whole subtree intentionally.
        outstanding = [d for d in dependents if d.raw not in target_set]
        if outstanding:
            blockers[target.raw] = [d.raw for d in outstanding]
    if not blockers:
        return
    lines = ["Cannot remove the following entries — other packages depend on them:"]
    for target_raw, dependents_raw in blockers.items():
        joined = ", ".join(dependents_raw)
        lines.append(f"  {target_raw}  <-  required by {joined}")
    lines.append("Remove the dependents too, or pass --force to override.")
    raise ConfigError("\n".join(lines))


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
    """Reassemble ``settings.json`` while preserving user edits.

    Strips previously-owned entries from existing settings, then merges
    remaining fragments into the user-only base, and records new
    ownership (delete if empty).
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
@click.option(
    "--force",
    is_flag=True,
    help=(
        "Remove even if other manifest entries declare a dependency on "
        "the target. The dependents stay installed but their declared "
        "dependency will become missing."
    ),
)
def remove(
    packages: tuple[str, ...],
    is_global: bool,
    no_gitignore: bool,
    force: bool,
) -> None:
    """Remove PACKAGES from the manifest and unlink their elements."""
    try:
        elements = parse_elements(list(packages))

        catalog = catalog_dir()
        manifest_path, claude_dir, project_root = _resolve_scope(is_global)

        if not force:
            _check_reverse_deps(manifest_path, catalog, elements)

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
