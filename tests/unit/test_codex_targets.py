"""Unit tests for ai_dotfiles.core.codex_targets."""

from __future__ import annotations

from pathlib import Path

from ai_dotfiles.core.codex_targets import (
    codex_skipped_domain_subdirs,
    iter_codex_pairs,
)
from ai_dotfiles.core.elements import Element, ElementType, parse_element

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


def test_standalone_rule_yields_no_pairs(tmp_path: Path) -> None:
    """Rules have no Phase-1 Codex surface — skipped, not raised."""
    element = Element(ElementType.RULE, "python", "rule:python")
    assert iter_codex_pairs(element, tmp_path / "proj", tmp_path / "catalog") == []


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


def test_domain_skips_rules_and_hooks_members(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    domain = _domain(catalog, "python")
    _write(domain / "skills" / "fmt" / "SKILL.md", _SKILL_MD)
    _write(domain / "rules" / "style.md", "---\nname: style\n---\nbody\n")
    _write(domain / "hooks" / "lint.sh", "echo\n")
    element = parse_element("@python")

    pairs = iter_codex_pairs(element, tmp_path / "proj", catalog)

    assert len(pairs) == 1
    assert pairs[0].element_type is ElementType.SKILL


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


def test_skipped_subdirs_reports_rules_and_hooks(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    domain = _domain(catalog, "python")
    _write(domain / "rules" / "style.md", "---\nname: style\n---\nbody\n")
    _write(domain / "hooks" / "lint.sh", "echo\n")
    element = parse_element("@python")

    assert codex_skipped_domain_subdirs(element, catalog) == ["rules", "hooks"]


def test_skipped_subdirs_empty_when_none_present(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    domain = _domain(catalog, "gitflow")
    _write(domain / "skills" / "commit" / "SKILL.md", _SKILL_MD)
    element = parse_element("@gitflow")

    assert codex_skipped_domain_subdirs(element, catalog) == []


def test_skipped_subdirs_empty_for_standalone_element(tmp_path: Path) -> None:
    element = parse_element("skill:commit")
    assert codex_skipped_domain_subdirs(element, tmp_path / "catalog") == []
