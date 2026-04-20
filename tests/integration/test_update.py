"""Integration tests for ``ai-dotfiles update``."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_dotfiles.commands.update import update
from ai_dotfiles.scaffold.generator import generate_storage_scaffold

pytestmark = pytest.mark.integration


def _setup_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    storage = tmp_path / ".ai-dotfiles"
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("AI_DOTFILES_HOME", str(storage))
    monkeypatch.setenv("HOME", str(home))
    generate_storage_scaffold(storage)
    return storage


def test_update_refreshes_builtin_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = _setup_storage(tmp_path, monkeypatch)
    skill = storage / "catalog" / "skills" / "ai-dotfiles" / "SKILL.md"
    # Simulate drift: user-visible regression in the storage copy.
    skill.write_text("stale content\n", encoding="utf-8")

    result = CliRunner().invoke(update, [])

    assert result.exit_code == 0, result.output
    refreshed = skill.read_text(encoding="utf-8")
    assert refreshed.startswith("---\n")
    assert "name: ai-dotfiles" in refreshed
    assert "stale content" not in refreshed
    assert str(skill) in result.output


def test_update_preserves_user_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = _setup_storage(tmp_path, monkeypatch)
    # User-authored file outside the builtin skill path.
    user_skill_dir = storage / "catalog" / "skills" / "my-skill"
    user_skill_dir.mkdir(parents=True)
    user_skill = user_skill_dir / "SKILL.md"
    user_skill.write_text("# my skill\n", encoding="utf-8")
    user_claude = storage / "global" / "CLAUDE.md"
    user_claude.write_text("my CLAUDE.md\n", encoding="utf-8")

    result = CliRunner().invoke(update, [])

    assert result.exit_code == 0, result.output
    assert user_skill.read_text(encoding="utf-8") == "# my skill\n"
    assert user_claude.read_text(encoding="utf-8") == "my CLAUDE.md\n"


def test_update_errors_when_storage_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = tmp_path / ".ai-dotfiles"  # never created
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("AI_DOTFILES_HOME", str(storage))
    monkeypatch.setenv("HOME", str(home))

    result = CliRunner().invoke(update, [])

    assert result.exit_code == 1
    assert "Storage not found" in result.output
    assert "init -g" in result.output
