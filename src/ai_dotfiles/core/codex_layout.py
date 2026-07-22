"""Scope-aware directory layout for the OpenAI Codex target.

The Codex target renders into two differently shaped trees:

* **project scope** — skills under ``<root>/.agents/skills/``, agents and
  the shared config/hooks under ``<root>/.codex/``, rule blocks in the
  project's ``AGENTS.md`` files;
* **global (user) scope** — everything under ``$CODEX_HOME`` (default
  ``~/.codex``): ``skills/``, ``agents/``, ``config.toml``, ``hooks.json``
  and the single global ``AGENTS.md``.

A :class:`CodexLayout` captures one such tree so the iteration layer
(:mod:`ai_dotfiles.core.codex_targets`) and the command layer can stay
scope-agnostic. ``project_root`` doubles as the scope discriminator:
``None`` means the global scope, which changes rule dispatch (a
path-scoped rule has no per-directory ``AGENTS.md`` surface without a
project tree — it demotes to a synthetic ``rule-<name>`` skill).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ai_dotfiles.core import paths
from ai_dotfiles.core.agents_md import AGENTS_FILENAME

__all__ = ["CodexLayout", "global_layout", "project_layout"]


@dataclass(frozen=True)
class CodexLayout:
    """One Codex render tree (project or global scope).

    ``skills_dir`` / ``agents_dir`` hold the rendered (or symlinked)
    skill directories and agent ``.toml`` files. ``codex_dir`` is the
    directory holding ``config.toml`` / ``hooks.json`` and the ownership
    sidecars. ``root_agents_md`` is where always-on rule blocks (and, at
    global scope, the instructions bridge) land. ``project_root`` is
    ``None`` at global scope.
    """

    skills_dir: Path
    agents_dir: Path
    codex_dir: Path
    root_agents_md: Path
    project_root: Path | None


def project_layout(root: Path) -> CodexLayout:
    """Return the project-scope Codex layout rooted at ``root``."""
    return CodexLayout(
        skills_dir=paths.project_codex_skills_dir(root),
        agents_dir=paths.project_codex_agents_dir(root),
        codex_dir=paths.project_codex_dir(root),
        root_agents_md=root / AGENTS_FILENAME,
        project_root=root,
    )


def global_layout() -> CodexLayout:
    """Return the user-scope Codex layout rooted at ``$CODEX_HOME``."""
    home = paths.codex_home()
    return CodexLayout(
        skills_dir=home / "skills",
        agents_dir=home / "agents",
        codex_dir=home,
        root_agents_md=home / AGENTS_FILENAME,
        project_root=None,
    )
