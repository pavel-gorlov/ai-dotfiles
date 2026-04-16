"""Vendor subsystem for ai-dotfiles.

Provides the shared plumbing (protocol, .source metadata, placement,
dependency handling) used by individual vendor plugins. Concrete
vendor singletons are registered in :data:`REGISTRY`; the CLI layer
iterates this mapping to build its per-vendor subcommand groups.
"""

from __future__ import annotations

from typing import cast

from ai_dotfiles.vendors.base import Vendor
from ai_dotfiles.vendors.github import GITHUB
from ai_dotfiles.vendors.npx_skills import NPX_SKILLS

# The two singletons satisfy the :class:`Vendor` protocol structurally,
# but mypy's strict protocol variance check rejects a direct assignment
# because the frozen dataclasses expose read-only attributes while the
# Protocol declares them as settable. ``cast`` bridges that gap without
# touching the protocol (which other non-frozen vendors might still rely
# on) or the vendor implementations.
REGISTRY: dict[str, Vendor] = {
    "github": cast(Vendor, GITHUB),
    "npx_skills": cast(Vendor, NPX_SKILLS),
}

__all__ = ["GITHUB", "NPX_SKILLS", "REGISTRY", "Vendor"]
