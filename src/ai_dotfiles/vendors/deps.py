"""Dependency checking for vendor plugins.

A vendor declares its host-system dependencies as a tuple of
:class:`~ai_dotfiles.vendors.base.Dependency` values. Before running
``fetch`` the CLI calls :func:`ensure` to fail fast with a clear
message — pointing at the upstream install URL — when anything is
missing. ai-dotfiles never installs system-level dependencies on the
user's behalf.
"""

from __future__ import annotations

from ai_dotfiles.core.errors import ExternalError
from ai_dotfiles.vendors.base import Dependency, Vendor


def check(vendor: Vendor) -> list[Dependency]:
    """Return the subset of ``vendor.deps`` that are not installed."""
    return [dep for dep in vendor.deps if not dep.is_installed()]


def ensure(vendor: Vendor) -> None:
    """Raise :class:`ExternalError` if any dependency is missing.

    The error message lists each missing dependency with its upstream
    install URL, using the format
    ``"missing dependency '<name>'; install: <url>"`` — one such line
    per missing dependency, joined by newlines.
    """
    missing = check(vendor)
    if not missing:
        return

    lines = [
        f"Vendor '{vendor.name}' is missing required dependencies:",
        "",
    ]
    for dep in missing:
        lines.append(f"missing dependency '{dep.name}'; install: {dep.install_url}")

    raise ExternalError("\n".join(lines))
