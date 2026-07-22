"""Reconcile the Codex target: regenerate every stale or missing artefact.

``install`` is the only path that (re)generates Codex artefacts, so after the
first install a catalog change (or an edited local source) leaves the project's
``.codex`` / ``.agents`` / ``AGENTS.md`` drifting silently until a full
reinstall. ``reconcile`` closes that gap: it walks the same artefacts
``status`` inspects, and — using the drift checks already in the codebase
(:func:`codex_install.is_stale`, :func:`codex_install.rule_block_state`,
:func:`codex_config.config_state`, plus local-source freshness) — regenerates
only what is stale or missing. ``check_only`` detects drift and writes nothing,
so it can gate a pre-commit / CI run.

Both catalog-derived artefacts (from the manifest) and local-derived ones
(from ``ai-dotfiles migrate``, tracked in the local registry) are covered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ai_dotfiles.core import (
    codex_config,
    codex_global,
    codex_install,
    codex_migrate,
    elements,
    paths,
    settings_merge,
)
from ai_dotfiles.core.codex_layout import global_layout, project_layout
from ai_dotfiles.core.codex_local_registry import load_local_registry
from ai_dotfiles.core.codex_targets import (
    CodexPair,
    CodexRulePlan,
    iter_codex_pairs,
    iter_codex_rule_plans,
)
from ai_dotfiles.core.elements import Element, ElementType
from ai_dotfiles.core.local_discovery import LocalElement, iter_local_elements
from ai_dotfiles.core.mcp_merge import collect_mcp_fragments

__all__ = ["ReconcileReport", "reconcile_codex", "reconcile_codex_global"]


@dataclass
class ReconcileReport:
    """What ``reconcile`` found stale/missing (and fixed, unless ``check_only``)."""

    drift: list[str] = field(default_factory=list)
    check_only: bool = False


def reconcile_codex(
    project_root: Path,
    packages: list[str],
    catalog: Path,
    *,
    check_only: bool = False,
    include_catalog: bool = True,
) -> ReconcileReport:
    """Refresh every stale/missing Codex artefact; return what drifted.

    ``include_catalog`` gates the manifest-driven catalog artefacts (skills,
    agents, rule blocks, config.toml) — pass it as ``"codex" in targets`` so a
    project that only ran ``migrate`` (Codex not in its targets) still gets its
    local artefacts reconciled without the catalog ones being treated as
    missing. With ``check_only`` nothing is written — the report lists the
    drift a plain ``reconcile`` would repair.
    """
    report = ReconcileReport(check_only=check_only)
    layout = project_layout(project_root)

    if include_catalog:
        for element in elements.parse_elements(packages):
            for pair in iter_codex_pairs(element, layout, catalog):
                if _pair_needs_refresh(pair):
                    report.drift.append(_pair_label(pair))
                    if not check_only:
                        _apply_pair(pair)
            for plan in iter_codex_rule_plans(element, layout, catalog):
                _reconcile_rule_plan(plan, project_root, report, check_only)
        _reconcile_config(
            packages, paths.project_codex_dir(project_root), catalog, report, check_only
        )

    _reconcile_local(project_root, packages, report, check_only)
    return report


def reconcile_codex_global(
    packages: list[str],
    catalog: Path,
    *,
    check_only: bool = False,
) -> ReconcileReport:
    """Refresh every stale/missing *global* Codex artefact.

    The user-scope counterpart of :func:`reconcile_codex`, walking the
    ``$CODEX_HOME`` layout the global install writes. The desired state
    per catalog skill follows the gated-symlink rule
    (:func:`codex_install.skill_symlink_ok`): an eligible skill must be
    a live symlink into the catalog; an ineligible one (e.g. its
    description grew over the cap) must be a fresh render — an
    eligibility flip is repaired by converting between the two. There is
    no local-registry side: ``migrate`` does not exist at global scope.
    The instructions bridge (``~/.claude/CLAUDE.md`` block) and the
    managed ``config.toml`` regions are refreshed too.
    """
    report = ReconcileReport(check_only=check_only)
    layout = global_layout()

    for element in elements.parse_elements(packages):
        for pair in iter_codex_pairs(element, layout, catalog):
            if _global_pair_needs_refresh(pair):
                report.drift.append(_pair_label(pair))
                if not check_only:
                    _apply_global_pair(pair)
        for plan in iter_codex_rule_plans(element, layout, catalog):
            _reconcile_rule_plan(plan, layout.codex_dir, report, check_only)
    _reconcile_config(packages, layout.codex_dir, catalog, report, check_only)
    _reconcile_global_bridge(layout.root_agents_md, report, check_only)
    return report


# ── catalog skill/agent/rule-skill pairs ──────────────────────────────


def _pair_generated_source(pair: CodexPair) -> tuple[Path, Path]:
    """Return the ``(generated, source)`` files whose sha drift is compared."""
    if pair.element_type is ElementType.AGENT:
        return pair.target, pair.source
    if pair.element_type is ElementType.SKILL:
        return pair.target / "SKILL.md", pair.source / "SKILL.md"
    # synthetic rule skill — source is the rule .md itself
    return pair.target / "SKILL.md", pair.source


def _pair_needs_refresh(pair: CodexPair) -> bool:
    generated, source = _pair_generated_source(pair)
    return not generated.is_file() or codex_install.is_stale(generated, source)


def _pair_label(pair: CodexPair) -> str:
    kind = "agents" if pair.element_type is ElementType.AGENT else "skills"
    return f"{kind}/{pair.target.name}"


def _apply_pair(pair: CodexPair) -> None:
    if pair.element_type is ElementType.AGENT:
        codex_install.install_codex_agent(pair.source, pair.target)
    elif pair.element_type is ElementType.SKILL:
        codex_install.install_codex_skill(pair.source, pair.target)
    else:
        codex_install.install_codex_rule_skill(pair.source, pair.target)


def _global_wants_symlink(pair: CodexPair) -> bool:
    """True when the global desired state for ``pair`` is a catalog symlink."""
    return (
        pair.element_type is ElementType.SKILL
        and codex_install.skill_symlink_ok(pair.source, pair.target.name)[0]
    )


def _global_pair_needs_refresh(pair: CodexPair) -> bool:
    if _global_wants_symlink(pair):
        return not _symlink_ok(pair.target, pair.source)
    if pair.target.is_symlink():
        # Rendered is the desired state (eligibility flipped, e.g. the
        # description grew over the cap) but a symlink is on disk.
        return True
    return _pair_needs_refresh(pair)


def _apply_global_pair(pair: CodexPair) -> None:
    if _global_wants_symlink(pair):
        codex_install.symlink_codex_skill(pair.source, pair.target, relative=False)
    else:
        _apply_pair(pair)


def _reconcile_global_bridge(
    agents_md_path: Path, report: ReconcileReport, check_only: bool
) -> None:
    """Refresh the global instructions bridge block when it drifted."""
    if codex_global.bridge_state(agents_md_path) in ("missing", "stale"):
        report.drift.append("AGENTS.md (global instructions)")
        if not check_only:
            codex_global.upsert_bridge(agents_md_path)


def _reconcile_rule_plan(
    plan: CodexRulePlan,
    label_base: Path,
    report: ReconcileReport,
    check_only: bool,
) -> None:
    from ai_dotfiles.core.agents_md import rule_name_of

    name = rule_name_of(plan.source)
    for agents_md_path in plan.agents_md_paths:
        if codex_install.rule_block_state(plan.source, agents_md_path) != "ok":
            report.drift.append(f"rules/{name} -> {_rel(agents_md_path, label_base)}")
            if not check_only:
                codex_install.apply_codex_rule_blocks(plan.source, [agents_md_path])


# ── config.toml ───────────────────────────────────────────────────────


def _fragment_pairs(
    packages: list[str], catalog: Path
) -> tuple[list[tuple[str, Path]], list[tuple[str, Path]]]:
    settings_pairs = [
        (path.parent.name, path)
        for path in settings_merge.collect_domain_fragments(packages, catalog)
    ]
    mcp_pairs = collect_mcp_fragments(packages, catalog)
    return settings_pairs, mcp_pairs


def _reconcile_config(
    packages: list[str],
    codex_dir: Path,
    catalog: Path,
    report: ReconcileReport,
    check_only: bool,
) -> None:
    settings_pairs, mcp_pairs = _fragment_pairs(packages, catalog)
    if codex_config.config_state(codex_dir, settings_pairs, mcp_pairs) == "stale":
        report.drift.append("config.toml")
        if not check_only:
            codex_config.write_codex_config(codex_dir, settings_pairs)
            codex_config.write_codex_mcp(codex_dir, mcp_pairs)


# ── local (migrate-origin) artefacts ──────────────────────────────────


def _reconcile_local(
    project_root: Path,
    packages: list[str],
    report: ReconcileReport,
    check_only: bool,
) -> None:
    """Detect drift in migrate-origin artefacts; re-run migrate to repair.

    Local symlinked skills are auto-fresh (the link points at the live source),
    so only a broken/missing link counts as drift; rendered skills/agents and
    rule blocks are checked for staleness against their local source.
    """
    drift = _local_drift(project_root, packages)
    if not drift:
        return
    report.drift.extend(drift)
    if not check_only:
        codex_migrate.migrate_to_codex(
            project_root, manifest_packages=packages, dry_run=False
        )


def _local_drift(project_root: Path, packages: list[str]) -> list[str]:
    registry = load_local_registry(project_root)
    recorded_skills: dict[str, str] = registry.get("skills", {})
    skills_dir = paths.project_codex_skills_dir(project_root)
    agents_dir = paths.project_codex_agents_dir(project_root)
    claude_dir = paths.project_claude_dir(project_root)
    out: list[str] = []

    for element in iter_local_elements(project_root, manifest_packages=packages):
        if element.type is ElementType.SKILL:
            target = skills_dir / element.name
            if recorded_skills.get(element.name) == "render":
                if not (target / "SKILL.md").is_file() or codex_install.is_stale(
                    target / "SKILL.md", element.source_path / "SKILL.md"
                ):
                    out.append(f"local skills/{element.name}")
            elif not _symlink_ok(target, element.source_path):
                out.append(f"local skills/{element.name}")
        elif element.type is ElementType.AGENT:
            target = agents_dir / f"{element.name}.toml"
            if not target.is_file() or codex_install.is_stale(
                target, element.source_path
            ):
                out.append(f"local agents/{element.name}")
        elif element.type is ElementType.RULE:
            out.extend(_local_rule_drift(element, project_root, claude_dir))
    return out


def _local_rule_drift(
    element: LocalElement, project_root: Path, claude_dir: Path
) -> list[str]:
    parsed = Element(ElementType.RULE, element.name, element.raw)
    layout = project_layout(project_root)
    out: list[str] = []
    for pair in iter_codex_pairs(parsed, layout, claude_dir):
        if _pair_needs_refresh(pair):
            out.append(f"local skills/{pair.target.name}")
    for plan in iter_codex_rule_plans(parsed, layout, claude_dir):
        for agents_md_path in plan.agents_md_paths:
            if codex_install.rule_block_state(plan.source, agents_md_path) != "ok":
                rel = _rel(agents_md_path, project_root)
                out.append(f"local rules/{element.name} -> {rel}")
    return out


def _symlink_ok(target: Path, source_dir: Path) -> bool:
    if not target.is_symlink():
        return False
    try:
        return target.resolve() == source_dir.resolve()
    except OSError:
        return False


def _rel(path: Path, project_root: Path) -> str:
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return path.name
