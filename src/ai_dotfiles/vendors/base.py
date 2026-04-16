"""Core vendor types: :class:`Vendor` protocol and supporting dataclasses.

No vendor implementations live here — this module only declares the
shape of a vendor plugin and the value objects exchanged between the
plugin and the shared plumbing (placement, .source metadata, deps).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable


@dataclass(frozen=True)
class Dependency:
    """A runtime dependency a vendor plugin needs on the host system.

    Attributes:
        name: Human-readable dependency name (e.g. ``"git"``, ``"npx"``).
        check: Zero-arg callable returning ``True`` if the dependency is
            available on the current host.
        install_url: Upstream URL the user can follow to install the
            dependency manually. ai-dotfiles itself never installs
            system-level dependencies.
    """

    name: str
    check: Callable[[], bool]
    install_url: str

    def is_installed(self) -> bool:
        return self.check()


@dataclass(frozen=True)
class FetchedItem:
    """A single item a vendor has fetched into a staging directory.

    Attributes:
        kind: Element kind (``"skill"``, ``"agent"``, or ``"rule"``).
        name: Catalog name for the element (directory/file basename).
        source_dir: Path of the staged content on disk. Will be moved
            into the catalog by :func:`placement.place_item`.
        origin: Origin string that ends up in ``.source`` (e.g.
            ``github:owner/repo/subpath``).
        license: Detected SPDX license id, or ``None`` if unknown.
    """

    kind: Literal["skill", "agent", "rule"]
    name: str
    source_dir: Path
    origin: str
    license: str | None


@dataclass(frozen=True)
class SourceMeta:
    """Parsed contents of a ``.source`` file."""

    vendor: str
    origin: str
    tool: str
    fetched: str  # ISO date YYYY-MM-DD
    license: str  # "unknown" if not detected


@runtime_checkable
class Vendor(Protocol):
    """Plugin interface implemented by concrete vendors (github, skills_sh, ...)."""

    name: str
    display_name: str
    description: str
    deps: tuple[Dependency, ...]

    def list_source(self, source: str) -> Iterable[str]:
        """List the items a given source exposes (without fetching)."""

    def fetch(
        self,
        source: str,
        *,
        select: tuple[str, ...] | None,
        workdir: Path,
    ) -> list[FetchedItem]:
        """Fetch ``source`` (optionally filtering by ``select``) into ``workdir``."""
