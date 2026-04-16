"""buildwithclaude vendor: install skills from davepoon/buildwithclaude.

Implements the :class:`~ai_dotfiles.vendors.base.Vendor` protocol by
git-cloning the public buildwithclaude marketplace repo through the
shared :mod:`_repo_cache` layer and copying one ``SKILL.md``-backed
directory at a time into our catalog. No upstream CLI is invoked.

Observed repo layout (April 2026):
``plugins/<plugin>/skills/<skill>/SKILL.md``. One skill name uniquely
identifies one directory (duplicates across plugins would be flagged).
"""

from __future__ import annotations

import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from ai_dotfiles.core.errors import ElementError, ExternalError
from ai_dotfiles.vendors import _repo_cache
from ai_dotfiles.vendors.base import Dependency, FetchedItem

# Keep `shutil` addressable at module scope so tests can monkeypatch
# ``ai_dotfiles.vendors.buildwithclaude.shutil.which``.

_REPO_URL = "https://github.com/davepoon/buildwithclaude.git"
_BRANCH = "main"

_LICENSE_CANDIDATES: tuple[str, ...] = ("LICENSE", "LICENSE.md", "LICENSE.txt")
_LICENSE_MAX_LEN = 60


def _git_is_installed() -> bool:
    return shutil.which("git") is not None


_GIT_DEPENDENCY = Dependency(
    name="git",
    check=_git_is_installed,
    install_url="https://git-scm.com/",
)


def _detect_license(directory: Path) -> str | None:
    """Return the first non-blank line of a ``LICENSE*`` file, truncated."""
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


@dataclass(frozen=True)
class SearchResult:
    """One hit from :meth:`_BuildWithClaudeVendor.search`.

    Mirrors the shape used by the other vendors so the CLI formatter
    renders them uniformly. ``source`` is always ``"buildwithclaude"``
    (the marketplace name); ``name`` is the skill name.
    """

    source: str
    name: str
    description: str
    url: str
    installs: str = ""


def _locate_skill(cache_root: Path, name: str) -> list[Path]:
    """Find every skill directory whose name matches ``name`` exactly."""
    return [d for d in _repo_cache.find_skill_dirs(cache_root) if d.name == name]


def _repo_relpath(cache_root: Path, entry: Path) -> str:
    try:
        return str(entry.relative_to(cache_root))
    except ValueError:
        return entry.name


def _make_url(relpath: str) -> str:
    return f"https://github.com/davepoon/buildwithclaude/tree/{_BRANCH}/{relpath}"


def _matches(query: str, meta: dict[str, str], name: str) -> bool:
    """Case-insensitive substring match against name/description/tags."""
    needle = query.lower()
    haystack = " ".join(
        [
            name,
            meta.get("name", ""),
            meta.get("description", ""),
            meta.get("tags", ""),
        ]
    ).lower()
    return needle in haystack


@dataclass(frozen=True)
class _BuildWithClaudeVendor:
    """Concrete buildwithclaude vendor implementing the Vendor protocol."""

    name: str = "buildwithclaude"
    display_name: str = "buildwithclaude"
    description: str = "Install skills from the buildwithclaude marketplace."
    deps: tuple[Dependency, ...] = (_GIT_DEPENDENCY,)

    def list_source(self, source: str) -> Iterable[str]:
        """Single-skill semantics: return ``[source]`` without network."""
        return [source]

    def refresh(self, *, force: bool = False) -> Path:
        """Re-fetch the marketplace cache; delegates to :mod:`_repo_cache`."""
        return _repo_cache.refresh(
            vendor_name=self.name,
            repo_url=_REPO_URL,
            branch=_BRANCH,
            force=force,
        )

    def search(self, query: str) -> list[SearchResult]:
        """Substring search over the cached catalog.

        Matches against skill directory name, frontmatter ``name``,
        ``description`` and ``tags``. Returns results in traversal
        order (stable for a given cache state).
        """
        if not query.strip():
            raise ValueError("query must be non-empty")

        cache_root = self.refresh(force=False)

        results: list[SearchResult] = []
        for skill_dir in _repo_cache.find_skill_dirs(cache_root):
            meta = _repo_cache.read_frontmatter(skill_dir / "SKILL.md")
            if not _matches(query, meta, skill_dir.name):
                continue
            relpath = _repo_relpath(cache_root, skill_dir)
            results.append(
                SearchResult(
                    source=self.name,
                    name=skill_dir.name,
                    description=meta.get("description", ""),
                    url=_make_url(relpath),
                )
            )
        if not results:
            raise ExternalError(f"buildwithclaude: no results for query={query!r}.")
        return results

    def fetch(
        self,
        source: str,
        *,
        select: tuple[str, ...] | None,
        workdir: Path,
    ) -> list[FetchedItem]:
        """Copy one matching skill directory into ``workdir/out/<name>/``.

        ``source`` is the leaf directory name; ``select`` must be
        empty (single-skill semantics). Raises :class:`ElementError`
        when the skill cannot be located or the catalog has a
        duplicate, :class:`ExternalError` on cache failures.
        """
        if select:
            raise ElementError(
                "buildwithclaude vendor does not support --select; "
                "install one source at a time."
            )

        cache_root = self.refresh(force=False)
        matches = _locate_skill(cache_root, source)
        if not matches:
            raise ExternalError(f"buildwithclaude: no skill named {source!r} in cache.")
        if len(matches) > 1:
            rels = ", ".join(_repo_relpath(cache_root, m) for m in matches)
            raise ElementError(
                f"buildwithclaude: skill name {source!r} is ambiguous "
                f"across plugins ({rels})."
            )

        match = matches[0]
        workdir.mkdir(parents=True, exist_ok=True)
        out = workdir / "out"
        out.mkdir(exist_ok=True)
        dest = out / source
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(match, dest)

        return [
            FetchedItem(
                kind="skill",
                name=source,
                source_dir=dest,
                origin=f"buildwithclaude:{source}",
                license=_detect_license(match),
            )
        ]


BUILDWITHCLAUDE: _BuildWithClaudeVendor = _BuildWithClaudeVendor()
"""Module-level singleton registered as the buildwithclaude vendor."""

__all__ = ["BUILDWITHCLAUDE", "SearchResult"]
