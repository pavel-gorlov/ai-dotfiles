"""E2E tests for ``ai-dotfiles create`` / ``ai-dotfiles delete``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_dotfiles.commands.create_delete import create, delete, find_usage


@pytest.fixture
def seeded_storage(tmp_storage: Path) -> Path:
    """Seed a minimal storage tree: catalog subdirs, empty global.json."""
    (tmp_storage / "catalog" / "skills").mkdir(parents=True)
    (tmp_storage / "catalog" / "agents").mkdir(parents=True)
    (tmp_storage / "catalog" / "rules").mkdir(parents=True)
    (tmp_storage / "global.json").write_text(
        json.dumps({"packages": []}, indent=2) + "\n", encoding="utf-8"
    )
    return tmp_storage


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


def test_create_skill(seeded_storage: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(create, ["skill", "my-linter"])
    assert result.exit_code == 0, result.output
    skill_md = seeded_storage / "catalog" / "skills" / "my-linter" / "SKILL.md"
    assert skill_md.is_file()
    assert "Created" in result.output


def test_create_agent(seeded_storage: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(create, ["agent", "reviewer"])
    assert result.exit_code == 0, result.output
    agent_md = seeded_storage / "catalog" / "agents" / "reviewer.md"
    assert agent_md.is_file()


def test_create_rule(seeded_storage: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(create, ["rule", "code-style"])
    assert result.exit_code == 0, result.output
    rule_md = seeded_storage / "catalog" / "rules" / "code-style.md"
    assert rule_md.is_file()


def test_create_already_exists(seeded_storage: Path) -> None:
    runner = CliRunner()
    runner.invoke(create, ["agent", "dupe"])
    result = runner.invoke(create, ["agent", "dupe"])
    assert result.exit_code != 0
    assert "already exists" in (result.output + (result.stderr or ""))


def test_create_template_has_name(seeded_storage: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(create, ["skill", "my-thing"])
    assert result.exit_code == 0, result.output
    content = (
        seeded_storage / "catalog" / "skills" / "my-thing" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "my-thing" in content
    assert "{{name}}" not in content


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def test_delete_skill(seeded_storage: Path) -> None:
    runner = CliRunner()
    runner.invoke(create, ["skill", "to-remove"])
    skill_dir = seeded_storage / "catalog" / "skills" / "to-remove"
    assert skill_dir.is_dir()

    result = runner.invoke(delete, ["skill", "to-remove", "--force"])
    assert result.exit_code == 0, result.output
    assert not skill_dir.exists()


def test_delete_agent(seeded_storage: Path) -> None:
    runner = CliRunner()
    runner.invoke(create, ["agent", "gone"])
    agent_md = seeded_storage / "catalog" / "agents" / "gone.md"
    assert agent_md.is_file()

    result = runner.invoke(delete, ["agent", "gone", "--force"])
    assert result.exit_code == 0, result.output
    assert not agent_md.exists()


def test_delete_not_found(seeded_storage: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(delete, ["rule", "nothing-here", "--force"])
    assert result.exit_code != 0
    assert "not found" in (result.output + (result.stderr or ""))


def test_delete_warns_if_used(seeded_storage: Path) -> None:
    runner = CliRunner()
    runner.invoke(create, ["skill", "used-one"])

    # Reference it from the global manifest.
    global_manifest = seeded_storage / "global.json"
    global_manifest.write_text(
        json.dumps({"packages": ["skill:used-one"]}, indent=2) + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(delete, ["skill", "used-one", "--force"])
    assert result.exit_code == 0, result.output
    assert "used in" in result.output
    assert "global.json" in result.output


def test_delete_confirmation_abort(seeded_storage: Path) -> None:
    runner = CliRunner()
    runner.invoke(create, ["agent", "keep-me"])
    agent_md = seeded_storage / "catalog" / "agents" / "keep-me.md"

    # Answer "n" to the prompt -> file must survive.
    result = runner.invoke(delete, ["agent", "keep-me"], input="n\n")
    assert result.exit_code == 0, result.output
    assert agent_md.exists()


# ---------------------------------------------------------------------------
# find_usage
# ---------------------------------------------------------------------------


def test_find_usage_in_manifest(seeded_storage: Path, tmp_project: Path) -> None:
    manifest = tmp_project / "ai-dotfiles.json"
    manifest.write_text(
        json.dumps({"packages": ["skill:my-thing"]}, indent=2) + "\n",
        encoding="utf-8",
    )
    usages = find_usage("skill:my-thing", seeded_storage, tmp_project)
    assert "ai-dotfiles.json" in usages


def test_find_usage_nowhere(seeded_storage: Path) -> None:
    usages = find_usage("skill:ghost", seeded_storage, None)
    assert usages == []
