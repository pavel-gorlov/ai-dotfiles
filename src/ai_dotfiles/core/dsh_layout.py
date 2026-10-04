"""Concrete project and user-scope DeepSeek Harness output paths.

Only recorded entries in the native skills tree and ai-dotfiles' resource
tree are managed. Shared instructions use marker-block ownership; native
home/profile patches and package manifests remain user-owned.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ai_dotfiles.core import paths
from ai_dotfiles.core.agents_md import AGENTS_FILENAME

__all__ = ["DshLayout", "global_layout", "project_layout"]


@dataclass(frozen=True)
class DshLayout:
    """One DSH render tree; ``project_root=None`` denotes user scope.

    A project's root is the manifest root, independent of the native Git
    discovery root. ``owned_roots`` bounds inventory/prune traversal, but
    does not claim ownership of arbitrary existing skills or resource files.
    """

    dsh_dir: Path
    skills_dir: Path
    root_agents_md: Path
    project_root: Path | None

    @property
    def owned_dir(self) -> Path:
        """Base for generated configuration, resources and ownership records."""
        return self.dsh_dir / "ai-dotfiles"

    @property
    def owned_roots(self) -> tuple[Path, Path]:
        """Bounded scan roots; deletion still requires per-entry provenance."""
        return self.skills_dir, self.owned_dir

    @property
    def config_path(self) -> Path:
        """Merged managed configuration snapshot, separate from native profiles."""
        return self.owned_dir / "config.json"

    @property
    def patch_path(self) -> Path:
        """Native JSON patch array supplied to a managed launch."""
        return self.owned_dir / "patch.json"

    @property
    def hooks_path(self) -> Path:
        """Combined managed command-hook configuration."""
        return self.owned_dir / "hooks.json"

    @property
    def bridge_path(self) -> Path:
        """Generated native prompt/policy bridge module."""
        return self.owned_dir / "bridge.mjs"

    @property
    def resources_dir(self) -> Path:
        """Origin-bound support files for managed contributions."""
        return self.owned_dir / "resources"

    @property
    def provenance_path(self) -> Path:
        """Catalog source, generator and resource ownership records."""
        return self.owned_dir / "provenance.json"

    @property
    def local_registry_path(self) -> Path:
        """Project-local migration ownership records."""
        return self.owned_dir / "local.json"


def project_layout(root: Path) -> DshLayout:
    """Compute outputs under a manifest root, without native root discovery."""
    return DshLayout(
        dsh_dir=paths.project_dsh_dir(root),
        skills_dir=paths.project_dsh_skills_dir(root),
        root_agents_md=root / AGENTS_FILENAME,
        project_root=root,
    )


def global_layout(configured_home: str | Path | None = None) -> DshLayout:
    """Compute user-scope outputs without inspecting any project or profile."""
    home = paths.dsh_home(configured_home)
    return DshLayout(
        dsh_dir=home,
        skills_dir=home / "skills",
        root_agents_md=home / AGENTS_FILENAME,
        project_root=None,
    )
