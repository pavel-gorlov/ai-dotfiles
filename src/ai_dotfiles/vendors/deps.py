"""Dependency checking and (opt-in) installation for vendor plugins.

A vendor declares its host-system dependencies as a tuple of
:class:`~ai_dotfiles.vendors.base.Dependency` values. Before running
``fetch`` the CLI calls :func:`ensure` to fail fast with a clear
message if anything is missing, and :func:`install` can optionally
run the platform-specific install command after confirming with the
user. We never invoke ``sudo`` on behalf of the user.
"""

from __future__ import annotations

import shutil
import subprocess  # noqa: S404 — we intentionally shell out to installers
import sys

import click

from ai_dotfiles.core.errors import ExternalError
from ai_dotfiles.vendors.base import Dependency, Vendor


def check(vendor: Vendor) -> list[Dependency]:
    """Return the subset of ``vendor.deps`` that are not installed."""
    return [dep for dep in vendor.deps if not dep.is_installed()]


def ensure(vendor: Vendor) -> None:
    """Raise :class:`ExternalError` if any dependency is missing.

    The error message lists each missing dependency with its manual
    install hint and points the user at
    ``ai-dotfiles vendor <vendor.name> deps install``.
    """
    missing = check(vendor)
    if not missing:
        return

    lines = [
        f"Vendor '{vendor.name}' is missing required dependencies:",
        "",
    ]
    for dep in missing:
        lines.append(f"  - {dep.name}: {dep.manual_hint}")
    lines.append("")
    lines.append(f"Install them with: ai-dotfiles vendor {vendor.name} deps install")

    raise ExternalError("\n".join(lines))


def _platform_key() -> str:
    """Return the ``sys.platform`` key used to look up install commands."""
    plat = sys.platform
    if plat.startswith("linux"):
        return "linux"
    if plat.startswith("darwin"):
        return "darwin"
    if plat.startswith("win"):
        return "win32"
    return plat


def install(vendor: Vendor, *, yes: bool = False) -> None:
    """Install any missing dependencies for ``vendor``.

    For each missing dependency:

    1. Pick the install command for the current platform.
    2. If there is none, raise :class:`ExternalError` with the manual hint.
    3. Unless ``yes`` is set, prompt the user to confirm the command
       (aborts on "no" without raising).
    4. Run the command via ``subprocess.run(..., check=True)``.

    Special case: on macOS, if the install command starts with ``brew``
    but Homebrew itself is not on ``PATH``, raise a clear error.

    Args:
        vendor: The vendor whose dependencies to install.
        yes: If ``True``, skip confirmation prompts.

    Raises:
        ExternalError: When no install command is available for the
            current platform, when Homebrew is required but missing, or
            when ``subprocess.run`` returns a non-zero exit code.
    """
    missing = check(vendor)
    if not missing:
        return

    platform = _platform_key()

    for dep in missing:
        cmd = dep.install_cmd.get(platform)
        if cmd is None:
            raise ExternalError(
                f"No automatic install for '{dep.name}' on {platform}. "
                f"{dep.manual_hint}"
            )

        if (
            platform == "darwin"
            and cmd
            and cmd[0] == "brew"
            and shutil.which("brew") is None
        ):
            raise ExternalError(
                "Homebrew is required to install "
                f"'{dep.name}' but 'brew' was not found on PATH. "
                "Install Homebrew from https://brew.sh/ first."
            )

        pretty = " ".join(cmd)
        if not yes and not click.confirm(f"Run: {pretty}?", default=False):
            return

        try:
            subprocess.run(
                cmd, check=True
            )  # noqa: S603 — cmd comes from trusted vendor metadata
        except FileNotFoundError as exc:
            raise ExternalError(
                f"Installer executable not found for '{dep.name}': {cmd[0]}. "
                f"{dep.manual_hint}"
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise ExternalError(
                f"Failed to install '{dep.name}' (exit {exc.returncode}): {pretty}"
            ) from exc
