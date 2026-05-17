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
from ai_dotfiles.core import (
    codex_install,
    elements,
    manifest,
    paths,
    settings_merge,
    symlinks,
)
from ai_dotfiles.core.codex_targets import iter_codex_pairs, iter_codex_rule_plans
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


def _print_codex_target(
    parsed: list[Element], project_root: Path, catalog: Path
) -> int:
    """Print Codex-target status. Return the count of issues found.

    Each manifest element is expanded into its Codex artefacts. A
    skill/agent — and a description-only rule's synthetic ``rule-<name>``
    skill — is OK when its generated file exists, BROKEN when missing,
    and STALE when its ``# source-sha256`` header no longer matches the
    catalog source (ADR ai-1-1 drift detection). An always-on /
    path-scoped rule is OK when its managed block is present in every
    target ``AGENTS.md``, MISSING otherwise. Each issue counts as one.
    """
    ui.info("")
    ui.info("  Codex target")
    issues = 0
    found_any = False

    for element in parsed:
        for pair in iter_codex_pairs(element, project_root, catalog):
            found_any = True
            issues += _print_codex_pair_status(pair)
        for plan in iter_codex_rule_plans(element, project_root, catalog):
            found_any = True
            issues += _print_codex_rule_plan_status(plan, project_root)

    if not found_any:
        ui.info("    (no Codex-renderable elements in the manifest)")
    return issues


def _print_codex_pair_status(pair: Any) -> int:
    """Print one skill/agent/synthetic-rule-skill artefact line.

    Returns 1 if the artefact is missing or stale, 0 if OK.
    """
    if pair.element_type is ElementType.AGENT:
        kind, generated, source = "agents", pair.target, pair.source
    elif pair.element_type is ElementType.SKILL:
        kind = "skills"
        generated, source = pair.target / "SKILL.md", pair.source / "SKILL.md"
    else:  # synthetic rule skill — source is the rule .md itself
        kind = "skills"
        generated, source = pair.target / "SKILL.md", pair.source

    label = f"{kind}/{pair.target.name}"
    if not generated.is_file():
        ui.info(f"    {_MISSING} {label.ljust(28)} NOT INSTALLED")
        return 1
    if codex_install.is_stale(generated, source):
        ui.info(f"    {_BROKEN} {label.ljust(28)} STALE (source changed)")
        return 1
    ui.info(_format_line(_OK, label, source, "OK"))
    return 0


def _print_codex_rule_plan_status(plan: Any, project_root: Path) -> int:
    """Print one always-on / path-scoped rule's ``AGENTS.md`` block status.

    Returns the number of target ``AGENTS.md`` files whose managed block
    for the rule is missing.
    """
    from ai_dotfiles.core.agents_md import iter_rule_block_names, rule_name_of

    name = rule_name_of(plan.source)
    issues = 0
    for agents_md_path in plan.agents_md_paths:
        try:
            rel = str(agents_md_path.relative_to(project_root))
        except ValueError:
            rel = agents_md_path.name
        label = f"rules/{name} -> {rel}"
        present = agents_md_path.is_file() and name in iter_rule_block_names(
            agents_md_path.read_text(encoding="utf-8")
        )
        if present:
            ui.info(f"    {_OK} {label}")
        else:
            ui.info(f"    {_MISSING} {label.ljust(28)} NOT INSTALLED")
            issues += 1
    return issues


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

    # The Codex target is project-scoped only (ADR ai-1-3).
    targets = ["claude"] if is_global else manifest.get_targets(manifest_path)

    total_issues = 0
    if "claude" in targets:
        for element in parsed:
            triples = _expected_pairs(element, claude_dir, catalog)
            total_issues += _print_package(element, triples, storage)
        _print_settings_summary(packages, catalog, claude_dir)

    if "codex" in targets and not is_global:
        project_root = paths.find_project_root()
        if project_root is not None:
            total_issues += _print_codex_target(parsed, project_root, catalog)

    ui.info("")
    if total_issues:
        noun = "issue" if total_issues == 1 else "issues"
        cmd = "ai-dotfiles install -g" if is_global else "ai-dotfiles install"
        ui.info(f"Issues: {total_issues} {noun} (run '{cmd}' to fix)")
        raise SystemExit(1)
    ui.info("All OK.")
    raise SystemExit(0)
