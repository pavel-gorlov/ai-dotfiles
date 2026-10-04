"""Unit tests for ``ai_dotfiles.core.elements``."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest

from ai_dotfiles.core.dsh_layout import DshLayout, global_layout, project_layout
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
from ai_dotfiles.core.targets import Target

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


# ---------------------------------------------------------------------------
# resolve_target_paths — Codex target
# ---------------------------------------------------------------------------


def test_resolve_target_default_is_claude(tmp_path: Path) -> None:
    # Omitting `target` and passing Target.CLAUDE explicitly must agree.
    catalog = tmp_path / "catalog"
    claude_dir = tmp_path / ".claude"
    default = resolve_target_paths(parse_element("skill:x"), claude_dir, catalog)
    explicit = resolve_target_paths(
        parse_element("skill:x"), claude_dir, catalog, target=Target.CLAUDE
    )
    assert default == explicit


def test_resolve_target_codex_skill(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    root = tmp_path / "project"
    pairs = resolve_target_paths(
        parse_element("skill:code-review"), root, catalog, target=Target.CODEX
    )
    assert pairs == [
        (
            catalog / "skills" / "code-review",
            root / ".agents" / "skills" / "code-review",
        )
    ]


def test_resolve_target_codex_agent(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    root = tmp_path / "project"
    pairs = resolve_target_paths(
        parse_element("agent:researcher"), root, catalog, target=Target.CODEX
    )
    assert pairs == [
        (
            catalog / "agents" / "researcher.md",
            root / ".codex" / "agents" / "researcher.toml",
        )
    ]


def test_resolve_target_codex_description_only_rule_is_synthetic_skill(
    tmp_path: Path,
) -> None:
    """A description-only rule resolves to its synthetic ``rule-<name>`` skill."""
    catalog = tmp_path / "catalog"
    root = tmp_path / "project"
    rule_md = catalog / "rules" / "security.md"
    rule_md.parent.mkdir(parents=True)
    rule_md.write_text("# Security\n\nA description-only rule body.\n")

    pairs = resolve_target_paths(
        parse_element("rule:security"), root, catalog, target=Target.CODEX
    )
    assert pairs == [(rule_md, root / ".agents" / "skills" / "rule-security")]


def test_resolve_target_codex_always_on_rule_is_root_agents_md(
    tmp_path: Path,
) -> None:
    """An always-on rule resolves to a managed block in the root AGENTS.md."""
    catalog = tmp_path / "catalog"
    root = tmp_path / "project"
    rule_md = catalog / "rules" / "principles.md"
    rule_md.parent.mkdir(parents=True)
    rule_md.write_text("---\nalways_on: true\n---\n\nAlways-on body.\n")

    pairs = resolve_target_paths(
        parse_element("rule:principles"), root, catalog, target=Target.CODEX
    )
    assert pairs == [(rule_md, root / "AGENTS.md")]


def test_resolve_target_codex_missing_rule_yields_no_pairs(
    tmp_path: Path,
) -> None:
    """An unresolvable rule file yields no Codex pairs rather than raising."""
    catalog = tmp_path / "catalog"
    root = tmp_path / "project"
    assert (
        resolve_target_paths(
            parse_element("rule:absent"), root, catalog, target=Target.CODEX
        )
        == []
    )


def test_resolve_target_codex_domain_expands_all_member_kinds(
    tmp_path: Path,
) -> None:
    """A domain expands into skill, agent, and rule Codex surfaces (Phase 2)."""
    catalog = tmp_path / "catalog"
    root = tmp_path / "project"
    domain = catalog / "python"
    (domain / "skills" / "pytest").mkdir(parents=True)
    (domain / "skills" / "pytest" / "SKILL.md").write_text("x")
    (domain / "agents").mkdir(parents=True)
    (domain / "agents" / "researcher.md").write_text("x")
    (domain / "rules").mkdir(parents=True)
    # A description-only rule (no frontmatter) -> synthetic rule-<name> skill.
    (domain / "rules" / "pep8.md").write_text("# PEP 8\n\nStyle guide.\n")

    pairs = resolve_target_paths(
        parse_element("@python"), root, catalog, target=Target.CODEX
    )
    assert set(pairs) == {
        (
            domain / "skills" / "pytest",
            root / ".agents" / "skills" / "pytest",
        ),
        (
            domain / "agents" / "researcher.md",
            root / ".codex" / "agents" / "researcher.toml",
        ),
        (
            domain / "rules" / "pep8.md",
            root / ".agents" / "skills" / "rule-pep8",
        ),
    }


# ---------------------------------------------------------------------------
# resolve_target_paths — DSH and mixed targets
# ---------------------------------------------------------------------------


@pytest.fixture(params=[False, True], ids=["project", "global"])
def dsh_layout(tmp_path: Path, request: pytest.FixtureRequest) -> DshLayout:
    if request.param:
        return global_layout(tmp_path / "dsh-home")
    return project_layout(tmp_path / "project")


def test_resolve_target_dsh_skill(tmp_path: Path, dsh_layout: DshLayout) -> None:
    catalog = tmp_path / "catalog"
    assert resolve_target_paths(
        parse_element("skill:code-review"), dsh_layout, catalog, target=Target.DSH
    ) == [(catalog / "skills" / "code-review", dsh_layout.skills_dir / "code-review")]


def test_resolve_target_dsh_project_root_matches_layout(tmp_path: Path) -> None:
    root = tmp_path / "project"
    catalog = tmp_path / "catalog"
    element = parse_element("skill:code-review")
    pairs = resolve_target_paths(element, root, catalog, target=Target.DSH)
    assert pairs == resolve_target_paths(
        element, project_layout(root), catalog, target=Target.DSH
    )
    assert pairs == [
        (catalog / "skills" / "code-review", root / ".dsh" / "skills" / "code-review")
    ]
    assert not root.exists()


def test_resolve_target_dsh_agent_is_native_config_row(
    tmp_path: Path, dsh_layout: DshLayout
) -> None:
    catalog = tmp_path / "catalog"
    assert resolve_target_paths(
        parse_element("agent:researcher"), dsh_layout, catalog, target=Target.DSH
    ) == [(catalog / "agents" / "researcher.md", dsh_layout.config_path)]


@pytest.mark.parametrize(
    ("metadata", "surface"),
    [
        ("", "config"),
        ("---\ndescription: Security guidance\n---\n", "config"),
        ("---\nalways_on: true\n---\n", "instructions"),
        ("---\npaths: []\nalways_on: true\n---\n", "instructions"),
        ("---\npaths: [src]\n---\n", None),
        ("---\npaths: [src]\nalways_on: true\n---\n", None),
        ("---\npaths: ['**/*.py']\n---\n", None),
        ("---\npaths: ['**/*.py']\nalways_on: true\n---\n", None),
        ("---\npaths:\n  - src\n  - '**/*.py'\n---\n", None),
        ("---\npaths: src\n---\n", None),
    ],
)
def test_resolve_target_dsh_rules_preserve_activation(
    tmp_path: Path, dsh_layout: DshLayout, metadata: str, surface: str | None
) -> None:
    catalog = tmp_path / "catalog"
    rule = catalog / "rules" / "security.md"
    rule.parent.mkdir(parents=True)
    rule.write_text(metadata + "\nRule body.\n", encoding="utf-8")
    pairs = resolve_target_paths(
        parse_element("rule:security"), dsh_layout, catalog, target=Target.DSH
    )
    if surface is None:
        assert pairs == []
    else:
        target = (
            dsh_layout.root_agents_md
            if surface == "instructions"
            else dsh_layout.config_path
        )
        assert pairs == [(rule, target)]
    assert not dsh_layout.dsh_dir.exists()


def test_resolve_target_dsh_missing_rule_yields_no_pairs(
    tmp_path: Path, dsh_layout: DshLayout
) -> None:
    assert (
        resolve_target_paths(
            parse_element("rule:absent"),
            dsh_layout,
            tmp_path / "catalog",
            target=Target.DSH,
        )
        == []
    )


def test_resolve_target_dsh_rule_read_error_names_source(
    tmp_path: Path, dsh_layout: DshLayout
) -> None:
    catalog = tmp_path / "catalog"
    rule = catalog / "rules" / "security.md"
    rule.parent.mkdir(parents=True)
    rule.write_text("Rule body.\n")
    with (
        patch.object(Path, "read_text", side_effect=PermissionError("denied")),
        pytest.raises(ElementError, match="Cannot read DSH rule") as error,
    ):
        resolve_target_paths(
            parse_element("rule:security"), dsh_layout, catalog, target=Target.DSH
        )
    assert str(rule) in str(error.value)
    assert isinstance(error.value.__cause__, PermissionError)


def test_resolve_target_dsh_domain_expands_native_members(
    tmp_path: Path, dsh_layout: DshLayout
) -> None:
    catalog = tmp_path / "catalog"
    domain = _make_domain(catalog, "python")
    (domain / "skills" / "pytest").mkdir()
    (domain / "agents" / "researcher.md").write_text("Agent body.\n")
    (domain / "rules" / "principles.md").write_text(
        "---\nalways_on: true\n---\n\nPrinciples.\n"
    )
    (domain / "rules" / "style.md").write_text("Unconditional Claude rule.\n")
    (domain / "rules" / "scoped.md").write_text("---\npaths: ['**/*.py']\n---\n")
    (domain / "agents" / "README.md").write_text("Metadata.\n")
    (domain / "agents" / ".hidden.md").write_text("Hidden.\n")
    (domain / "agents" / "dsh.fragment.json").write_text("[]\n")
    (domain / "skills" / "README.md").write_text("Metadata.\n")
    (domain / "hooks" / "pre_commit.sh").write_text("exit 0\n")

    assert resolve_target_paths(
        parse_element("@python"), dsh_layout, catalog, target=Target.DSH
    ) == [
        (domain / "skills" / "pytest", dsh_layout.skills_dir / "pytest"),
        (domain / "agents" / "researcher.md", dsh_layout.config_path),
        (domain / "rules" / "principles.md", dsh_layout.root_agents_md),
        (domain / "rules" / "style.md", dsh_layout.config_path),
    ]


def test_resolve_target_dsh_missing_domain_yields_no_pairs(
    tmp_path: Path, dsh_layout: DshLayout
) -> None:
    assert (
        resolve_target_paths(
            parse_element("@absent"),
            dsh_layout,
            tmp_path / "catalog",
            target=Target.DSH,
        )
        == []
    )


def test_resolve_target_mixed_skills_use_distinct_native_trees(tmp_path: Path) -> None:
    root = tmp_path / "project"
    catalog = tmp_path / "catalog"
    skill = parse_element("skill:code-review")
    targets = {
        target: resolve_target_paths(
            skill,
            root / ".claude" if target is Target.CLAUDE else root,
            catalog,
            target=target,
        )
        for target in Target
    }
    source = catalog / "skills" / "code-review"
    assert targets == {
        Target.CLAUDE: [(source, root / ".claude" / "skills" / "code-review")],
        Target.CODEX: [(source, root / ".agents" / "skills" / "code-review")],
        Target.DSH: [(source, root / ".dsh" / "skills" / "code-review")],
    }


@pytest.mark.parametrize(
    ("metadata", "codex_destination", "dsh_destination"),
    [
        ("", ".agents/skills/rule-security", ".dsh/ai-dotfiles/config.json"),
        ("---\npaths: ['**/*.py']\nalways_on: true\n---\n", "AGENTS.md", None),
    ],
)
def test_resolve_target_mixed_rules_keep_codex_classification(
    tmp_path: Path,
    metadata: str,
    codex_destination: str,
    dsh_destination: str | None,
) -> None:
    root = tmp_path / "project"
    catalog = tmp_path / "catalog"
    rule = catalog / "rules" / "security.md"
    rule.parent.mkdir(parents=True)
    rule.write_text(metadata + "\nRule body.\n")
    element = parse_element("rule:security")
    assert resolve_target_paths(element, root, catalog, target=Target.CODEX) == [
        (rule, root / codex_destination)
    ]
    expected_dsh = [] if dsh_destination is None else [(rule, root / dsh_destination)]
    assert (
        resolve_target_paths(element, root, catalog, target=Target.DSH) == expected_dsh
    )


@pytest.mark.parametrize("target", ["unknown", "codex", "dsh"])
def test_resolve_target_invalid_explicit_target_never_falls_through(
    tmp_path: Path, target: str
) -> None:
    with pytest.raises(ElementError, match="Unsupported target"):
        resolve_target_paths(
            parse_element("skill:x"), tmp_path, tmp_path, target=cast(Target, target)
        )


@pytest.mark.parametrize("target", [None, Target.CLAUDE, Target.CODEX])
def test_resolve_target_dsh_layout_requires_dsh_target(
    tmp_path: Path, target: Target | None
) -> None:
    with pytest.raises(ElementError, match="DSH layout requires"):
        resolve_target_paths(
            parse_element("skill:x"), global_layout(tmp_path), tmp_path, target=target
        )
