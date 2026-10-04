"""Native DSH root and skill-directory bindings for later collectors.

The filesystem provider discovers the closest Git root, whereas ai-dotfiles
installs at the manifest root. ``customSkillDirs`` explicitly binds those
outputs when the roots differ, including non-Git launches from a child cwd.
This module plans paths only; it does not render elements or native patches.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from ai_dotfiles.core import paths
from ai_dotfiles.core.dsh_layout import DshLayout, global_layout, project_layout

__all__ = [
    "DSH_AGENT_INSTRUCTIONS_PACKAGE",
    "DSH_CUSTOM_SKILL_DIRS_FIELD",
    "DSH_SKILL_FILESYSTEM_PACKAGE",
    "DshSkillProviderConfig",
    "DshTargetPlan",
    "global_target_plan",
    "project_target_plan",
]

# Native 0.2.0-rc.2 package names and configuration field; not Python aliases.
DSH_SKILL_FILESYSTEM_PACKAGE = "@deepseek-ai/dsh-skill-filesystem"
DSH_AGENT_INSTRUCTIONS_PACKAGE = "@deepseek-ai/dsh-agent-instructions"
DSH_CUSTOM_SKILL_DIRS_FIELD = "customSkillDirs"


class DshSkillProviderConfig(TypedDict, total=False):
    """The native filesystem-provider configuration contributed by a plan."""

    customSkillDirs: list[str]


@dataclass(frozen=True)
class DshTargetPlan:
    """Manifest outputs plus the native skill lookup for one launch cwd.

    User scope has no cwd or native project root. A project's binding is an
    addition to the effective provider's existing ``customSkillDirs``; the
    composition collector must merge it, preserving unrelated configuration.
    It does not change the native provider's root-discovery algorithm or the
    instruction loader's project-chain semantics.
    """

    layout: DshLayout
    cwd: Path | None
    native_project_root: Path | None
    custom_skill_dirs: tuple[Path, ...]

    def skill_provider_config(self) -> DshSkillProviderConfig:
        """Return native JSON fields for the required additional skill roots.

        Omit the field when no binding is needed, so an empty plan cannot
        reset a user's configured roots. This is configuration data, not a
        complete replacement patch for the native provider.
        """
        if not self.custom_skill_dirs:
            return {}
        return {"customSkillDirs": [str(path) for path in self.custom_skill_dirs]}


def project_target_plan(root: Path, cwd: Path | None = None) -> DshTargetPlan:
    """Plan a manifest's output tree for a native lookup from ``cwd``.

    The default launch cwd is the manifest root. Keep lexical absolute
    paths, matching Node, rather than following symlinks into another tree.
    """
    root = paths.dsh_absolute_path(root)
    launch_cwd = paths.dsh_absolute_path(cwd) if cwd is not None else root
    layout = project_layout(root)
    native_root = paths.find_dsh_project_root(launch_cwd)
    custom_dirs = (layout.skills_dir,) if native_root != root else ()
    return DshTargetPlan(layout, launch_cwd, native_root, custom_dirs)


def global_target_plan(
    configured_home: str | Path | None = None,
) -> DshTargetPlan:
    """Plan user-scope native outputs independently of the current project."""
    return DshTargetPlan(global_layout(configured_home), None, None, ())
