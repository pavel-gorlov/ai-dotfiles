"""Codex-target element iteration shared by the command layer.

``install`` / ``add`` / ``remove`` / ``status`` all need to walk a
manifest element and ask "which Codex artefacts does this produce?".
That walk — domain expansion, skill-vs-agent classification, the
rules/hooks skip — lives here so the four command modules stay thin
wrappers and the logic has a single home (project rule: business logic
belongs in ``core/``).

Each :class:`CodexPair` ties a catalog ``source`` to its rendered Codex
``target`` path and records the originating :class:`ElementType` so the
caller can dispatch to the right :mod:`ai_dotfiles.core.codex_install`
function.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from ai_dotfiles.core.elements import Element, ElementType, resolve_source_path
from ai_dotfiles.core.targets import RenderMode, Target, render_policy_for

__all__ = ["CodexPair", "codex_skipped_domain_subdirs", "iter_codex_pairs"]

# Domain subdirectories that have a Phase-1 Codex surface, paired with
# the element type each member is rendered as.
_CODEX_DOMAIN_SUBDIRS: tuple[tuple[str, ElementType], ...] = (
    ("skills", ElementType.SKILL),
    ("agents", ElementType.AGENT),
)

# Domain subdirectories with no Phase-1 Codex surface — skipped with an
# explicit message rather than failing (rules are Phase 2; Codex has no
# hook harness).
_CODEX_SKIP_SUBDIRS: tuple[str, ...] = ("rules", "hooks")

# Files that are domain metadata, never an installable member.
_DOMAIN_SKIP_FILES: frozenset[str] = frozenset(
    {"README.md", "domain.json", "settings.fragment.json", "mcp.fragment.json"}
)


@dataclass(frozen=True)
class CodexPair:
    """One catalog source rendered to one Codex target path.

    ``element_type`` is :data:`ElementType.SKILL` or
    :data:`ElementType.AGENT` — the only two types with a Phase-1 Codex
    surface. ``source`` is the catalog path (a skill directory or an
    agent ``.md``); ``target`` is the rendered destination
    (``.agents/skills/<name>/`` or ``.codex/agents/<name>.toml``).
    """

    element_type: ElementType
    source: Path
    target: Path


def codex_skipped_domain_subdirs(element: Element, catalog: Path) -> list[str]:
    """Return the non-empty ``rules``/``hooks`` subdirs of a domain.

    These have no Phase-1 Codex surface; the command layer reports the
    skip explicitly. Returns an empty list for non-domain elements or
    domains without those subdirectories.
    """
    if element.type is not ElementType.DOMAIN:
        return []
    domain_root = catalog / element.name
    skipped: list[str] = []
    for sub in _CODEX_SKIP_SUBDIRS:
        sub_dir = domain_root / sub
        if sub_dir.is_dir() and any(
            child.name not in _DOMAIN_SKIP_FILES and not child.name.startswith(".")
            for child in sub_dir.iterdir()
        ):
            skipped.append(sub)
    return skipped


def _domain_codex_pairs(
    element: Element, project_root: Path, catalog: Path
) -> Iterator[CodexPair]:
    """Yield Codex pairs for every skill/agent member of a domain."""
    # Imported lazily so this module does not depend on the path layer
    # at import time (path layer imports ElementType from elements).
    from ai_dotfiles.core import paths

    domain_root = catalog / element.name
    for subdir, member_type in _CODEX_DOMAIN_SUBDIRS:
        source_dir = domain_root / subdir
        if not source_dir.is_dir():
            continue
        for entry in sorted(source_dir.iterdir()):
            if entry.name in _DOMAIN_SKIP_FILES or entry.name.startswith("."):
                continue
            if member_type is ElementType.SKILL:
                target = paths.project_codex_skills_dir(project_root) / entry.name
            else:
                target = (
                    paths.project_codex_agents_dir(project_root) / f"{entry.stem}.toml"
                )
            yield CodexPair(member_type, entry, target)


def iter_codex_pairs(
    element: Element, project_root: Path, catalog: Path
) -> list[CodexPair]:
    """Return the Codex artefacts ``element`` produces, project-scoped.

    A domain is expanded into its skill/agent members (rules/hooks
    skipped — see :func:`codex_skipped_domain_subdirs`). A standalone
    skill/agent yields a single pair. A standalone rule has no Phase-1
    Codex surface and yields an empty list — the command layer reports
    the skip.
    """
    if element.type is ElementType.DOMAIN:
        return list(_domain_codex_pairs(element, project_root, catalog))

    policy = render_policy_for(Target.CODEX, element.type)
    if policy.mode is RenderMode.SKIP:
        return []

    # Imported lazily for the same reason as above.
    from ai_dotfiles.core import paths

    source = resolve_source_path(element, catalog)
    if element.type is ElementType.SKILL:
        target = paths.project_codex_skills_dir(project_root) / element.name
    else:  # AGENT
        target = paths.project_codex_agents_dir(project_root) / f"{element.name}.toml"
    return [CodexPair(element.type, source, target)]
