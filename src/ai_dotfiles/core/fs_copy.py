"""Filesystem copy primitives for self-contained targets.

The Codex target (and, from ai-21, the Claude target's copy mode) writes
*real* files rather than symlinks into the catalog. When the project and
the catalog live on different filesystems — a Windows project under
``/mnt/c/...`` while the catalog sits in WSL — a symlink into the catalog
points at a path native-Windows tooling cannot resolve. Copying makes the
installed artefact fully self-contained.

:func:`copy_tree_into` is the single primitive both targets use to mirror
a catalog item (a file or a directory) into an install directory,
preserving executable bits so ``scripts/*`` stays runnable.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ai_dotfiles.core.errors import LinkError

__all__ = ["copy_tree_into"]


def copy_tree_into(source: Path, dest: Path) -> None:
    """Copy ``source`` (file or directory) to ``dest``, replacing any prior copy.

    A directory is copied recursively with :func:`shutil.copytree`; a file
    with :func:`shutil.copy2`. Both preserve mode bits, so an executable
    ``scripts/run.sh`` stays executable after the copy.

    ``dest`` is removed first if it already exists, so re-installing
    refreshes the copy cleanly — a file deleted from the catalog source
    between installs does not linger.

    Raises:
        LinkError: if ``source`` does not exist or the copy fails.
    """
    if not source.exists():
        raise LinkError(f"Copy source does not exist: {source}")

    try:
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        elif dest.is_dir():
            shutil.rmtree(dest)
    except OSError as exc:
        raise LinkError(f"Failed to clear stale copy at {dest}: {exc}") from exc

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, dest)
        else:
            shutil.copy2(source, dest)
    except OSError as exc:
        raise LinkError(f"Failed to copy {source} -> {dest}: {exc}") from exc
