"""End-to-end test for .gitignore auto-management via the CLI."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_dotfiles.commands.add import add
from ai_dotfiles.commands.remove import remove
from ai_dotfiles.core.gitignore import MANAGED_END, MANAGED_START


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))
    return home_dir


@pytest.fixture
def storage(home: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    storage_dir = home / ".ai-dotfiles"
    storage_dir.mkdir()
    monkeypatch.setenv("AI_DOTFILES_HOME", str(storage_dir))
    return storage_dir


@pytest.fixture
def catalog(storage: Path) -> Path:
    cat = storage / "catalog"
    domain = cat / "testdomain"
    (domain / "skills" / "test-skill").mkdir(parents=True)
    (domain / "skills" / "test-skill" / "SKILL.md").write_text("x", encoding="utf-8")
    (domain / "agents").mkdir()
    (domain / "agents" / "test-agent.md").write_text("x", encoding="utf-8")
    return cat


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".git").mkdir()
    (proj / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    monkeypatch.chdir(proj)
    return proj


def test_add_then_remove_roundtrip_updates_gitignore(
    catalog: Path, project: Path
) -> None:
    runner = CliRunner()

    # 1. add
    assert runner.invoke(add, ["@testdomain"]).exit_code == 0

    text = (project / ".gitignore").read_text(encoding="utf-8")
    assert "node_modules/" in text
    assert MANAGED_START in text
    assert "/.claude/skills/test-skill" in text
    assert "/.claude/agents/test-agent.md" in text
    assert MANAGED_END in text

    # 2. remove
    assert runner.invoke(remove, ["@testdomain"]).exit_code == 0

    text_after = (project / ".gitignore").read_text(encoding="utf-8")
    assert MANAGED_START not in text_after
    assert MANAGED_END not in text_after
    assert "node_modules/" in text_after
