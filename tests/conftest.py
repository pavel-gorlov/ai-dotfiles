"""Shared pytest fixtures for ai-dotfiles tests."""

from pathlib import Path

import pytest


@pytest.fixture
def tmp_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Set AI_DOTFILES_HOME to a temp dir, return the path."""
    storage = tmp_path / ".ai-dotfiles"
    storage.mkdir()
    monkeypatch.setenv("AI_DOTFILES_HOME", str(storage))
    return storage


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a temp project dir with .git, return the path."""
    project = tmp_path / "my-project"
    project.mkdir()
    (project / ".git").mkdir()
    return project


@pytest.fixture
def tmp_claude_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Override HOME so ~/.claude/ points to temp."""
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path
