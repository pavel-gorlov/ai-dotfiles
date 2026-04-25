"""Path resolution for ai-dotfiles.

Centralizes all path computation. Every other module imports paths from here.
No directory creation happens in this module — functions only compute paths.
"""

from __future__ import annotations

import os
from pathlib import Path


def storage_root() -> Path:
    """Return the root storage directory.

    Defaults to ``~/.ai-dotfiles``; may be overridden via the
    ``AI_DOTFILES_HOME`` environment variable.
    """
    override = os.environ.get("AI_DOTFILES_HOME")
    if override:
        return Path(override)
    return Path.home() / ".ai-dotfiles"


def global_dir() -> Path:
    """Physical files that get symlinked into ``~/.claude/``."""
    return storage_root() / "global"


def catalog_dir() -> Path:
    """All installable content (skills, agents, rules, domains)."""
    return storage_root() / "catalog"


def completion_dir() -> Path:
    """Cached shell completion scripts (``~/.ai-dotfiles/completions``)."""
    return storage_root() / "completions"


def global_manifest_path() -> Path:
    """Manifest of globally installed packages."""
    return storage_root() / "global.json"


def claude_global_dir() -> Path:
    """Claude Code's global config directory (``~/.claude``)."""
    return Path.home() / ".claude"


def backup_dir() -> Path:
    """Location where conflicting files are moved (``~/.dotfiles-backup``)."""
    return Path.home() / ".dotfiles-backup"


def find_project_root(start: Path | None = None) -> Path | None:
    """Walk upward looking for a project root.

    Starting from ``start`` (default: current working directory), walks up
    the filesystem looking for a directory containing ``ai-dotfiles.json``.
    If none is found, a second pass looks for a ``.git`` directory.
    Returns ``None`` if neither marker is found before the filesystem root.
    """
    origin = (start if start is not None else Path.cwd()).resolve()

    # First pass: prefer ai-dotfiles.json (closer wins).
    current = origin
    while True:
        if (current / "ai-dotfiles.json").is_file():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent

    # Second pass: fall back to .git marker.
    current = origin
    while True:
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent

    return None


def project_manifest_path(root: Path) -> Path:
    """Project manifest path (``<root>/ai-dotfiles.json``)."""
    return root / "ai-dotfiles.json"


def project_claude_dir(root: Path) -> Path:
    """Project-level Claude config directory (``<root>/.claude``)."""
    return root / ".claude"
