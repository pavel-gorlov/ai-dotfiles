"""Shared pytest fixtures for ai-dotfiles tests."""

from pathlib import Path

import pytest

from tests.integration.test_dsh_bridge import (
    bridge_native_runtime as _bridge_native_runtime,
)

# Existing native suites keep their fixture imports. The required acceptance
# suite shares the same pinned, disposable setup rather than an optional skip.
bridge_native_runtime = _bridge_native_runtime


@pytest.fixture(scope="session")
def dsh_native_runtime(bridge_native_runtime: Path) -> Path:
    """Resolve exact official RC2; setup errors fail this required fixture."""
    return bridge_native_runtime


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


@pytest.fixture
def tmp_codex_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Set CODEX_HOME to a temp dir so tests never touch the real ~/.codex."""
    codex = tmp_path / ".codex"
    codex.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex))
    return codex
