"""Unit tests for ``ai_dotfiles.core.elements``."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_dotfiles.core.elements import (
    Element,
    ElementType,
    parse_element,
    parse_elements,
    resolve_source_path,
    resolve_target_paths,
    validate_element_exists,
)
from ai_dotfiles.core.errors import ElementError

# ---------------------------------------------------------------------------
# parse_element / parse_elements
# ---------------------------------------------------------------------------


def test_parse_domain() -> None:
    el = parse_element("@python")
    assert el == Element(ElementType.DOMAIN, "python", "@python")


def test_parse_skill() -> None:
    el = parse_element("skill:code-review")
    assert el.type is ElementType.SKILL
    assert el.name == "code-review"
    assert el.raw == "skill:code-review"


def test_parse_agent() -> None:
    el = parse_element("agent:researcher")
    assert el == Element(ElementType.AGENT, "researcher", "agent:researcher")


def test_parse_rule() -> None:
    el = parse_element("rule:security")
    assert el == Element(ElementType.RULE, "security", "rule:security")


def test_parse_invalid_no_prefix() -> None:
    with pytest.raises(ElementError):
        parse_element("foobar")


def test_parse_invalid_unknown_type() -> None:
    with pytest.raises(ElementError):
        parse_element("hook:foo")


def test_parse_invalid_empty() -> None:
    with pytest.raises(ElementError):
        parse_element("")


def test_parse_invalid_empty_domain() -> None:
    with pytest.raises(ElementError):
        parse_element("@")


def test_parse_invalid_empty_name() -> None:
    with pytest.raises(ElementError):
        parse_element("skill:")


def test_parse_invalid_name_with_slash() -> None:
    with pytest.raises(ElementError):
        parse_element("skill:foo/bar")


def test_parse_invalid_name_with_dot() -> None:
    with pytest.raises(ElementError):
        parse_element("agent:foo.md")


def test_parse_reserved_domain_underscore() -> None:
    with pytest.raises(ElementError):
        parse_element("@_private")


def test_parse_reserved_domain_example_allowed() -> None:
    el = parse_element("@_example")
    assert el == Element(ElementType.DOMAIN, "_example", "@_example")


def test_parse_elements_multiple() -> None:
    items = ["@python", "skill:code-review", "agent:researcher", "rule:security"]
    parsed = parse_elements(items)
    assert [e.type for e in parsed] == [
        ElementType.DOMAIN,
        ElementType.SKILL,
        ElementType.AGENT,
        ElementType.RULE,
    ]
    assert [e.name for e in parsed] == [
        "python",
        "code-review",
        "researcher",
        "security",
    ]


def test_parse_elements_empty() -> None:
    assert parse_elements([]) == []


def test_parse_elements_propagates_error() -> None:
    with pytest.raises(ElementError):
        parse_elements(["@python", "nope"])


def test_element_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    el = parse_element("@python")
    with pytest.raises(FrozenInstanceError):
        el.name = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# resolve_source_path
# ---------------------------------------------------------------------------


def test_resolve_source_domain(tmp_path: Path) -> None:
    el = parse_element("@python")
    assert resolve_source_path(el, tmp_path) == tmp_path / "python"


def test_resolve_source_skill(tmp_path: Path) -> None:
    el = parse_element("skill:code-review")
    assert resolve_source_path(el, tmp_path) == tmp_path / "skills" / "code-review"


def test_resolve_source_agent(tmp_path: Path) -> None:
    el = parse_element("agent:researcher")
    assert resolve_source_path(el, tmp_path) == tmp_path / "agents" / "researcher.md"


def test_resolve_source_rule(tmp_path: Path) -> None:
    el = parse_element("rule:security")
    assert resolve_source_path(el, tmp_path) == tmp_path / "rules" / "security.md"


# ---------------------------------------------------------------------------
# resolve_target_paths — domain
# ---------------------------------------------------------------------------


def _make_domain(catalog: Path, name: str) -> Path:
    root = catalog / name
    for sub in ("skills", "agents", "rules", "hooks"):
        (root / sub).mkdir(parents=True)
    return root


def test_resolve_target_domain(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    claude_dir = tmp_path / ".claude"
    root = _make_domain(catalog, "python")

    (root / "skills" / "pytest").mkdir()
    (root / "skills" / "pytest" / "SKILL.md").write_text("x")
    (root / "agents" / "researcher.md").write_text("x")
    (root / "rules" / "pep8.md").write_text("x")
    (root / "hooks" / "pre_commit.sh").write_text("x")

    el = parse_element("@python")
    pairs = resolve_target_paths(el, claude_dir, catalog)

    expected = {
        (root / "skills" / "pytest", claude_dir / "skills" / "pytest"),
        (root / "agents" / "researcher.md", claude_dir / "agents" / "researcher.md"),
        (root / "rules" / "pep8.md", claude_dir / "rules" / "pep8.md"),
        (root / "hooks" / "pre_commit.sh", claude_dir / "hooks" / "pre_commit.sh"),
    }
    assert set(pairs) == expected
    assert len(pairs) == len(expected)


def test_resolve_target_domain_skips_readme(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    claude_dir = tmp_path / ".claude"
    root = _make_domain(catalog, "python")
    (root / "agents" / "README.md").write_text("ignore me")
    (root / "agents" / "real.md").write_text("x")
    (root / "rules" / "README.md").write_text("ignore me")

    pairs = resolve_target_paths(parse_element("@python"), claude_dir, catalog)
    targets = {p[1].name for p in pairs}
    assert "README.md" not in targets
    assert "real.md" in targets


def test_resolve_target_domain_skips_settings_fragment(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    claude_dir = tmp_path / ".claude"
    root = _make_domain(catalog, "python")
    # settings.fragment.json typically lives at domain root, but guard it
    # even if someone drops it inside a subdir.
    (root / "agents" / "settings.fragment.json").write_text("{}")
    (root / "agents" / "real.md").write_text("x")

    pairs = resolve_target_paths(parse_element("@python"), claude_dir, catalog)
    names = {p[0].name for p in pairs}
    assert "settings.fragment.json" not in names
    assert "real.md" in names


def test_resolve_target_domain_missing_subdirs(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    claude_dir = tmp_path / ".claude"
    # Only skills/ exists; other subdirs are absent.
    (catalog / "python" / "skills" / "pytest").mkdir(parents=True)
    (catalog / "python" / "skills" / "pytest" / "SKILL.md").write_text("x")

    pairs = resolve_target_paths(parse_element("@python"), claude_dir, catalog)
    assert pairs == [
        (
            catalog / "python" / "skills" / "pytest",
            claude_dir / "skills" / "pytest",
        )
    ]


# ---------------------------------------------------------------------------
# resolve_target_paths — standalone
# ---------------------------------------------------------------------------


def test_resolve_target_standalone_skill(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    claude_dir = tmp_path / ".claude"
    pairs = resolve_target_paths(
        parse_element("skill:code-review"), claude_dir, catalog
    )
    assert pairs == [
        (
            catalog / "skills" / "code-review",
            claude_dir / "skills" / "code-review",
        )
    ]


def test_resolve_target_standalone_agent(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    claude_dir = tmp_path / ".claude"
    pairs = resolve_target_paths(parse_element("agent:researcher"), claude_dir, catalog)
    assert pairs == [
        (
            catalog / "agents" / "researcher.md",
            claude_dir / "agents" / "researcher.md",
        )
    ]


def test_resolve_target_standalone_rule(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    claude_dir = tmp_path / ".claude"
    pairs = resolve_target_paths(parse_element("rule:security"), claude_dir, catalog)
    assert pairs == [
        (
            catalog / "rules" / "security.md",
            claude_dir / "rules" / "security.md",
        )
    ]


# ---------------------------------------------------------------------------
# validate_element_exists
# ---------------------------------------------------------------------------


def test_validate_exists_ok_domain(tmp_path: Path) -> None:
    (tmp_path / "python").mkdir()
    validate_element_exists(parse_element("@python"), tmp_path)


def test_validate_exists_ok_skill(tmp_path: Path) -> None:
    (tmp_path / "skills" / "code-review").mkdir(parents=True)
    validate_element_exists(parse_element("skill:code-review"), tmp_path)


def test_validate_exists_ok_agent(tmp_path: Path) -> None:
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "researcher.md").write_text("x")
    validate_element_exists(parse_element("agent:researcher"), tmp_path)


def test_validate_exists_missing(tmp_path: Path) -> None:
    with pytest.raises(ElementError):
        validate_element_exists(parse_element("@nonexistent"), tmp_path)


def test_validate_exists_missing_skill(tmp_path: Path) -> None:
    with pytest.raises(ElementError):
        validate_element_exists(parse_element("skill:nope"), tmp_path)
