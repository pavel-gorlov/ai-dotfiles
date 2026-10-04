"""Native DeepSeek Harness path resolution contracts."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ai_dotfiles.core import paths
from ai_dotfiles.core.errors import ConfigError


@pytest.mark.parametrize("override", [None, "", " \t\n"])
def test_home_unset_or_blank_uses_default(
    override: str | None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    if override is None:
        monkeypatch.delenv("DSH_HOME", raising=False)
    else:
        monkeypatch.setenv("DSH_HOME", override)
    assert paths.dsh_home() == tmp_path / ".dsh"


def test_home_configuration_wins_over_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSH_HOME", str(tmp_path / "environment"))
    configured = tmp_path / "configured"
    assert paths.dsh_home(configured) == configured


def test_explicit_empty_configuration_resolves_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only blank environment overrides are unset in the native contract."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DSH_HOME", str(tmp_path / "environment"))
    assert paths.dsh_home("") == tmp_path


@pytest.mark.parametrize("value", ["~", "~/custom", "~\\custom", "~//custom"])
def test_home_expands_native_tilde_prefixes(
    value: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("DSH_HOME", value)
    expected = tmp_path if value == "~" else tmp_path / "custom"
    assert paths.dsh_home() == expected


@pytest.mark.parametrize("value", ["relative/../custom", " path with spaces "])
def test_home_normalizes_relative_values_without_trimming(
    value: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DSH_HOME", value)
    expected = "custom" if value.startswith("relative") else value
    assert paths.dsh_home() == tmp_path / expected


def test_home_does_not_expand_named_user_tildes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert paths.dsh_home("~another-user/state") == (
        tmp_path / "~another-user" / "state"
    )


@pytest.mark.skipif(os.name != "posix", reason="POSIX path normalization contract")
def test_home_collapses_posix_double_leading_slash(tmp_path: Path) -> None:
    assert paths.dsh_home("/" + str(tmp_path / "state")) == tmp_path / "state"


def test_home_preserves_symlink_spelling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    monkeypatch.setenv("DSH_HOME", str(alias / "state"))
    assert paths.dsh_home() == alias / "state"


def test_path_helpers_compute_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "absent-home"
    project = tmp_path / "absent-project"
    monkeypatch.setenv("DSH_HOME", str(home))
    assert paths.dsh_home() == home
    assert paths.project_dsh_dir(project) == project / ".dsh"
    assert paths.project_dsh_skills_dir(project) == project / ".dsh" / "skills"
    assert paths.project_dsh_owned_dir(project) == project / ".dsh" / "ai-dotfiles"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("worktree", [False, True])
def test_native_root_accepts_git_directory_or_worktree_file(
    worktree: bool, tmp_path: Path
) -> None:
    project = tmp_path / "project"
    child = project / "src" / "nested"
    child.mkdir(parents=True)
    marker = project / ".git"
    if worktree:
        marker.write_text("gitdir: /unused/worktrees/project\n", encoding="utf-8")
    else:
        marker.mkdir()
    assert paths.find_dsh_project_root(child) == project


def test_native_root_uses_closest_git_even_with_outer_manifest(tmp_path: Path) -> None:
    outer = tmp_path / "outer"
    inner = outer / "inner"
    child = inner / "src"
    child.mkdir(parents=True)
    (outer / ".git").mkdir()
    (outer / "ai-dotfiles.json").write_text("{}", encoding="utf-8")
    (inner / ".git").write_text("gitdir: /unused/inner\n", encoding="utf-8")
    assert paths.find_dsh_project_root(child) == inner
    assert paths.find_project_root(child) == outer.resolve()


def test_native_root_ignores_nested_manifest(tmp_path: Path) -> None:
    git_root = tmp_path / "repository"
    manifest_root = git_root / "package"
    child = manifest_root / "src"
    child.mkdir(parents=True)
    (git_root / ".git").mkdir()
    (manifest_root / "ai-dotfiles.json").write_text("{}", encoding="utf-8")
    assert paths.find_dsh_project_root(child) == git_root
    assert paths.find_project_root(child) == manifest_root.resolve()


def test_native_root_without_git_returns_cwd_and_ignores_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    child = project / "src"
    child.mkdir(parents=True)
    (project / "ai-dotfiles.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(child)
    monkeypatch.setattr(Path, "exists", lambda _: False)
    assert paths.find_dsh_project_root() == child


def test_native_root_normalizes_relative_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    assert paths.find_dsh_project_root(Path("src/../child")) == tmp_path


def test_native_root_preserves_symlink_spelling(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / ".git").mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    assert paths.find_dsh_project_root(alias / "src") == alias


def test_native_root_skips_failed_skill_marker_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".git").mkdir()
    child = tmp_path / "child"
    child.mkdir()
    original_exists = Path.exists

    def marker_exists(path: Path) -> bool:
        if path == child / ".git":
            raise PermissionError("unreadable marker")
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", marker_exists)
    assert paths.find_dsh_project_root(child) == tmp_path


def test_unusable_cwd_uses_existing_error_hierarchy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable_cwd() -> Path:
        raise ConfigError("Cannot determine the current working directory")

    monkeypatch.setattr(paths, "current_dir", unavailable_cwd)
    with pytest.raises(ConfigError, match="current working directory"):
        paths.find_dsh_project_root()
    with pytest.raises(ConfigError, match="current working directory"):
        paths.dsh_home("relative")
