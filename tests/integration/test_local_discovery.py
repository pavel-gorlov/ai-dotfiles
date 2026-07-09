"""Integration tests for :mod:`ai_dotfiles.core.local_discovery`.

Filesystem-backed: builds a project ``.claude/`` tree mixing local
(hand-authored) elements with catalog symlinks and asserts only the local
ones are discovered.
"""

from pathlib import Path

import pytest

from ai_dotfiles.core.elements import ElementType
from ai_dotfiles.core.local_discovery import LocalElement, iter_local_elements

pytestmark = pytest.mark.integration


def _write(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build_tree(project: Path, storage: Path) -> None:
    """Populate ``project/.claude`` with a mix of local and catalog entries."""
    catalog = storage / "catalog"
    claude = project / ".claude"

    # ── local elements (real files/dirs) ──────────────────────────────
    _write(
        claude / "skills" / "local-skill" / "SKILL.md", "---\nname: local-skill\n---"
    )
    _write(claude / "rules" / "local-rule.md", "# local rule")
    _write(claude / "agents" / "local-agent.md", "---\nname: local-agent\n---")

    # ── catalog-managed (symlinks into storage) ───────────────────────
    _write(catalog / "skills" / "cat-skill" / "SKILL.md", "---\nname: cat-skill\n---")
    (claude / "skills" / "cat-skill").symlink_to(catalog / "skills" / "cat-skill")

    _write(catalog / "rules" / "python.md", "# python rule")
    (claude / "rules" / "python.md").symlink_to(catalog / "rules" / "python.md")

    _write(catalog / "agents" / "git.md", "---\nname: git\n---")
    (claude / "agents" / "git.md").symlink_to(catalog / "agents" / "git.md")

    # ── noise that must be ignored ────────────────────────────────────
    (claude / "skills" / "not-a-skill").mkdir()  # dir without SKILL.md
    _write(claude / "skills" / ".hidden" / "SKILL.md")  # hidden dir
    _write(claude / "rules" / ".DS_Store")  # hidden file
    _write(claude / "rules" / "notes.txt")  # non-markdown


def _keys(elements: list[LocalElement]) -> set[tuple[ElementType, str]]:
    return {(el.type, el.name) for el in elements}


def test_discovers_only_local_elements(tmp_path: Path, tmp_storage: Path) -> None:
    project = tmp_path / "proj"
    _build_tree(project, tmp_storage)

    found = list(iter_local_elements(project))

    assert _keys(found) == {
        (ElementType.SKILL, "local-skill"),
        (ElementType.RULE, "local-rule"),
        (ElementType.AGENT, "local-agent"),
    }


def test_local_element_carries_real_source_and_specifier(
    tmp_path: Path, tmp_storage: Path
) -> None:
    project = tmp_path / "proj"
    _build_tree(project, tmp_storage)

    by_name = {el.name: el for el in iter_local_elements(project)}

    skill = by_name["local-skill"]
    assert skill.raw == "skill:local-skill"
    assert skill.source_path == project / ".claude" / "skills" / "local-skill"
    assert not skill.source_path.is_symlink()

    rule = by_name["local-rule"]
    assert rule.raw == "rule:local-rule"
    assert rule.source_path == project / ".claude" / "rules" / "local-rule.md"


def test_manifest_named_elements_are_excluded(
    tmp_path: Path, tmp_storage: Path
) -> None:
    project = tmp_path / "proj"
    _build_tree(project, tmp_storage)

    found = list(
        iter_local_elements(project, manifest_packages=["skill:local-skill", "@domain"])
    )

    # local-skill is now manifest-declared -> excluded; the rest remain.
    assert _keys(found) == {
        (ElementType.RULE, "local-rule"),
        (ElementType.AGENT, "local-agent"),
    }


def test_ordering_is_skills_then_agents_then_rules(
    tmp_path: Path, tmp_storage: Path
) -> None:
    project = tmp_path / "proj"
    _build_tree(project, tmp_storage)

    order = [el.type for el in iter_local_elements(project)]

    assert order == [ElementType.SKILL, ElementType.AGENT, ElementType.RULE]


def test_missing_claude_dir_yields_nothing(tmp_path: Path, tmp_storage: Path) -> None:
    project = tmp_path / "empty-proj"
    project.mkdir()

    assert list(iter_local_elements(project)) == []


def test_symlink_pointing_outside_storage_is_local(
    tmp_path: Path, tmp_storage: Path
) -> None:
    """A symlink that does NOT resolve into storage is a user link -> local."""
    project = tmp_path / "proj"
    external = tmp_path / "external" / "my-skill"
    _write(external / "SKILL.md", "---\nname: my-skill\n---")
    (project / ".claude" / "skills").mkdir(parents=True)
    (project / ".claude" / "skills" / "my-skill").symlink_to(external)

    found = list(iter_local_elements(project))

    assert _keys(found) == {(ElementType.SKILL, "my-skill")}
