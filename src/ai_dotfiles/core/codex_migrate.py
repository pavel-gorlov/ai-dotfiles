"""Migrate LOCAL (non-catalog) project elements to the OpenAI Codex target.

The manifest-driven ``install`` renders only catalog elements for Codex; a
project's own hand-authored ``.claude/`` skills/agents/rules are invisible to
it (see :mod:`ai_dotfiles.core.local_discovery`). This module carries those
local elements to Codex, following the platform-verified rule "symlink where
the format is unchanged, render where it changes":

* **skill** — a relative symlink ``.agents/skills/<name>`` ->
  ``../../.claude/skills/<name>`` (auto-fresh, no drift tracking) when the raw
  ``SKILL.md`` satisfies Codex's constraints (frontmatter ``description`` <=
  :data:`SKILL_DESCRIPTION_MAX` chars — a hard cap; valid hyphen-case
  ``name``). Otherwise it is *rendered* with the first-sentence description
  trim (the only structurally required transform);
* **agent** — always rendered ``.codex/agents/<name>.toml`` (markdown -> TOML);
* **rule** — dispatched exactly like a catalog rule: a synthetic
  ``rule-<name>`` skill for description-only / glob rules, or managed
  ``AGENTS.md`` blocks for always-on / path-scoped rules.

Every artefact migrate creates is recorded in the local-provenance registry
(:mod:`ai_dotfiles.core.codex_local_registry`) so ``install --prune`` keeps it
and ``reconcile`` can refresh it. The canonical instruction file stays in
``CLAUDE.md``: migrate points Codex at it via
``project_doc_fallback_filenames`` rather than copying it into ``AGENTS.md``.

``migrate_to_codex`` returns a :class:`MigrateReport`; with ``dry_run=True`` it
plans and classifies every action (and lists Claude-only surfaces with no
Codex home) without touching the filesystem.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import tomllib

from ai_dotfiles.core import codex_config, codex_install, codex_render, paths
from ai_dotfiles.core.codex_layout import project_layout
from ai_dotfiles.core.codex_local_registry import (
    load_local_registry,
    save_local_registry,
)
from ai_dotfiles.core.codex_targets import iter_codex_pairs, iter_codex_rule_plans
from ai_dotfiles.core.elements import Element, ElementType
from ai_dotfiles.core.errors import AiDotfilesError
from ai_dotfiles.core.local_discovery import LocalElement, iter_local_elements

__all__ = [
    "SKILL_DESCRIPTION_MAX",
    "MigrateAction",
    "MigrateReport",
    "claude_only_surfaces",
    "migrate_to_codex",
]

# Re-exported for compatibility — the cap (and the whole gated-symlink
# decision) moved to :mod:`ai_dotfiles.core.codex_install` when the global
# Codex scope started sharing it (see ``skill_symlink_ok``).
SKILL_DESCRIPTION_MAX = codex_install.SKILL_DESCRIPTION_MAX


@dataclass(frozen=True)
class MigrateAction:
    """One planned or applied migration of a local element to Codex.

    ``strategy`` is ``symlink`` / ``render-skill`` / ``render-agent`` /
    ``rule-skill`` / ``rule-block``. ``classification`` mirrors the converter
    convention: ``MECHANICAL`` (deterministic, lossless), ``REFACTOR`` (a
    lossy transform a human should sanity-check, e.g. a trimmed description),
    or ``MANUAL`` (could not migrate automatically).
    """

    element_type: ElementType
    name: str
    strategy: str
    target_label: str
    classification: str
    note: str = ""


@dataclass
class MigrateReport:
    """Outcome (or plan, when ``dry_run``) of a Codex migration."""

    actions: list[MigrateAction] = field(default_factory=list)
    claude_only: list[tuple[str, str]] = field(default_factory=list)
    fallback_changed: bool = False
    mcp_added: list[str] = field(default_factory=list)
    dry_run: bool = False


def migrate_to_codex(
    project_root: Path,
    *,
    manifest_packages: Iterable[str] | None = None,
    dry_run: bool = False,
) -> MigrateReport:
    """Migrate every LOCAL ``.claude/`` element to the Codex target.

    Discovers local skills/agents/rules (excluding catalog symlinks and
    manifest-declared names), applies the symlink-or-render strategy per type,
    records provenance, and points Codex at ``CLAUDE.md`` via
    ``project_doc_fallback_filenames``. With ``dry_run`` nothing is written —
    the returned report is the plan. Claude-only surfaces (workflows, custom
    commands) with no Codex home are collected in
    :attr:`MigrateReport.claude_only`.
    """
    report = MigrateReport(dry_run=dry_run)
    registry = load_local_registry(project_root)
    packages = list(manifest_packages) if manifest_packages is not None else None

    for element in iter_local_elements(project_root, manifest_packages=packages):
        if element.type is ElementType.SKILL:
            _migrate_skill(element, project_root, registry, report, dry_run)
        elif element.type is ElementType.AGENT:
            _migrate_agent(element, project_root, registry, report, dry_run)
        elif element.type is ElementType.RULE:
            _migrate_rule(element, project_root, registry, report, dry_run)

    _migrate_instructions(project_root, report, dry_run)
    _migrate_user_mcp(project_root, report, dry_run)
    report.claude_only.extend(claude_only_surfaces(project_root))

    if not dry_run:
        save_local_registry(project_root, registry)

    return report


# ── per-element strategies ────────────────────────────────────────────


def _migrate_skill(
    element: LocalElement,
    project_root: Path,
    registry: dict[str, object],
    report: MigrateReport,
    dry_run: bool,
) -> None:
    source_dir = element.source_path
    target_dir = paths.project_codex_skills_dir(project_root) / element.name
    can_symlink, reason = codex_install.skill_symlink_ok(source_dir, element.name)
    skills: dict[str, str] = registry["skills"]  # type: ignore[assignment]

    if can_symlink:
        if not dry_run:
            codex_install.symlink_codex_skill(source_dir, target_dir)
        skills[element.name] = "symlink"
        report.actions.append(
            MigrateAction(
                ElementType.SKILL,
                element.name,
                "symlink",
                f".agents/skills/{element.name}",
                "MECHANICAL",
                reason,
            )
        )
        return

    if not dry_run:
        codex_install.install_codex_skill(source_dir, target_dir)
    skills[element.name] = "render"
    report.actions.append(
        MigrateAction(
            ElementType.SKILL,
            element.name,
            "render-skill",
            f".agents/skills/{element.name}",
            "REFACTOR",
            reason,
        )
    )


def _migrate_agent(
    element: LocalElement,
    project_root: Path,
    registry: dict[str, object],
    report: MigrateReport,
    dry_run: bool,
) -> None:
    source_md = element.source_path
    target = paths.project_codex_agents_dir(project_root) / f"{element.name}.toml"
    try:
        if dry_run:
            codex_render.render_agent_toml(source_md)  # validate frontmatter
        else:
            codex_install.install_codex_agent(source_md, target)
    except AiDotfilesError as exc:
        report.claude_only.append(
            (f"agent:{element.name}", f"cannot render to Codex TOML — {exc}")
        )
        return
    agents: dict[str, str] = registry["agents"]  # type: ignore[assignment]
    agents[element.name] = "render"
    report.actions.append(
        MigrateAction(
            ElementType.AGENT,
            element.name,
            "render-agent",
            f".codex/agents/{element.name}.toml",
            "MECHANICAL",
            "markdown -> TOML (developer_instructions)",
        )
    )


def _migrate_rule(
    element: LocalElement,
    project_root: Path,
    registry: dict[str, object],
    report: MigrateReport,
    dry_run: bool,
) -> None:
    parsed = Element(ElementType.RULE, element.name, element.raw)
    catalog = paths.project_claude_dir(project_root)  # .claude mirrors catalog layout
    layout = project_layout(project_root)

    skills: dict[str, str] = registry["skills"]  # type: ignore[assignment]
    for pair in iter_codex_pairs(parsed, layout, catalog):
        if not dry_run:
            codex_install.install_codex_rule_skill(pair.source, pair.target)
        skills[pair.target.name] = "render"
        report.actions.append(
            MigrateAction(
                ElementType.RULE,
                element.name,
                "rule-skill",
                f".agents/skills/{pair.target.name}",
                "MECHANICAL",
                "description-only rule -> synthetic Codex skill",
            )
        )

    rule_blocks: dict[str, list[str]] = registry["rule_blocks"]  # type: ignore[assignment]
    for plan in iter_codex_rule_plans(parsed, layout, catalog):
        rule_name = element.name
        if not dry_run:
            codex_install.apply_codex_rule_blocks(plan.source, plan.agents_md_paths)
        for agents_md_path in plan.agents_md_paths:
            rel = _rellabel(agents_md_path, project_root)
            names = rule_blocks.setdefault(rel, [])
            if rule_name not in names:
                names.append(rule_name)
            report.actions.append(
                MigrateAction(
                    ElementType.RULE,
                    element.name,
                    "rule-block",
                    rel,
                    "MECHANICAL",
                    f"{plan.rule_class} rule -> AGENTS.md managed block",
                )
            )


def _migrate_instructions(
    project_root: Path, report: MigrateReport, dry_run: bool
) -> None:
    """Point Codex at the project's ``CLAUDE.md`` via fallback filenames."""
    claude_md = project_root / "CLAUDE.md"
    if not claude_md.is_file():
        return
    if dry_run:
        current = _current_fallbacks(project_root)
        report.fallback_changed = "CLAUDE.md" not in current
        return
    report.fallback_changed = codex_config.ensure_project_doc_fallback(
        paths.project_codex_dir(project_root), "CLAUDE.md"
    )


def _migrate_user_mcp(project_root: Path, report: MigrateReport, dry_run: bool) -> None:
    """Carry user-authored ``.mcp.json`` servers to Codex ``[mcp_servers]``.

    Only servers the user added themselves are migrated — domain-contributed
    servers (recorded in the Claude MCP ownership sidecar) are already handled
    by the domain MCP writer. Servers already present in ``config.toml`` are
    left as-is.
    """
    from ai_dotfiles.core.mcp_ownership import load_ownership

    mcp_path = project_root / ".mcp.json"
    if not mcp_path.is_file():
        return
    try:
        data = json.loads(mcp_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        return

    owned = load_ownership(paths.project_claude_dir(project_root))
    user_servers = {
        name: cfg
        for name, cfg in servers.items()
        if name not in owned and isinstance(cfg, dict)
    }
    if not user_servers:
        return

    translated = {
        name: codex_config.translate_mcp_server(cfg)
        for name, cfg in user_servers.items()
    }
    if dry_run:
        current = _current_mcp_names(project_root)
        report.mcp_added.extend(name for name in translated if name not in current)
        return
    added, _ = codex_config.add_mcp_servers(
        paths.project_codex_dir(project_root), translated
    )
    report.mcp_added.extend(added)


# ── helpers ───────────────────────────────────────────────────────────


def _load_config_toml(project_root: Path) -> dict[str, object]:
    path = codex_config.config_path(paths.project_codex_dir(project_root))
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _current_fallbacks(project_root: Path) -> list[str]:
    value = _load_config_toml(project_root).get("project_doc_fallback_filenames")
    return [str(x) for x in value] if isinstance(value, list) else []


def _current_mcp_names(project_root: Path) -> set[str]:
    value = _load_config_toml(project_root).get("mcp_servers")
    return set(value) if isinstance(value, dict) else set()


def _rellabel(path: Path, project_root: Path) -> str:
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return path.name


def claude_only_surfaces(project_root: Path) -> list[tuple[str, str]]:
    """List project surfaces that have no Codex home (reported, not migrated).

    Workflows and custom slash commands are Claude Code harness features
    Codex cannot host; they are surfaced so a Codex switch does not silently
    drop real work. Hooks are *not* listed here — they migrate to
    ``.codex/hooks.json`` via the hooks step.
    """
    claude_dir = paths.project_claude_dir(project_root)
    out: list[tuple[str, str]] = []

    workflows = claude_dir / "workflows"
    if workflows.is_dir():
        for entry in sorted(workflows.iterdir()):
            if entry.name.startswith(".") or not entry.is_file():
                continue
            out.append(
                (f"workflows/{entry.name}", "Codex has no workflow/phase engine")
            )

    commands = claude_dir / "commands"
    if commands.is_dir():
        for entry in sorted(commands.iterdir()):
            if entry.name.startswith(".") or entry.suffix != ".md":
                continue
            out.append(
                (
                    f"commands/{entry.name}",
                    "Codex custom prompts are user-scoped; re-express as a skill",
                )
            )

    return out
