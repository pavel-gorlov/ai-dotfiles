"""Vendor subsystem for ai-dotfiles.

Provides the shared plumbing (protocol, .source metadata, placement,
dependency handling) used by individual vendor plugins. Plugins
register themselves in :data:`REGISTRY` at import time from
``commands/vendor.py`` to avoid circular imports here.
"""

from __future__ import annotations

from ai_dotfiles.vendors.base import Vendor

REGISTRY: dict[str, Vendor] = {}

__all__ = ["REGISTRY", "Vendor"]
