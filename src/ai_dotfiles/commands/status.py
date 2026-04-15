"""``ai-dotfiles status`` — validate installed symlinks and show settings summary.

Thin wrapper over ``core``:

1. Resolve scope (project or global via ``-g``) and load the manifest.
2. For each package, resolve expected ``(source, target)`` pairs.
3. Classify each target as OK (``+``), BROKEN (``!``), or NOT LINKED (``x``).
4. Print a summary of merged domain hooks.
5. Exit 0 if everything is OK, 1 if any issue was found.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import click

from ai_dotfiles import ui
from ai_dotfiles.core import elements, manifest, paths, settings_merge, symlinks
from ai_dotfiles.core.elements import Element, ElementType
from ai_dotfiles.core.errors import AiDotfilesError, ConfigError

# ── Status indicators ────────────────────────────────────────────────────

_OK = "+"
_BROKEN = "!"
_MISSING = "x"


def _resolve_scope(is_global: bool) -> tuple[Path, Path, str]:
    """Return ``(manifest_path, claude_dir, label)`` for the selected scope."""
    if is_global:
        return (
            paths.global_manifest_path(),
            paths.claude_global_dir(),
            "global",
        )

    root = paths.find_project_root()
    if root is None or not paths.project_manifest_path(root).is_file():
        raise ConfigError("ai-dotfiles.json not found. Run 'ai-dotfiles init' first.")
    return paths.project_manifest_path(root), paths.project_claude_dir(root), root.name


def _expected_pairs(
    element: Element, claude_dir: Path, catalog: Path
) -> list[tuple[Path, Path, str]]:
    """Return ``(source, target, label)`` triples expected for ``element``.

    ``label`` is a short human-readable path (e.g. ``skills/foo``) relative to
    ``claude_dir``.
    """
    triples: list[tuple[Path, Path, str]] = []
    if element.type is ElementType.DOMAIN:
        # Domain may or may not exist in catalog; resolve_target_paths handles
        # missing subdirs gracefully (returns empty list).
        source_root = elements.resolve_source_path(element, catalog)
        if not source_root.is_dir():
            return triples
        for source, target in elements.resolve_target_paths(
            element, claude_dir, catalog
        ):
            label = _relative_label(target, claude_dir)
            triples.append((source, target, label))
        return triples

    for source, target in elements.resolve_target_paths(element, claude_dir, catalog):
        triples.append((source, target, _relative_label(target, claude_dir)))
    return triples


def _relative_label(target: Path, claude_dir: Path) -> str:
    try:
        rel = target.relative_to(claude_dir)
    except ValueError:
        return str(target)
    return str(rel)


def _classify(source: Path, target: Path, storage: Path) -> str:
    """Return one of :data:`_OK`, :data:`_BROKEN`, :data:`_MISSING`."""
    if not target.is_symlink() and not target.exists():
        return _MISSING

    if not target.is_symlink():
        # A real file/dir at the target — not managed by us.
        return _BROKEN

    # It's a symlink. Check what it points at.
    try:
        current = Path(os.readlink(target))
    except OSError:
        return _BROKEN

    current_abs = current if current.is_absolute() else (target.parent / current)
    try:
        resolved = current_abs.resolve()
    except OSError:
        return _BROKEN

    try:
        expected = source.resolve()
    except OSError:
        return _BROKEN

    if not resolved.exists():
        return _BROKEN
    if resolved != expected:
        return _BROKEN
    if not symlinks.is_managed_symlink(target, storage):
        return _BROKEN
    return _OK


def _format_line(indicator: str, label: str, source: Path, status_text: str) -> str:
    # Pad label for column alignment.
    padded = label.ljust(28)
    return f"    {indicator} {padded} -> {source}  {status_text}"


def _print_package(
    element: Element,
    triples: list[tuple[Path, Path, str]],
    storage: Path,
) -> int:
    """Print one package block. Returns count of issues found."""
    header = element.raw
    ui.info(f"  {header}")

    issues = 0

    if not triples:
        # Nothing to verify (e.g. domain missing from catalog or empty).
        ui.info(f"    {_MISSING} (no linkable items found in catalog)")
        return 1

    for source, target, label in triples:
        status = _classify(source, target, storage)
        if status == _OK:
            ui.info(_format_line(_OK, label, source, "OK"))
        elif status == _BROKEN:
            ui.info(f"    {_BROKEN} {label.ljust(28)} -> BROKEN (target missing)")
            issues += 1
        else:
            ui.info(f"    {_MISSING} {label.ljust(28)} NOT LINKED")
            issues += 1
    return issues


def _print_settings_summary(
    packages: list[str], catalog: Path, claude_dir: Path
) -> None:
    fragments = settings_merge.collect_domain_fragments(packages, catalog)
    settings_path = claude_dir / "settings.json"

    ui.info("")
    ui.info(f"  Settings: {_relative_label(settings_path, claude_dir.parent)}")

    if not settings_path.is_file():
        ui.info("    (settings.json not present)")
        return

    if fragments:
        domain_names = _domain_specs(packages)
        if domain_names:
            ui.info(f"    Merged from: {', '.join(domain_names)}")

    merged: dict[str, Any] = settings_merge.assemble_settings(fragments)
    hooks = merged.get("hooks")
    if isinstance(hooks, dict) and hooks:
        parts: list[str] = []
        for event in sorted(hooks.keys()):
            entries = hooks[event]
            count = len(entries) if isinstance(entries, list) else 1
            noun = "handler" if count == 1 else "handlers"
            parts.append(f"{event} ({count} {noun})")
        ui.info(f"    Hooks: {', '.join(parts)}")
    else:
        ui.info("    Hooks: none")


def _domain_specs(packages: list[str]) -> list[str]:
    names: list[str] = []
    for spec in packages:
        try:
            element = elements.parse_element(spec)
        except AiDotfilesError:
            continue
        if element.type is ElementType.DOMAIN:
            names.append(spec)
    return names


@click.command("status")
@click.option(
    "-g",
    "--global",
    "is_global",
    is_flag=True,
    help="Check the global manifest instead of the project one.",
)
def status(is_global: bool) -> None:
    """Show installation status and merged settings summary."""
    try:
        manifest_path, claude_dir, label = _resolve_scope(is_global)
    except AiDotfilesError as exc:
        ui.error(str(exc))
        raise SystemExit(exc.exit_code) from exc

    ui.info(f"ai-dotfiles status ({label})")
    ui.info("")

    packages = manifest.get_packages(manifest_path)
    if not packages:
        ui.info("  No packages installed.")
        raise SystemExit(0)

    catalog = paths.catalog_dir()
    storage = paths.storage_root()

    try:
        parsed = elements.parse_elements(packages)
    except AiDotfilesError as exc:
        ui.error(str(exc))
        raise SystemExit(exc.exit_code) from exc

    total_issues = 0
    for element in parsed:
        triples = _expected_pairs(element, claude_dir, catalog)
        total_issues += _print_package(element, triples, storage)

    _print_settings_summary(packages, catalog, claude_dir)

    ui.info("")
    if total_issues:
        noun = "issue" if total_issues == 1 else "issues"
        ui.info(f"Issues: {total_issues} {noun} (run 'ai-dotfiles install' to fix)")
        raise SystemExit(1)
    ui.info("All OK.")
    raise SystemExit(0)
