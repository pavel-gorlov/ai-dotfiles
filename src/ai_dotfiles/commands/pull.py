"""``ai-dotfiles pull`` — fetch and apply remote changes to the storage repo.

When ``~/.ai-dotfiles/`` (or ``$AI_DOTFILES_HOME``) is a git repository with
a configured remote (typically created via ``init -g --from <git-url>`` or
cloned manually), this command fast-forwards the local checkout to match
the remote.

Default strategy is ``--ff-only`` — safe, fails fast on divergence. Pass
``--rebase`` to rebase local commits onto the remote tip instead.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click

from ai_dotfiles import ui
from ai_dotfiles.core import git_ops, paths
from ai_dotfiles.core.errors import AiDotfilesError, ConfigError, ExternalError


def _require_git_repo(storage: Path) -> None:
    """Raise ``ConfigError`` if ``storage`` is not a git working tree."""
    if not (storage / ".git").exists():
        raise ConfigError(
            f"Storage {storage} is not a git repository. "
            "Run 'ai-dotfiles init -g --from <git-url>' to clone, or "
            "run 'git init && git remote add origin <url>' manually."
        )


def _require_clean_worktree(storage: Path) -> None:
    """Raise ``ConfigError`` if the working tree has uncommitted changes."""
    result = git_ops._run_git(["status", "--porcelain"], cwd=storage)
    if result.stdout.strip():
        raise ConfigError(
            f"Storage {storage} has uncommitted changes. "
            "Commit or stash them before pulling."
        )


def _current_branch(storage: Path) -> str:
    """Return the current branch name (fails on detached HEAD)."""
    result = git_ops._run_git(["symbolic-ref", "--short", "HEAD"], cwd=storage)
    return result.stdout.strip()


def _default_remote(storage: Path) -> str:
    """Return the remote name, preferring ``origin``. Raise if none configured."""
    result = git_ops._run_git(["remote"], cwd=storage)
    remotes = [r for r in result.stdout.splitlines() if r.strip()]
    if not remotes:
        raise ConfigError(
            f"Storage {storage} has no git remotes configured. "
            "Add one with 'git -C {storage} remote add origin <url>'."
        )
    if "origin" in remotes:
        return "origin"
    return remotes[0]


def _summarise_incoming(storage: Path, remote: str, branch: str) -> list[str]:
    """Return one-line summaries of commits in ``remote/branch`` but not HEAD."""
    try:
        result = git_ops._run_git(
            ["log", "--oneline", f"HEAD..{remote}/{branch}"],
            cwd=storage,
        )
    except ExternalError:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


@click.command("pull")
@click.option(
    "--rebase",
    is_flag=True,
    help="Rebase local commits onto the remote tip (default: fast-forward only).",
)
def pull(rebase: bool) -> None:
    """Fetch and apply remote changes to the storage repo."""
    try:
        storage = paths.storage_root()
        if not storage.is_dir():
            raise ConfigError(
                f"Storage {storage} does not exist. Run 'ai-dotfiles init -g' first."
            )

        _require_git_repo(storage)
        _require_clean_worktree(storage)

        branch = _current_branch(storage)
        remote = _default_remote(storage)

        ui.info(f"Fetching {remote}/{branch}...")
        git_ops._run_git(["fetch", remote, branch], cwd=storage)

        incoming = _summarise_incoming(storage, remote, branch)
        if not incoming:
            ui.info("Already up to date.")
            return

        ui.info(f"{len(incoming)} new commit{'s' if len(incoming) != 1 else ''}:")
        for line in incoming:
            ui.info(f"  {line}")

        strategy = "--rebase" if rebase else "--ff-only"
        try:
            git_ops._run_git(["pull", strategy, remote, branch], cwd=storage)
        except ExternalError as exc:
            if rebase:
                raise
            # ff-only failed — most likely divergence. Suggest --rebase.
            raise ConfigError(
                f"Cannot fast-forward: local branch has diverged from "
                f"{remote}/{branch}. Re-run with --rebase to replay local "
                "commits on top of the remote, or resolve manually."
            ) from exc

        ui.success(f"Pulled {len(incoming)} commit{'s' if len(incoming) != 1 else ''}.")
        ui.info("Hint: run 'ai-dotfiles install -g' to re-link updated global content.")

    except subprocess.TimeoutExpired as exc:  # pragma: no cover - defensive
        ui.error(f"git operation timed out: {exc}")
        sys.exit(1)
    except AiDotfilesError as exc:
        ui.error(str(exc))
        sys.exit(exc.exit_code)
