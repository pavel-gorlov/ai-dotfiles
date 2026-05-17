"""Unit tests for ai_dotfiles.core.codex_targets."""

from __future__ import annotations

from pathlib import Path

from ai_dotfiles.core.codex_targets import (
    codex_skipped_domain_subdirs,
    iter_codex_pairs,
    iter_codex_rule_plans,
)
from ai_dotfiles.core.elements import ElementType, parse_element

# A description-only rule: no frontmatter at all (the un-migrated default).
_RULE_DESC_ONLY = "# Some rule\n\nA description-only rule body.\n"
# An always-on rule.
_RULE_ALWAYS_ON = "---\nalways_on: true\n---\n\n# Always\n\nAlways-on body.\n"
# A path-scoped rule.
_RULE_PATH_SCOPED = "---\npaths:\n  - src/api\n---\n\n# Scoped\n\nPath-scoped body.\n"

_SKILL_MD = "---\nname: s\ndescription: A skill.\n---\n\nbody\n"
_AGENT_MD = "---\nname: a\ndescription: An agent.\n---\n\nbody\n"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _domain(catalog: Path, name: str) -> Path:
    root = catalog / name
    root.mkdir(parents=True, exist_ok=True)
    return root


# ── iter_codex_pairs: standalone elements ──────────────────────────


def test_standalone_skill_yields_one_skill_pair(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    _write(catalog / "skills" / "commit" / "SKILL.md", _SKILL_MD)
    element = parse_element("skill:commit")

    pairs = iter_codex_pairs(element, tmp_path / "proj", catalog)

    assert len(pairs) == 1
    assert pairs[0].element_type is ElementType.SKILL
    assert pairs[0].target == tmp_path / "proj" / ".agents" / "skills" / "commit"


def test_standalone_agent_yields_one_agent_pair(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    _write(catalog / "agents" / "writer.md", _AGENT_MD)
    element = parse_element("agent:writer")

    pairs = iter_codex_pairs(element, tmp_path / "proj", catalog)

    assert len(pairs) == 1
    assert pairs[0].element_type is ElementType.AGENT
    assert pairs[0].target == (tmp_path / "proj" / ".codex" / "agents" / "writer.toml")


def test_standalone_description_only_rule_yields_synthetic_skill_pair(
    tmp_path: Path,
) -> None:
    """A description-only rule (Phase 2) renders as a ``rule-<name>`` skill."""
    catalog = tmp_path / "catalog"
    _write(catalog / "rules" / "python.md", _RULE_DESC_ONLY)
    element = parse_element("rule:python")

    pairs = iter_codex_pairs(element, tmp_path / "proj", catalog)

    assert len(pairs) == 1
    assert pairs[0].element_type is ElementType.RULE
    assert pairs[0].source == catalog / "rules" / "python.md"
    assert pairs[0].target == (tmp_path / "proj" / ".agents" / "skills" / "rule-python")
    # An always-on / path-scoped rule has no skill pair.
    assert iter_codex_rule_plans(element, tmp_path / "proj", catalog) == []


def test_standalone_always_on_rule_yields_root_agents_md_plan(
    tmp_path: Path,
) -> None:
    """An always-on rule plans a managed block in the root AGENTS.md."""
    catalog = tmp_path / "catalog"
    _write(catalog / "rules" / "principles.md", _RULE_ALWAYS_ON)
    element = parse_element("rule:principles")
    proj = tmp_path / "proj"

    assert iter_codex_pairs(element, proj, catalog) == []
    plans = iter_codex_rule_plans(element, proj, catalog)

    assert len(plans) == 1
    assert plans[0].rule_class == "always_on"
    assert plans[0].agents_md_paths == [proj / "AGENTS.md"]


def test_standalone_path_scoped_rule_yields_nested_agents_md_plan(
    tmp_path: Path,
) -> None:
    """A path-scoped rule plans a managed block in each <dir>/AGENTS.md."""
    catalog = tmp_path / "catalog"
    _write(catalog / "rules" / "api.md", _RULE_PATH_SCOPED)
    element = parse_element("rule:api")
    proj = tmp_path / "proj"

    plans = iter_codex_rule_plans(element, proj, catalog)

    assert len(plans) == 1
    assert plans[0].rule_class == "path_scoped"
    assert plans[0].agents_md_paths == [(proj / "src" / "api" / "AGENTS.md")]


# ── iter_codex_pairs: domain expansion ─────────────────────────────


def test_domain_expands_skills_and_agents(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    domain = _domain(catalog, "gitflow")
    _write(domain / "skills" / "commit" / "SKILL.md", _SKILL_MD)
    _write(domain / "agents" / "reviewer.md", _AGENT_MD)
    element = parse_element("@gitflow")

    pairs = iter_codex_pairs(element, tmp_path / "proj", catalog)
    kinds = sorted(p.element_type.value for p in pairs)

    assert kinds == ["agent", "skill"]


def test_domain_expands_rules_into_codex_surfaces(tmp_path: Path) -> None:
    """A domain's rules render for the Codex target (Phase 2); hooks skip."""
    catalog = tmp_path / "catalog"
    domain = _domain(catalog, "python")
    _write(domain / "skills" / "fmt" / "SKILL.md", _SKILL_MD)
    _write(domain / "rules" / "style.md", _RULE_DESC_ONLY)
    _write(domain / "rules" / "principles.md", _RULE_ALWAYS_ON)
    _write(domain / "hooks" / "lint.sh", "echo\n")
    element = parse_element("@python")
    proj = tmp_path / "proj"

    pairs = iter_codex_pairs(element, proj, catalog)
    plans = iter_codex_rule_plans(element, proj, catalog)

    # The skill member plus the description-only rule's synthetic skill.
    kinds = sorted(p.element_type.value for p in pairs)
    assert kinds == ["rule", "skill"]
    # The always-on rule plans a root-AGENTS.md block.
    assert len(plans) == 1
    assert plans[0].agents_md_paths == [proj / "AGENTS.md"]


def test_domain_metadata_files_are_not_members(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    domain = _domain(catalog, "gitflow")
    _write(domain / "skills" / "commit" / "SKILL.md", _SKILL_MD)
    _write(domain / "agents" / "README.md", "readme\n")
    element = parse_element("@gitflow")

    pairs = iter_codex_pairs(element, tmp_path / "proj", catalog)

    assert len(pairs) == 1
    assert pairs[0].element_type is ElementType.SKILL


# ── codex_skipped_domain_subdirs ───────────────────────────────────


def test_skipped_subdirs_reports_only_hooks(tmp_path: Path) -> None:
    """Phase 2: rules render for Codex; only hooks remain skipped."""
    catalog = tmp_path / "catalog"
    domain = _domain(catalog, "python")
    _write(domain / "rules" / "style.md", _RULE_DESC_ONLY)
    _write(domain / "hooks" / "lint.sh", "echo\n")
    element = parse_element("@python")

    assert codex_skipped_domain_subdirs(element, catalog) == ["hooks"]


def test_skipped_subdirs_empty_when_none_present(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    domain = _domain(catalog, "gitflow")
    _write(domain / "skills" / "commit" / "SKILL.md", _SKILL_MD)
    element = parse_element("@gitflow")

    assert codex_skipped_domain_subdirs(element, catalog) == []


def test_skipped_subdirs_empty_for_standalone_element(tmp_path: Path) -> None:
    element = parse_element("skill:commit")
    assert codex_skipped_domain_subdirs(element, tmp_path / "catalog") == []
