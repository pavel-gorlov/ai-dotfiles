"""Integration tests for ``ai-dotfiles init`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from ai_dotfiles.commands.init import init
from ai_dotfiles.scaffold.generator import generate_storage_scaffold

pytestmark = pytest.mark.integration


def test_init_project(tmp_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_project)
    runner = CliRunner()

    result = runner.invoke(init, [])

    assert result.exit_code == 0, result.output
    manifest = tmp_project / "ai-dotfiles.json"
    assert manifest.is_file()
    assert "Created ai-dotfiles.json" in result.output


def test_init_project_already_exists(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_project)
    manifest = tmp_project / "ai-dotfiles.json"
    manifest.write_text('{"packages": ["keep-me"]}\n', encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(init, [])

    assert result.exit_code == 0
    # Existing content is preserved.
    assert "keep-me" in manifest.read_text(encoding="utf-8")
    assert "already exists" in result.output


def test_init_global(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage = tmp_path / ".ai-dotfiles"
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("AI_DOTFILES_HOME", str(storage))
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(init, ["-g"])

    assert result.exit_code == 0, result.output
    assert (storage / "global" / "CLAUDE.md").is_file()
    assert (storage / "global.json").is_file()
    claude_dir = home / ".claude"
    assert (claude_dir / "CLAUDE.md").is_symlink()
    assert (claude_dir / "settings.json").is_symlink()
    assert "Created storage" in result.output
    assert "Linked global/" in result.output


def test_init_global_already_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = tmp_path / ".ai-dotfiles"
    storage.mkdir()
    (storage / "global.json").write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("AI_DOTFILES_HOME", str(storage))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    runner = CliRunner()
    result = runner.invoke(init, ["-g"])

    assert result.exit_code == 0
    assert "already exists" in result.output
    # Untouched.
    assert (storage / "global.json").read_text(encoding="utf-8") == "{}\n"


def test_init_global_from_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage = tmp_path / ".ai-dotfiles"
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("AI_DOTFILES_HOME", str(storage))
    monkeypatch.setenv("HOME", str(home))

    called: dict[str, Any] = {}

    def fake_clone(url: str, dest: Path, branch: str | None = None) -> None:
        called["url"] = url
        called["dest"] = dest
        # Simulate a clone by producing a valid scaffold at dest.
        generate_storage_scaffold(dest)

    monkeypatch.setattr("ai_dotfiles.commands.init.git_ops.git_clone", fake_clone)

    runner = CliRunner()
    result = runner.invoke(init, ["-g", "--from", "https://github.com/owner/repo"])

    assert result.exit_code == 0, result.output
    assert called["url"] == "https://github.com/owner/repo"
    assert called["dest"] == storage
    assert (home / ".claude" / "CLAUDE.md").is_symlink()
    assert "Cloned" in result.output
    assert "Linked global/" in result.output


def test_init_from_without_global(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_project)
    runner = CliRunner()

    result = runner.invoke(init, ["--from", "https://github.com/owner/repo"])

    assert result.exit_code != 0
    assert "--from requires -g" in result.output


def test_init_global_creates_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = tmp_path / ".ai-dotfiles"
    home = tmp_path / "home"
    home.mkdir()
    claude_dir = home / ".claude"
    claude_dir.mkdir()
    existing = claude_dir / "CLAUDE.md"
    existing.write_text("user-previous-content\n", encoding="utf-8")

    monkeypatch.setenv("AI_DOTFILES_HOME", str(storage))
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(init, ["-g"])

    assert result.exit_code == 0, result.output
    # Old file backed up under ~/.dotfiles-backup, new one is a symlink.
    assert (claude_dir / "CLAUDE.md").is_symlink()
    backed = home / ".dotfiles-backup" / ".claude" / "CLAUDE.md"
    assert backed.is_file()
    assert backed.read_text(encoding="utf-8") == "user-previous-content\n"
    assert "backed up" in result.output.lower()
