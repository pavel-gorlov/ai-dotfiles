"""Integration tests for ``ai-dotfiles pull`` using a real local git remote."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_dotfiles.commands.pull import pull

pytestmark = pytest.mark.integration


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(
        cmd,
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
        env={
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "t@example.com",
            "HOME": str(cwd),
            "PATH": "/usr/bin:/bin:/usr/local/bin",
        },
    )


@pytest.fixture
def remote_and_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    """Create a bare remote, clone it as storage. Return (remote, storage) paths.

    Seeds both with an initial commit so fetching produces a sane base state.
    """
    remote = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    storage = tmp_path / ".ai-dotfiles"

    # Bare remote
    _run(["git", "init", "--bare", "--initial-branch=main", str(remote)], cwd=tmp_path)

    # Seed clone → initial commit → push
    _run(["git", "clone", str(remote), str(seed)], cwd=tmp_path)
    (seed / "README.md").write_text("initial\n")
    _run(["git", "add", "README.md"], cwd=seed)
    _run(["git", "commit", "-m", "chore: initial"], cwd=seed)
    _run(["git", "push", "origin", "main"], cwd=seed)

    # The real storage
    _run(["git", "clone", str(remote), str(storage)], cwd=tmp_path)

    monkeypatch.setenv("AI_DOTFILES_HOME", str(storage))
    return remote, storage


def _commit_on_remote(
    remote: Path, tmp_path: Path, filename: str, message: str
) -> None:
    """Push a new commit to ``remote`` via a throwaway clone."""
    work = tmp_path / f"work-{filename}"
    _run(["git", "clone", str(remote), str(work)], cwd=tmp_path)
    (work / filename).write_text("content\n")
    _run(["git", "add", filename], cwd=work)
    _run(["git", "commit", "-m", message], cwd=work)
    _run(["git", "push", "origin", "main"], cwd=work)


def test_pull_fast_forwards_new_commit(
    remote_and_storage: tuple[Path, Path], tmp_path: Path
) -> None:
    remote, storage = remote_and_storage
    _commit_on_remote(remote, tmp_path, "new.md", "feat: add new file")

    result = CliRunner().invoke(pull, [])

    assert result.exit_code == 0, result.output
    assert "1 new commit" in result.output
    assert "feat: add new file" in result.output
    assert "Pulled 1 commit" in result.output
    assert (storage / "new.md").is_file()


def test_pull_already_up_to_date(remote_and_storage: tuple[Path, Path]) -> None:
    result = CliRunner().invoke(pull, [])

    assert result.exit_code == 0, result.output
    assert "Already up to date." in result.output


def test_pull_refuses_dirty_worktree(
    remote_and_storage: tuple[Path, Path],
) -> None:
    _, storage = remote_and_storage
    (storage / "dirty.txt").write_text("uncommitted\n")

    result = CliRunner().invoke(pull, [])

    assert result.exit_code != 0
    assert "uncommitted changes" in result.output


def test_pull_refuses_when_not_a_git_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = tmp_path / ".ai-dotfiles"
    storage.mkdir()
    monkeypatch.setenv("AI_DOTFILES_HOME", str(storage))

    result = CliRunner().invoke(pull, [])

    assert result.exit_code != 0
    assert "not a git repository" in result.output


def test_pull_refuses_when_storage_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_DOTFILES_HOME", str(tmp_path / "missing"))

    result = CliRunner().invoke(pull, [])

    assert result.exit_code != 0
    assert "does not exist" in result.output


def test_pull_ff_only_fails_on_divergence(
    remote_and_storage: tuple[Path, Path], tmp_path: Path
) -> None:
    """If local and remote both have new commits, ff-only refuses with hint."""
    remote, storage = remote_and_storage

    # Local commit
    (storage / "local.md").write_text("local\n")
    _run(["git", "add", "local.md"], cwd=storage)
    _run(["git", "commit", "-m", "local: only-here"], cwd=storage)

    # Remote commit (different file)
    _commit_on_remote(remote, tmp_path, "remote.md", "feat: remote-only")

    result = CliRunner().invoke(pull, [])

    assert result.exit_code != 0
    assert "diverged" in result.output.lower()
    assert "--rebase" in result.output


def test_pull_rebase_replays_local_commits(
    remote_and_storage: tuple[Path, Path], tmp_path: Path
) -> None:
    remote, storage = remote_and_storage

    (storage / "local.md").write_text("local\n")
    _run(["git", "add", "local.md"], cwd=storage)
    _run(["git", "commit", "-m", "local: only-here"], cwd=storage)

    _commit_on_remote(remote, tmp_path, "remote.md", "feat: remote-only")

    result = CliRunner().invoke(pull, ["--rebase"])

    assert result.exit_code == 0, result.output
    assert (storage / "local.md").is_file()
    assert (storage / "remote.md").is_file()
