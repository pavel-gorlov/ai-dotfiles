"""Codex-target element iteration shared by the command layer.

``install`` / ``add`` / ``remove`` / ``status`` all need to walk a
manifest element and ask "which Codex artefacts does this produce?".
That walk — domain expansion, skill-vs-agent classification, the
rules/hooks skip — lives here so the four command modules stay thin
wrappers and the logic has a single home (project rule: business logic
belongs in ``core/``).

Each :class:`CodexPair` ties a catalog ``source`` to its rendered Codex
``target`` path and records the originating :class:`ElementType` so the
caller can dispatch to the right :mod:`ai_dotfiles.core.codex_install`
function.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from ai_dotfiles.core.elements import Element, ElementType, resolve_source_path
from ai_dotfiles.core.rule_classify import RuleClass, classify_rule
from ai_dotfiles.core.targets import RenderMode, Target, render_policy_for

__all__ = [
    "CodexPair",
    "CodexRulePlan",
    "codex_skipped_domain_subdirs",
    "iter_codex_pairs",
    "iter_codex_rule_plans",
]

# Domain subdirectories that have a Codex surface, paired with the
# element type each member is rendered as. Rules joined the set in
# Phase 2 (ai-11) — they dispatch via :func:`iter_codex_rule_plans`.
_CODEX_DOMAIN_SUBDIRS: tuple[tuple[str, ElementType], ...] = (
    ("skills", ElementType.SKILL),
    ("agents", ElementType.AGENT),
)

# Domain subdirectories with no Codex surface at all — skipped with an
# explicit message rather than failing. ``rules`` left this set in
# Phase 2; only ``hooks`` remains (Codex has no hook harness).
_CODEX_SKIP_SUBDIRS: tuple[str, ...] = ("hooks",)

# Domain subdirectory holding rule members.
_CODEX_RULES_SUBDIR = "rules"

# Files that are domain metadata, never an installable member.
_DOMAIN_SKIP_FILES: frozenset[str] = frozenset(
    {"README.md", "domain.json", "settings.fragment.json", "mcp.fragment.json"}
)


@dataclass(frozen=True)
class CodexPair:
    """One catalog source rendered to one Codex target path.

    ``element_type`` selects the apply function:

    * :data:`ElementType.SKILL` — a catalog skill: ``source`` is the
      skill directory, ``target`` is ``.agents/skills/<name>/``;
    * :data:`ElementType.AGENT` — a catalog agent: ``source`` is the
      agent ``.md``, ``target`` is ``.codex/agents/<name>.toml``;
    * :data:`ElementType.RULE` — a *description-only* rule rendered as a
      synthetic Codex-only skill (ADR ai-1-2): ``source`` is the rule
      ``.md``, ``target`` is ``.agents/skills/rule-<name>/``.

    Always-on and path-scoped rules have no single source->target pair —
    they produce :class:`CodexRulePlan` entries instead.
    """

    element_type: ElementType
    source: Path
    target: Path


@dataclass(frozen=True)
class CodexRulePlan:
    """An always-on / path-scoped rule's ``AGENTS.md`` assembly plan.

    ``source`` is the catalog rule ``.md``; ``rule_class`` is the
    :class:`~ai_dotfiles.core.rule_classify.RuleClass` *value* string
    (``"always_on"`` / ``"path_scoped"``); ``agents_md_paths`` is the
    list of ``AGENTS.md`` files the rule's managed block must land in
    (the project-root file for always-on, one ``<dir>/AGENTS.md`` per
    ``paths:`` entry for path-scoped).
    """

    source: Path
    rule_class: str
    agents_md_paths: list[Path]


def codex_skipped_domain_subdirs(element: Element, catalog: Path) -> list[str]:
    """Return the non-empty no-Codex-surface subdirs of a domain.

    Only ``hooks`` qualifies — Codex has no hook harness, so a domain's
    ``hooks/`` is skipped with an explicit message. ``rules/`` is *not*
    skipped any more: Phase 2 (ai-11) renders rules for the Codex target
    (see :func:`iter_codex_pairs` / :func:`iter_codex_rule_plans`).
    Returns an empty list for non-domain elements or domains without a
    populated ``hooks/``.
    """
    if element.type is not ElementType.DOMAIN:
        return []
    domain_root = catalog / element.name
    skipped: list[str] = []
    for sub in _CODEX_SKIP_SUBDIRS:
        sub_dir = domain_root / sub
        if sub_dir.is_dir() and any(
            child.name not in _DOMAIN_SKIP_FILES and not child.name.startswith(".")
            for child in sub_dir.iterdir()
        ):
            skipped.append(sub)
    return skipped


def _iter_rule_sources(element: Element, catalog: Path) -> Iterator[Path]:
    """Yield the catalog rule ``.md`` paths ``element`` contributes.

    A standalone ``rule:`` element yields its single source; a domain
    yields every member of its ``rules/`` subdirectory. Skill/agent
    elements yield nothing.
    """
    if element.type is ElementType.RULE:
        yield resolve_source_path(element, catalog)
        return
    if element.type is ElementType.DOMAIN:
        rules_dir = catalog / element.name / _CODEX_RULES_SUBDIR
        if not rules_dir.is_dir():
            return
        for entry in sorted(rules_dir.iterdir()):
            if entry.name in _DOMAIN_SKIP_FILES or entry.name.startswith("."):
                continue
            if entry.suffix == ".md" and entry.is_file():
                yield entry


def _rule_skill_pair(rule_md: Path, project_root: Path) -> CodexPair:
    """Build the synthetic ``rule-<name>`` skill pair for a rule (ADR ai-1-2)."""
    # Imported lazily so this module does not depend on the path layer
    # at import time (path layer imports ElementType from elements).
    from ai_dotfiles.core import paths

    target = paths.project_codex_skills_dir(project_root) / f"rule-{rule_md.stem}"
    return CodexPair(ElementType.RULE, rule_md, target)


def _domain_codex_pairs(
    element: Element, project_root: Path, catalog: Path
) -> Iterator[CodexPair]:
    """Yield Codex pairs for every skill/agent member of a domain."""
    # Imported lazily so this module does not depend on the path layer
    # at import time (path layer imports ElementType from elements).
    from ai_dotfiles.core import paths

    domain_root = catalog / element.name
    for subdir, member_type in _CODEX_DOMAIN_SUBDIRS:
        source_dir = domain_root / subdir
        if not source_dir.is_dir():
            continue
        for entry in sorted(source_dir.iterdir()):
            if entry.name in _DOMAIN_SKIP_FILES or entry.name.startswith("."):
                continue
            if member_type is ElementType.SKILL:
                target = paths.project_codex_skills_dir(project_root) / entry.name
            else:
                target = (
                    paths.project_codex_agents_dir(project_root) / f"{entry.stem}.toml"
                )
            yield CodexPair(member_type, entry, target)


def iter_codex_pairs(
    element: Element, project_root: Path, catalog: Path
) -> list[CodexPair]:
    """Return the Codex skill/agent artefacts ``element`` produces.

    A domain is expanded into its skill/agent members (``hooks/``
    skipped — see :func:`codex_skipped_domain_subdirs`). A standalone
    skill/agent yields a single pair.

    Rules dispatch by :class:`~ai_dotfiles.core.rule_classify.RuleClass`
    (Phase 2, ADR ai-1-2): a *description-only* rule yields one
    :class:`CodexPair` of type :data:`ElementType.RULE` — the synthetic
    ``rule-<name>`` skill. Always-on / path-scoped rules have no
    skill/agent pair; they are returned by :func:`iter_codex_rule_plans`
    instead, so they contribute nothing here.
    """
    if element.type is ElementType.DOMAIN:
        pairs = list(_domain_codex_pairs(element, project_root, catalog))
        for rule_md in _iter_rule_sources(element, catalog):
            if classify_rule(rule_md) is RuleClass.DESCRIPTION_ONLY:
                pairs.append(_rule_skill_pair(rule_md, project_root))
        return pairs

    policy = render_policy_for(Target.CODEX, element.type)
    if policy.mode is RenderMode.SKIP:
        return []

    if element.type is ElementType.RULE:
        rule_md = resolve_source_path(element, catalog)
        if classify_rule(rule_md) is RuleClass.DESCRIPTION_ONLY:
            return [_rule_skill_pair(rule_md, project_root)]
        return []

    # Imported lazily for the same reason as above.
    from ai_dotfiles.core import paths

    source = resolve_source_path(element, catalog)
    if element.type is ElementType.SKILL:
        target = paths.project_codex_skills_dir(project_root) / element.name
    else:  # AGENT
        target = paths.project_codex_agents_dir(project_root) / f"{element.name}.toml"
    return [CodexPair(element.type, source, target)]


def iter_codex_rule_plans(
    element: Element, project_root: Path, catalog: Path
) -> list[CodexRulePlan]:
    """Return the ``AGENTS.md`` assembly plans ``element`` produces.

    Covers the always-on and path-scoped rules of a standalone ``rule:``
    element or every rule member of a domain. Description-only rules are
    *not* here — they render as synthetic skills via
    :func:`iter_codex_pairs`. Returns an empty list for skill/agent
    elements and for domains/rules with no always-on / path-scoped rule.
    """
    from ai_dotfiles.core.agents_md import rule_block_targets

    plans: list[CodexRulePlan] = []
    for rule_md in _iter_rule_sources(element, catalog):
        rule_class = classify_rule(rule_md)
        if rule_class is RuleClass.DESCRIPTION_ONLY:
            continue
        agents_md_paths = rule_block_targets(rule_md, project_root, rule_class.value)
        plans.append(CodexRulePlan(rule_md, rule_class.value, agents_md_paths))
    return plans
