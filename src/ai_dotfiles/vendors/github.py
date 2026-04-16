"""GitHub vendor: sparse-clone a subtree from GitHub.

Implements the :class:`~ai_dotfiles.vendors.base.Vendor` protocol for
GitHub URLs. Exposes a module-level :data:`GITHUB` instance that the
registry picks up in ``vendors/__init__.py``.

The heavy lifting (URL parsing, subprocess wrapping, element kind
detection) lives in :mod:`ai_dotfiles.core.git_ops` and is reused here
verbatim — this module only adapts those helpers to the vendor
protocol surface.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from ai_dotfiles.core import git_ops
from ai_dotfiles.core.errors import ElementError, ExternalError
from ai_dotfiles.vendors.base import Dependency, FetchedItem

_LICENSE_CANDIDATES: tuple[str, ...] = ("LICENSE", "LICENSE.md", "LICENSE.txt")
_LICENSE_MAX_LEN = 60

_VALID_KINDS: frozenset[str] = frozenset({"skill", "agent", "rule"})


def _git_is_installed() -> bool:
    """Return ``True`` if the ``git`` executable is on ``PATH``."""
    return shutil.which("git") is not None


_GIT_DEPENDENCY = Dependency(
    name="git",
    check=_git_is_installed,
    install_cmd={
        "darwin": ["brew", "install", "git"],
        "linux": ["apt-get", "install", "-y", "git"],
    },
    manual_hint=(
        "Install git from https://git-scm.com/downloads or your package manager."
    ),
)


def _detect_license(directory: Path) -> str | None:
    """Return the first non-blank line of a ``LICENSE*`` file, truncated.

    Searches ``directory`` for one of :data:`_LICENSE_CANDIDATES` (in
    order). Returns the first non-blank line of the first match,
    stripped and truncated to :data:`_LICENSE_MAX_LEN` characters.
    Returns ``None`` if no license file is found or if every candidate
    is empty / unreadable.
    """
    for candidate in _LICENSE_CANDIDATES:
        path = directory / candidate
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line:
                return line[:_LICENSE_MAX_LEN]
    return None


def _owner_repo_from_url(repo_url: str) -> tuple[str, str]:
    """Extract ``(owner, repo)`` from the normalized repo URL.

    ``parse_github_url`` returns either:

    * ``https://github.com/<owner>/<repo>.git``
    * ``git@github.com:<owner>/<repo>.git``
    """
    if repo_url.startswith("git@"):
        _, _, tail = repo_url.partition(":")
    else:
        tail = repo_url.rsplit("github.com/", 1)[-1]
    owner, _, repo = tail.partition("/")
    if repo.endswith(".git"):
        repo = repo[: -len(".git")]
    return owner, repo


def _resolve_kind(staging: Path) -> Literal["skill", "agent", "rule"]:
    """Return element kind for ``staging``, defaulting to ``"skill"``."""
    kind = git_ops.detect_element_type(staging)
    if kind in _VALID_KINDS:
        return cast(Literal["skill", "agent", "rule"], kind)
    return "skill"


def _origin(owner: str, repo: str, subpath: str) -> str:
    suffix = f"/{subpath}" if subpath else ""
    return f"github:{owner}/{repo}{suffix}"


@dataclass(frozen=True)
class _GitHubVendor:
    """Concrete GitHub vendor implementing the :class:`Vendor` protocol."""

    name: str = "github"
    display_name: str = "GitHub"
    description: str = "Sparse-clone a subtree from GitHub."
    deps: tuple[Dependency, ...] = (_GIT_DEPENDENCY,)

    def list_source(self, source: str) -> Iterable[str]:
        """List top-level entries under the URL's subpath.

        Performs a sparse checkout into a temporary directory and
        returns the names of the first-level entries found there. For a
        root-URL (no subpath) this lists the repo's top-level entries.
        """
        parsed = git_ops.parse_github_url(source)
        if parsed is None:
            raise ElementError(
                "Unrecognized GitHub URL. Supported formats:\n"
                "  https://github.com/<owner>/<repo>\n"
                "  https://github.com/<owner>/<repo>/tree/<branch>/<subpath>\n"
                "  git@github.com:<owner>/<repo>.git"
            )

        repo_url, branch, subpath, _ = parsed

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "listing"
            if subpath:
                git_ops.git_sparse_checkout(repo_url, subpath, dest, branch=branch)
            else:
                git_ops.git_clone(repo_url, dest, branch=branch)
            if not dest.is_dir():
                raise ExternalError(f"Expected directory after fetch: {dest}")
            return sorted(entry.name for entry in dest.iterdir())

    def fetch(
        self,
        source: str,
        *,
        select: tuple[str, ...] | None,
        workdir: Path,
    ) -> list[FetchedItem]:
        """Sparse-clone ``source`` into ``workdir`` and return one item.

        The GitHub vendor intentionally does not support partial
        selection: the URL itself must already point at the content to
        fetch. Passing a non-empty ``select`` raises
        :class:`~ai_dotfiles.core.errors.ElementError`.
        """
        if select:
            raise ElementError(
                "GitHub vendor does not support --select; " "use a more specific URL"
            )

        parsed = git_ops.parse_github_url(source)
        if parsed is None:
            raise ElementError(
                "Unrecognized GitHub URL. Supported formats:\n"
                "  https://github.com/<owner>/<repo>\n"
                "  https://github.com/<owner>/<repo>/tree/<branch>/<subpath>\n"
                "  git@github.com:<owner>/<repo>.git"
            )

        repo_url, branch, subpath, name = parsed
        owner, repo = _owner_repo_from_url(repo_url)

        workdir.mkdir(parents=True, exist_ok=True)
        staging = workdir / name
        if staging.exists():
            shutil.rmtree(staging)

        git_ops.git_sparse_checkout(repo_url, subpath, staging, branch=branch)

        kind = _resolve_kind(staging)
        license_id = _detect_license(staging)

        return [
            FetchedItem(
                kind=kind,
                name=name,
                source_dir=staging,
                origin=_origin(owner, repo, subpath),
                license=license_id,
            )
        ]


GITHUB: _GitHubVendor = _GitHubVendor()
"""Module-level singleton registered as the GitHub vendor."""

__all__ = ["GITHUB"]
