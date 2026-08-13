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
    codex_config,
    codex_global,
    codex_install,
    codex_migrate,
    elements,
    manifest,
    paths,
    settings_merge,
    symlinks,
)
from ai_dotfiles.core.codex_layout import CodexLayout, global_layout, project_layout
from ai_dotfiles.core.codex_local_registry import load_local_registry
from ai_dotfiles.core.codex_targets import iter_codex_pairs, iter_codex_rule_plans
from ai_dotfiles.core.copy_ownership import load_copy_ownership, relative_label
from ai_dotfiles.core.elements import Element, ElementType
from ai_dotfiles.core.errors import AiDotfilesError, ConfigError
from ai_dotfiles.core.local_discovery import LocalElement, iter_local_elements
from ai_dotfiles.core.mcp_merge import collect_mcp_fragments

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


def _classify(
    source: Path,
    target: Path,
    storage: Path,
    *,
    copy_mode: bool = False,
    owned_copies: frozenset[str] = frozenset(),
    claude_dir: Path | None = None,
) -> str:
    """Return one of :data:`_OK`, :data:`_BROKEN`, :data:`_MISSING`.

    In ``copy_mode`` the Claude target holds real copied files, not
    symlinks: a target is OK when it exists and is recorded as an
    ai-dotfiles-managed copy in the copy-ownership sidecar; MISSING when
    absent; BROKEN when present but unrecorded (the user's own file).
    """
    if copy_mode:
        if not target.exists() and not target.is_symlink():
            return _MISSING
        if claude_dir is None:
            return _BROKEN
        return _OK if relative_label(target, claude_dir) in owned_copies else _BROKEN

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
    *,
    copy_mode: bool = False,
    owned_copies: frozenset[str] = frozenset(),
    claude_dir: Path | None = None,
) -> int:
    """Print one package block. Returns count of issues found.

    In ``copy_mode`` the Claude target is materialised as copied files,
    so an OK entry is reported as ``copied`` rather than a live symlink.
    """
    header = element.raw
    ui.info(f"  {header}")

    issues = 0

    if not triples:
        # Nothing to verify (e.g. domain missing from catalog or empty).
        ui.info(f"    {_MISSING} (no linkable items found in catalog)")
        return 1

    ok_text = "OK (copied)" if copy_mode else "OK"
    for source, target, label in triples:
        status = _classify(
            source,
            target,
            storage,
            copy_mode=copy_mode,
            owned_copies=owned_copies,
            claude_dir=claude_dir,
        )
        if status == _OK:
            ui.info(_format_line(_OK, label, source, ok_text))
        elif status == _BROKEN:
            if copy_mode:
                ui.info(
                    f"    {_BROKEN} {label.ljust(28)} -> BROKEN "
                    "(unmanaged file at target)"
                )
            else:
                ui.info(f"    {_BROKEN} {label.ljust(28)} -> BROKEN (target missing)")
            issues += 1
        else:
            not_text = "NOT COPIED" if copy_mode else "NOT LINKED"
            ui.info(f"    {_MISSING} {label.ljust(28)} {not_text}")
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
    parsed: list[Element], packages: list[str], layout: CodexLayout, catalog: Path
) -> int:
    """Print Codex-target status. Return the count of issues found.

    Each manifest element is expanded into its Codex artefacts. A
    skill/agent — and a description-only rule's synthetic ``rule-<name>``
    skill — is OK when its generated file exists, BROKEN when missing,
    and STALE when its ``# source-sha256`` header no longer matches the
    catalog source (ADR ai-1-1 drift detection). An always-on /
    path-scoped rule is OK when its managed block is present in every
    target ``AGENTS.md`` and matches the rule body, STALE when the block
    is present but the source changed, and MISSING (NOT INSTALLED)
    otherwise. The managed ``config.toml`` regions (``[ai_dotfiles]`` +
    domain-owned ``[mcp_servers]``) are reported STALE when they no
    longer match the current domain fragments. At global scope a
    symlinked skill is OK while the link resolves into the catalog *and*
    the source still fits Codex's limits, and the instructions bridge
    block is reported too. Each issue counts as one.
    """
    ui.info("")
    ui.info(
        "  Codex target"
        if layout.project_root is not None
        else "  Codex target (global)"
    )
    issues = 0
    found_any = False

    for element in parsed:
        for pair in iter_codex_pairs(element, layout, catalog):
            found_any = True
            issues += _print_codex_pair_status(pair)
        for plan in iter_codex_rule_plans(element, layout, catalog):
            found_any = True
            issues += _print_codex_rule_plan_status(
                plan, layout.project_root or layout.codex_dir
            )

    if layout.project_root is None:
        issues += _print_codex_bridge_status(layout)
    issues += _print_codex_config_status(packages, layout.codex_dir, catalog)

    if not found_any:
        ui.info("    (no Codex-renderable elements in the manifest)")
    return issues


def _print_codex_config_status(
    packages: list[str], codex_dir: Path, catalog: Path
) -> int:
    """Print the managed ``config.toml`` drift status. Return issues.

    Recomputes the expected managed ``[ai_dotfiles]`` table and
    domain-owned ``[mcp_servers]`` from the current domain fragments and
    compares them to the on-disk file (:func:`codex_config.config_state`).
    Prints nothing (and returns 0) when there is no managed config to
    report; STALE counts as one issue.
    """
    settings_pairs = [
        (path.parent.name, path)
        for path in settings_merge.collect_domain_fragments(packages, catalog)
    ]
    mcp_pairs = collect_mcp_fragments(packages, catalog)
    state = codex_config.config_state(codex_dir, settings_pairs, mcp_pairs)
    if state == "absent":
        return 0
    if state == "ok":
        ui.info(f"    {_OK} {'config.toml'.ljust(28)} OK")
        return 0
    ui.info(f"    {_BROKEN} {'config.toml'.ljust(28)} STALE (fragments changed)")
    return 1


def _print_codex_bridge_status(layout: CodexLayout) -> int:
    """Print the global instructions-bridge block status. Return issues.

    Silent when there is no ``~/.claude/CLAUDE.md`` to bridge. STALE
    means the user edited ``CLAUDE.md`` since the last ``install -g`` /
    ``reconcile -g``.
    """
    state = codex_global.bridge_state(layout.root_agents_md)
    if state == "absent":
        return 0
    label = "AGENTS.md (global instructions)"
    if state == "ok":
        ui.info(f"    {_OK} {label}")
        return 0
    if state == "stale":
        ui.info(f"    {_BROKEN} {label.ljust(28)} STALE (source changed)")
        return 1
    ui.info(f"    {_MISSING} {label.ljust(28)} NOT INSTALLED")
    return 1


def _print_codex_pair_status(pair: Any) -> int:
    """Print one skill/agent/synthetic-rule-skill artefact line.

    Returns 1 if the artefact is missing or stale, 0 if OK. A symlinked
    skill (the global gated-symlink strategy) is OK while the link
    resolves to its catalog source *and* the source still satisfies
    Codex's skill limits — a description that has since grown over the
    1024-char cap would silently break the skill in every Codex session,
    so it is surfaced as STALE (re-render needed).
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

    if pair.element_type is ElementType.SKILL and pair.target.is_symlink():
        try:
            resolves = pair.target.resolve() == pair.source.resolve()
        except OSError:
            resolves = False
        if not resolves or not pair.source.is_dir():
            ui.info(f"    {_BROKEN} {label.ljust(28)} BROKEN (dangling symlink)")
            return 1
        if not codex_install.skill_symlink_ok(pair.source, pair.target.name)[0]:
            ui.info(
                f"    {_BROKEN} {label.ljust(28)} STALE "
                "(source exceeds Codex skill limits — re-render needed)"
            )
            return 1
        ui.info(_format_line(_OK, label, source, "OK (symlink)"))
        return 0

    if not generated.is_file():
        ui.info(f"    {_MISSING} {label.ljust(28)} NOT INSTALLED")
        return 1
    if codex_install.is_stale(generated, source):
        reason = (
            "generator changed"
            if codex_install.generator_is_outdated(generated)
            else "source changed"
        )
        ui.info(f"    {_BROKEN} {label.ljust(28)} STALE ({reason})")
        return 1
    ui.info(_format_line(_OK, label, source, "OK"))
    return 0


def _print_codex_rule_plan_status(plan: Any, project_root: Path) -> int:
    """Print one always-on / path-scoped rule's ``AGENTS.md`` block status.

    Each target ``AGENTS.md`` is OK when its managed block is present and its
    recorded sha still matches the rule body, STALE when the block is present
    but the rule source changed, and NOT INSTALLED when the block is absent.
    Returns the number of target files that are stale or missing.
    """
    from ai_dotfiles.core.agents_md import rule_name_of

    name = rule_name_of(plan.source)
    issues = 0
    for agents_md_path in plan.agents_md_paths:
        try:
            rel = str(agents_md_path.relative_to(project_root))
        except ValueError:
            rel = agents_md_path.name
        label = f"rules/{name} -> {rel}"
        state = codex_install.rule_block_state(plan.source, agents_md_path)
        if state == "ok":
            ui.info(f"    {_OK} {label}")
        elif state == "stale":
            ui.info(f"    {_BROKEN} {label.ljust(28)} STALE (source changed)")
            issues += 1
        else:  # missing
            ui.info(f"    {_MISSING} {label.ljust(28)} NOT INSTALLED")
            issues += 1
    return issues


def _print_local_status(project_root: Path, packages: list[str]) -> None:
    """Print LOCAL (non-catalog) elements and Claude-only surfaces.

    Local hand-authored ``.claude/`` elements are invisible to the
    manifest-driven checks above; this surfaces them and whether each has
    been carried to Codex by ``ai-dotfiles migrate`` (tracked in the local
    registry). Claude-only surfaces (workflows, custom commands) with no Codex
    home are listed so a Codex switch does not silently drop them. Purely
    informational — none of this counts as an install issue.
    """
    local_elements = list(iter_local_elements(project_root, manifest_packages=packages))
    claude_only = codex_migrate.claude_only_surfaces(project_root)
    if not local_elements and not claude_only:
        return

    registry = load_local_registry(project_root)
    ui.info("")
    ui.info("  Local (non-catalog) elements")
    if not local_elements:
        ui.info("    (none)")
    for element in local_elements:
        migrated = _local_is_migrated(element, registry)
        mark = _OK if migrated else _MISSING
        state = (
            "migrated to Codex"
            if migrated
            else "not migrated (run 'ai-dotfiles migrate')"
        )
        ui.info(f"    {mark} {element.raw.ljust(28)} {state}")

    if claude_only:
        ui.info("")
        ui.info("  Claude-only (no Codex target)")
        for label, reason in claude_only:
            ui.info(f"    - {label}: {reason}")


def _local_is_migrated(element: LocalElement, registry: dict[str, Any]) -> bool:
    if element.type is ElementType.SKILL:
        return element.name in registry.get("skills", {})
    if element.type is ElementType.AGENT:
        return element.name in registry.get("agents", {})
    if element.type is ElementType.RULE:
        if f"rule-{element.name}" in registry.get("skills", {}):
            return True
        return any(
            element.name in names for names in registry.get("rule_blocks", {}).values()
        )
    return False


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
        if not is_global:
            local_root = paths.find_project_root()
            if local_root is not None:
                _print_local_status(local_root, [])
        raise SystemExit(0)

    catalog = paths.catalog_dir()
    storage = paths.storage_root()

    try:
        parsed = elements.parse_elements(packages)
    except AiDotfilesError as exc:
        ui.error(str(exc))
        raise SystemExit(exc.exit_code) from exc

    # Both scopes honour the manifest's `targets` (the global Codex target
    # superseded ADR ai-1-3's project-only restriction); the global scope
    # is always symlink-mode.
    targets = manifest.get_targets(manifest_path)
    link_mode = "symlink" if is_global else manifest.get_link_mode(manifest_path)
    copy_mode = link_mode == "copy"

    total_issues = 0
    if "claude" in targets:
        owned_copies = (
            frozenset(load_copy_ownership(claude_dir)) if copy_mode else frozenset()
        )
        if copy_mode:
            ui.info("  Claude target: copy mode (real files, snapshot of catalog)")
        for element in parsed:
            triples = _expected_pairs(element, claude_dir, catalog)
            total_issues += _print_package(
                element,
                triples,
                storage,
                copy_mode=copy_mode,
                owned_copies=owned_copies,
                claude_dir=claude_dir,
            )
        _print_settings_summary(packages, catalog, claude_dir)

    if "codex" in targets:
        if is_global:
            total_issues += _print_codex_target(
                parsed, packages, global_layout(), catalog
            )
        else:
            project_root = paths.find_project_root()
            if project_root is not None:
                total_issues += _print_codex_target(
                    parsed, packages, project_layout(project_root), catalog
                )

    if not is_global:
        local_root = paths.find_project_root()
        if local_root is not None:
            _print_local_status(local_root, packages)

    ui.info("")
    if total_issues:
        noun = "issue" if total_issues == 1 else "issues"
        cmd = "ai-dotfiles install -g" if is_global else "ai-dotfiles install"
        ui.info(f"Issues: {total_issues} {noun} (run '{cmd}' to fix)")
        raise SystemExit(1)
    ui.info("All OK.")
    raise SystemExit(0)
