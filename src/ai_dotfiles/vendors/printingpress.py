"""printingpress vendor: install skills from mvanhorn/printing-press-library.

Mirrors :mod:`mattpocock` shape. Backs onto the printingpress.dev
catalog (Matt Van Horn's `mvanhorn/printing-press-library`, Apache-2.0)
via the shared :mod:`_repo_cache`. No upstream CLI is invoked at
install time.

Observed repo layout (May 2026): two parallel trees.

- ``library/<category>/<entry>/`` — full source (Go + SKILL.md);
  heavy (~236 MB).
- ``cli-skills/pp-<name>/SKILL.md`` — self-contained skill folders,
  one SKILL.md per directory, names already prefixed ``pp-`` (no
  collisions across the catalog).

We walk the focused ``cli-skills/`` tree so the cache stays small.
Each skill instructs Claude (in its SKILL.md body) to bootstrap its
matching prebuilt CLI binary via ``npx -y @mvanhorn/printing-press
install <name> --cli-only`` on first use — so the vendor itself
needs only ``git``; Node/Go are runtime concerns of the skill body.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from ai_dotfiles.core.errors import ElementError, ExternalError
from ai_dotfiles.vendors import _repo_cache
from ai_dotfiles.vendors.base import Dependency, FetchedItem

_REPO_URL = "https://github.com/mvanhorn/printing-press-library.git"
_BRANCH = "main"
_WALK_SUBDIR = "cli-skills"

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
    """One hit from :meth:`_PrintingPressVendor.search`."""

    source: str
    name: str
    description: str
    url: str
    installs: str = ""


def _locate_skill(cache_root: Path, name: str) -> list[Path]:
    return [
        d
        for d in _repo_cache.find_skill_dirs(cache_root / _WALK_SUBDIR)
        if d.name == name
    ]


def _repo_relpath(cache_root: Path, entry: Path) -> str:
    try:
        return str(entry.relative_to(cache_root))
    except ValueError:
        return entry.name


def _make_url(relpath: str) -> str:
    return (
        "https://github.com/mvanhorn/printing-press-library/"
        f"tree/{_BRANCH}/{relpath}"
    )


def _matches(query: str, meta: dict[str, str], name: str) -> bool:
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
class _PrintingPressVendor:
    """Concrete printingpress vendor implementing the Vendor protocol."""

    name: str = "printingpress"
    display_name: str = "printingpress"
    description: str = (
        "Install skills from mvanhorn/printing-press-library — each skill "
        "bootstraps its own prebuilt CLI binary via npx on first use."
    )
    deps: tuple[Dependency, ...] = (_GIT_DEPENDENCY,)

    def list_source(self, source: str) -> Iterable[str]:
        return [source]

    def refresh(self, *, force: bool = False) -> Path:
        return _repo_cache.refresh(
            vendor_name=self.name,
            repo_url=_REPO_URL,
            branch=_BRANCH,
            force=force,
        )

    def search(self, query: str) -> list[SearchResult]:
        if not query.strip():
            raise ValueError("query must be non-empty")

        cache_root = self.refresh(force=False)

        results: list[SearchResult] = []
        for skill_dir in _repo_cache.find_skill_dirs(cache_root / _WALK_SUBDIR):
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
            raise ExternalError(f"printingpress: no results for query={query!r}.")
        return results

    def fetch(
        self,
        source: str,
        *,
        select: tuple[str, ...] | None,
        workdir: Path,
    ) -> list[FetchedItem]:
        if select:
            raise ElementError(
                "printingpress vendor does not support --select; "
                "install one source at a time."
            )

        cache_root = self.refresh(force=False)
        matches = _locate_skill(cache_root, source)
        if not matches:
            raise ExternalError(f"printingpress: no skill named {source!r} in cache.")
        if len(matches) > 1:
            rels = ", ".join(_repo_relpath(cache_root, m) for m in matches)
            raise ElementError(
                f"printingpress: skill name {source!r} is ambiguous ({rels})."
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
                origin=f"printingpress:{source}",
                license=_detect_license(match),
            )
        ]


PRINTINGPRESS: _PrintingPressVendor = _PrintingPressVendor()
"""Module-level singleton registered as the printingpress vendor."""

__all__ = ["PRINTINGPRESS", "SearchResult"]
