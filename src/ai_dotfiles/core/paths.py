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


def codex_home() -> Path:
    """Return OpenAI Codex CLI's user-scope config directory.

    Defaults to ``~/.codex``; may be overridden via the ``CODEX_HOME``
    environment variable (the same override Codex itself honours) —
    mirroring how :func:`storage_root` respects ``AI_DOTFILES_HOME``.
    """
    override = os.environ.get("CODEX_HOME")
    if override:
        return Path(override)
    return Path.home() / ".codex"


def dsh_home(configured: str | Path | None = None) -> Path:
    """Return the native DeepSeek Harness home as an absolute path.

    Match ``resolveDshHome`` in DSH 0.2.0-rc.2: an explicit configured
    value wins over ``DSH_HOME``, followed by ``~/.dsh``. Empty or blank
    environment overrides are unset; non-blank values retain whitespace.
    Only ``~``, ``~/`` and ``~\\`` prefixes expand, and normalization
    does not resolve symlinks or create directories.
    """
    override = os.environ.get("DSH_HOME")
    selected = (
        str(configured)
        if configured is not None
        else override if override is not None and override.strip() else None
    )
    if selected is None:
        candidate = Path.home() / ".dsh"
    elif selected == "~":
        candidate = Path.home()
    elif selected.startswith(("~/", "~\\")):
        candidate = Path(f"{Path.home()}{os.sep}{selected[2:]}")
    else:
        candidate = Path(selected)
    return dsh_absolute_path(candidate)


def dsh_absolute_path(path: str | Path) -> Path:
    """Normalize a native DSH path like Node's platform ``path.resolve``.

    Keep symlink spelling. POSIX Node collapses a double leading slash,
    unlike Python's ``normpath``; Windows retains its native UNC spelling.
    """
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = current_dir() / candidate
    normalized = os.path.normpath(candidate)
    if os.name == "posix":
        normalized = "/" + normalized.lstrip("/")
    return Path(normalized)


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


def find_dsh_project_root(start: Path | None = None) -> Path:
    """Return the native skill provider's nearest Git root or starting cwd.

    Unlike :func:`find_project_root`, DSH does not inspect manifests.
    A ``.git`` directory or worktree file is sufficient. Failed marker
    probes are skipped, matching the native skill provider (the separate
    instruction loader has stricter I/O-error semantics). Paths normalize
    lexically, without resolving symlinks, as Node's ``path.resolve`` does.
    """
    origin = dsh_absolute_path(start if start is not None else current_dir())
    current = origin
    while True:
        try:
            if (current / ".git").exists():
                return current
        except OSError:
            pass
        parent = current.parent
        if parent == current:
            return origin
        current = parent


def project_manifest_path(root: Path) -> Path:
    """Project manifest path (``<root>/ai-dotfiles.json``)."""
    return root / "ai-dotfiles.json"


def project_claude_dir(root: Path) -> Path:
    """Project-level Claude config directory (``<root>/.claude``)."""
    return root / ".claude"


def project_codex_dir(root: Path) -> Path:
    """Project-level Codex config directory (``<root>/.codex``).

    Holds ``config.toml``, ``hooks.json``, ``agents/`` and the
    ai-dotfiles ownership sidecars. The user-scope equivalent is
    :func:`codex_home`.
    """
    return root / ".codex"


def project_codex_skills_dir(root: Path) -> Path:
    """Project-level Codex skills directory (``<root>/.agents/skills``)."""
    return root / ".agents" / "skills"


def project_codex_agents_dir(root: Path) -> Path:
    """Project-level Codex agents directory (``<root>/.codex/agents``)."""
    return project_codex_dir(root) / "agents"


def project_dsh_dir(root: Path) -> Path:
    """Project-level DeepSeek Harness directory (``<root>/.dsh``)."""
    return root / ".dsh"


def project_dsh_skills_dir(root: Path) -> Path:
    """Native project DSH skills directory (``<root>/.dsh/skills``)."""
    return project_dsh_dir(root) / "skills"


def project_dsh_owned_dir(root: Path) -> Path:
    """ai-dotfiles' bounded project resource tree (``.dsh/ai-dotfiles``)."""
    return project_dsh_dir(root) / "ai-dotfiles"
