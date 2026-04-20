"""``ai-dotfiles init`` command.

Thin wrapper around :mod:`ai_dotfiles.core` and :mod:`ai_dotfiles.scaffold`.

Three modes:

- ``ai-dotfiles init`` — create a project manifest in the current project.
- ``ai-dotfiles init -g`` — scaffold ``~/.ai-dotfiles`` and link ``global/``
  into ``~/.claude/``.
- ``ai-dotfiles init -g --from <url>`` — clone an existing storage repo and
  link ``global/``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from ai_dotfiles import ui
from ai_dotfiles.core import git_ops, paths, symlinks
from ai_dotfiles.core.errors import AiDotfilesError
from ai_dotfiles.scaffold.generator import (
    generate_project_manifest,
    generate_storage_scaffold,
)


def _run_init_project() -> None:
    """Initialize a project manifest in the current project root."""
    root = paths.find_project_root() or Path.cwd()
    manifest = paths.project_manifest_path(root)
    if manifest.exists():
        ui.warn(f"ai-dotfiles.json already exists at {manifest}")
        return
    generate_project_manifest(root)
    ui.success(f"Created ai-dotfiles.json in {root}")


def _report_link_messages(messages: list[str]) -> None:
    """Emit one info line per link operation; note adopted files, if any."""
    adopted: list[str] = []
    for msg in messages:
        ui.info(f"  {msg}")
        if msg.startswith("adopted "):
            adopted.append(msg.removeprefix("adopted "))
    if adopted:
        joined = ", ".join(adopted)
        ui.info(
            f"Adopted existing {joined} into {paths.global_dir()} "
            "(your previous content is preserved as the storage source)."
        )


def _run_init_global(from_url: str | None) -> None:
    """Initialize global storage, optionally cloning it from a remote URL."""
    root = paths.storage_root()
    if root.exists() and any(root.iterdir()):
        ui.warn(f"Storage already exists at {root}")
        ui.info("If the existing storage is broken, remove it and retry:")
        ui.info(f"  rm -rf {root}")
        return

    if from_url is not None:
        # git clone refuses to target an existing (even empty) directory.
        if root.exists():
            root.rmdir()
        git_ops.git_clone(from_url, root)
        ui.success(f"Cloned {from_url} to {root}")
    else:
        generate_storage_scaffold(root)
        ui.success(f"Created storage at {root}")

    messages = symlinks.link_global_files(
        paths.global_dir(),
        paths.claude_global_dir(),
        paths.backup_dir(),
        adopt=from_url is None,
    )
    ui.success(f"Linked global/ -> {paths.claude_global_dir()}")
    _report_link_messages(messages)


@click.command()
@click.option(
    "-g",
    "--global",
    "is_global",
    is_flag=True,
    help="Initialize global storage at ~/.ai-dotfiles.",
)
@click.option(
    "--from",
    "from_url",
    default=None,
    help="Clone existing storage from a git URL (requires -g).",
)
def init(is_global: bool, from_url: str | None) -> None:
    """Initialize a project manifest or global storage."""
    if from_url is not None and not is_global:
        ui.error("--from requires -g")
        sys.exit(2)

    try:
        if is_global:
            _run_init_global(from_url)
        else:
            _run_init_project()
    except AiDotfilesError as exc:
        ui.error(str(exc))
        sys.exit(exc.exit_code)
