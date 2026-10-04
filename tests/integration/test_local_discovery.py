"""Integration tests for :mod:`ai_dotfiles.core.local_discovery`.

Filesystem-backed: builds a project ``.claude/`` tree mixing local
(hand-authored) elements with catalog symlinks and asserts only the local
ones are discovered.
"""

from pathlib import Path

import pytest

from ai_dotfiles.core.claude_copy import copy_element
from ai_dotfiles.core.copy_ownership import save_copy_ownership
from ai_dotfiles.core.elements import ElementType, parse_element
from ai_dotfiles.core.errors import ConfigError
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


@pytest.mark.parametrize("modified", [False, True])
def test_catalog_domain_copies_are_not_local(
    tmp_path: Path, tmp_storage: Path, modified: bool
) -> None:
    project = tmp_path / "project"
    catalog = tmp_storage / "catalog"
    domain = catalog / "development"
    _write(domain / "skills" / "copied" / "SKILL.md", "# Catalog skill")
    _write(domain / "agents" / "copied.md", "# Catalog agent")
    _write(domain / "rules" / "copied.md", "# Catalog rule")
    copy_element(parse_element("@development"), project / ".claude", catalog)
    if modified:
        _write(project / ".claude" / "agents" / "copied.md", "User edited copy")
    _write(project / ".claude" / "agents" / "local.md", "# Catalog agent")

    found = list(iter_local_elements(project, manifest_packages=["@development"]))

    assert _keys(found) == {(ElementType.AGENT, "local")}


def test_catalog_linked_parent_is_not_local(tmp_path: Path, tmp_storage: Path) -> None:
    project = tmp_path / "project"
    directory = tmp_storage / "catalog" / "domain" / "agents"
    _write(directory / "managed.md", "# managed")
    (project / ".claude").mkdir(parents=True)
    (project / ".claude" / "agents").symlink_to(directory)

    assert list(iter_local_elements(project)) == []


@pytest.mark.parametrize(
    "label",
    ["../agents/escape.md", "/tmp/escape.md", "skills/../escape", "skills//escape"],
)
def test_copy_ledger_refuses_unsafe_paths(
    tmp_path: Path, tmp_storage: Path, label: str
) -> None:
    _write(tmp_path / ".claude" / "agents" / "local.md")
    save_copy_ownership(tmp_path / ".claude", {label})

    with pytest.raises(ConfigError, match="Unsafe Claude copy ownership"):
        list(iter_local_elements(tmp_path))
