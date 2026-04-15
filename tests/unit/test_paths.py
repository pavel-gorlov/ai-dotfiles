"""Unit tests for ai_dotfiles.core.paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_dotfiles.core import paths


def test_storage_root_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("AI_DOTFILES_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert paths.storage_root() == Path(str(tmp_path)) / ".ai-dotfiles"


def test_storage_root_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    custom = tmp_path / "custom-store"
    monkeypatch.setenv("AI_DOTFILES_HOME", str(custom))
    assert paths.storage_root() == custom


def test_global_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AI_DOTFILES_HOME", str(tmp_path))
    assert paths.global_dir() == tmp_path / "global"


def test_catalog_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AI_DOTFILES_HOME", str(tmp_path))
    assert paths.catalog_dir() == tmp_path / "catalog"


def test_stacks_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AI_DOTFILES_HOME", str(tmp_path))
    assert paths.stacks_dir() == tmp_path / "stacks"


def test_global_manifest_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AI_DOTFILES_HOME", str(tmp_path))
    assert paths.global_manifest_path() == tmp_path / "global.json"


def test_claude_global_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert paths.claude_global_dir() == Path(str(tmp_path)) / ".claude"


def test_backup_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert paths.backup_dir() == Path(str(tmp_path)) / ".dotfiles-backup"


def test_find_project_root_with_manifest(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    (project / "ai-dotfiles.json").write_text("{}")
    child = project / "sub" / "deep"
    child.mkdir(parents=True)

    assert paths.find_project_root(child) == project.resolve()


def test_find_project_root_with_git(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".git").mkdir()
    child = project / "src"
    child.mkdir()

    assert paths.find_project_root(child) == project.resolve()


def test_find_project_root_manifest_priority(tmp_path: Path) -> None:
    """Manifest in closer dir beats .git in outer dir."""
    outer = tmp_path / "outer"
    outer.mkdir()
    (outer / ".git").mkdir()

    inner = outer / "inner"
    inner.mkdir()
    (inner / "ai-dotfiles.json").write_text("{}")

    child = inner / "sub"
    child.mkdir()

    assert paths.find_project_root(child) == inner.resolve()


def test_find_project_root_none(tmp_path: Path) -> None:
    isolated = tmp_path / "nothing-here"
    isolated.mkdir()
    # Walk should terminate at filesystem root without finding markers.
    # If the real filesystem above tmp_path happens to contain a .git, this
    # test would be flaky; tmp_path is under pytest's own tmp tree which
    # does not contain such markers.
    result = paths.find_project_root(isolated)
    # Accept either None (clean env) or a path that is NOT below tmp_path
    # — only None represents the intended behavior, but guard against
    # ancestor .git directories in the test host.
    if result is not None:
        assert tmp_path.resolve() not in result.parents
        assert result != isolated.resolve()
    else:
        assert result is None


def test_project_manifest_path(tmp_path: Path) -> None:
    assert paths.project_manifest_path(tmp_path) == tmp_path / "ai-dotfiles.json"


def test_project_claude_dir(tmp_path: Path) -> None:
    assert paths.project_claude_dir(tmp_path) == tmp_path / ".claude"
