"""Path resolution for ai-dotfiles.

Centralizes all path computation. Every other module imports paths from here.
No directory creation happens in this module — functions only compute paths.
"""

from __future__ import annotations

import os
from pathlib import Path

from ai_dotfiles.core.errors import ConfigError


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


def bin_dir() -> Path:
    """Aggregated PATH directory for shims of domain ``bin/`` entries.

    Each installed domain that ships a ``bin/`` directory gets one shim
    per executable here, so users only have to add this single directory
    to ``PATH`` once.
    """
    return storage_root() / "bin"


def venvs_dir() -> Path:
    """Per-domain Python venvs (``~/.ai-dotfiles/venvs``).

    A domain that lists ``requires.python`` packages in ``domain.json``
    gets an isolated virtualenv at ``<venvs_dir>/<domain>``; the shim
    for its ``bin/<name>`` script invokes that venv's Python.
    """
    return storage_root() / "venvs"


def global_manifest_path() -> Path:
    """Manifest of globally installed packages."""
    return storage_root() / "global.json"


def claude_global_dir() -> Path:
    """Claude Code's global config directory (``~/.claude``)."""
    return Path.home() / ".claude"


def backup_dir() -> Path:
    """Location where conflicting files are moved (``~/.dotfiles-backup``)."""
    return Path.home() / ".dotfiles-backup"


def current_dir() -> Path:
    """Return the current working directory.

    ``Path.cwd()`` (i.e. ``os.getcwd``) raises ``FileNotFoundError`` when the
    process's CWD has been deleted or is otherwise unreadable — a real edge
    case under WSL with Windows-mount symlinks. Fall back to the shell-
    maintained ``PWD`` environment variable, and surface a clean
    :class:`ConfigError` if both fail rather than letting a raw traceback
    escape to the user.
    """
    try:
        return Path.cwd()
    except (FileNotFoundError, OSError):
        pass

    pwd = os.environ.get("PWD")
    if pwd:
        candidate = Path(pwd)
        try:
            if candidate.is_dir():
                return candidate
        except OSError:
            pass

    raise ConfigError(
        "Cannot determine the current working directory "
        "(it may have been deleted or become unreadable). "
        "cd to a valid directory and retry."
    )


def find_project_root(start: Path | None = None) -> Path | None:
    """Walk upward looking for a project root.

    Starting from ``start`` (default: current working directory), walks up
    the filesystem looking for a directory containing ``ai-dotfiles.json``.
    If none is found, a second pass looks for a ``.git`` directory.
    Returns ``None`` if neither marker is found before the filesystem root.
    """
    origin = (start if start is not None else current_dir()).resolve()

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
