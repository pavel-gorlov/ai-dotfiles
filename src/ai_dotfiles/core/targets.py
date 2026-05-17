"""Target abstraction for multi-target rendering.

ai-dotfiles is a multi-target package manager: one catalog, one
manifest, rendered into the plumbing of several agent CLIs. A
:class:`Target` identifies one such CLI; the :data:`RENDER_POLICY`
table says, per :class:`~ai_dotfiles.core.elements.ElementType`, *where*
an element goes for that target and *how* it gets there.

This module is pure data — no I/O, no path computation (that lives in
:mod:`ai_dotfiles.core.paths`), no rendering (that lives in the render
layer). It is the contract consumed by the render and command layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ai_dotfiles.core.elements import ElementType

__all__ = [
    "Target",
    "RenderMode",
    "ElementRenderPolicy",
    "RENDER_POLICY",
    "render_policy_for",
]


class Target(Enum):
    """An agent-CLI ai-dotfiles can render a catalog into.

    ``CLAUDE`` is the original and default target (a manifest with no
    ``targets`` field resolves to ``["claude"]``). ``CODEX`` is the
    OpenAI Codex CLI target.
    """

    CLAUDE = "claude"
    CODEX = "codex"


class RenderMode(Enum):
    """How an element is materialised into a target's directory tree.

    ``SYMLINK``  — the catalog source is symlinked into place unchanged.
    ``RENDER``   — a new file is generated from the catalog source
    (format conversion or content trimming); the result is a real
    artefact, not a symlink, and is drift-tracked.
    ``SKIP``     — the target has no surface for this element type; the
    command layer logs the skip rather than failing.
    ``DISPATCH`` — the materialisation strategy is not fixed by the
    ``(Target, ElementType)`` pair alone; the command layer must inspect
    the individual element to decide. Codex rules use this: a rule maps
    onto a root ``AGENTS.md`` block, a nested ``AGENTS.md`` block, or a
    synthetic skill depending on its
    :class:`~ai_dotfiles.core.rule_classify.RuleClass`.
    """

    SYMLINK = "symlink"
    RENDER = "render"
    SKIP = "skip"
    DISPATCH = "dispatch"


@dataclass(frozen=True)
class ElementRenderPolicy:
    """How one :class:`ElementType` is rendered for one :class:`Target`.

    ``mode`` is the materialisation strategy. ``subdir`` is the
    target-tree subdirectory the element lands in (``None`` when
    ``mode`` is :data:`RenderMode.SKIP` — there is no destination).
    """

    mode: RenderMode
    subdir: str | None


# Per-(Target, ElementType) render policy. The destination *directory*
# is resolved by the path layer; ``subdir`` here is the leaf bucket
# name within that target's config root.
RENDER_POLICY: dict[Target, dict[ElementType, ElementRenderPolicy]] = {
    Target.CLAUDE: {
        ElementType.DOMAIN: ElementRenderPolicy(RenderMode.SYMLINK, None),
        ElementType.SKILL: ElementRenderPolicy(RenderMode.SYMLINK, "skills"),
        ElementType.AGENT: ElementRenderPolicy(RenderMode.SYMLINK, "agents"),
        ElementType.RULE: ElementRenderPolicy(RenderMode.SYMLINK, "rules"),
    },
    Target.CODEX: {
        # A domain expands into its member elements; each member is
        # rendered per its own type, so the domain itself has no subdir.
        ElementType.DOMAIN: ElementRenderPolicy(RenderMode.SYMLINK, None),
        # Codex skills: SKILL.md is regenerated (trimmed description),
        # support files symlinked — hence RENDER.
        ElementType.SKILL: ElementRenderPolicy(RenderMode.RENDER, "skills"),
        # Codex agents: catalog .md is converted to .toml — RENDER.
        ElementType.AGENT: ElementRenderPolicy(RenderMode.RENDER, "agents"),
        # Codex rules split three ways by RuleClass (always-on -> root
        # AGENTS.md, path-scoped -> nested AGENTS.md, description-only ->
        # synthetic skill); the command layer classifies each rule and
        # dispatches. No single subdir applies, hence ``None``.
        ElementType.RULE: ElementRenderPolicy(RenderMode.DISPATCH, None),
    },
}


def render_policy_for(target: Target, element_type: ElementType) -> ElementRenderPolicy:
    """Return the :class:`ElementRenderPolicy` for ``element_type`` on ``target``."""
    return RENDER_POLICY[target][element_type]
