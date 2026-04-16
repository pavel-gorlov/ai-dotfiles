"""paks vendor: install Claude Code skills from the paks registry.

Implements the :class:`~ai_dotfiles.vendors.base.Vendor` protocol by
wrapping the upstream ``paks`` CLI (``stakpak/paks``), a native Rust
binary installed out-of-band (e.g. ``brew tap stakpak/stakpak &&
brew install paks``). Each source argument maps to a single skill;
the ``--select`` fan-out pattern used by ``skills_sh`` does not apply
here — install one source at a time.

The upstream CLI supports an explicit ``--dir`` flag, so we direct
its output to a caller-owned staging directory under ``workdir/out``
rather than redirecting ``HOME`` like we do for ``skills_sh``. Only
``PATH`` is forwarded to the subprocess.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess  # noqa: S404 — vendor intentionally shells out to paks
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from ai_dotfiles.core.errors import ElementError, ExternalError
from ai_dotfiles.vendors.base import Dependency, FetchedItem

_LICENSE_CANDIDATES: tuple[str, ...] = ("LICENSE", "LICENSE.md", "LICENSE.txt")
_LICENSE_MAX_LEN = 60

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

# ``paks search <query>`` output format (v0.1.18):
#   <2 spaces><owner>/<skill> <U+2193>N  [#tag ...]
#   <4 spaces><description>
#
# Match the name line: `<owner>/<skill>` where both parts are identifier-like
# (alphanumerics, hyphens, dots, underscores). Match is anchored to start
# with exactly two spaces to exclude the trailing "Install: ..." footer,
# which starts with two spaces then a capitalised word.
_SEARCH_NAME_RE = re.compile(
    r"^  (?P<owner>[A-Za-z0-9][A-Za-z0-9_.-]*)"
    r"/(?P<skill>[A-Za-z0-9][A-Za-z0-9_.-]*)\b"
    r"(?:\s+(?:\u2193|\u2191|\u21D3|\u21D1|\^|v)?(?P<installs>\d[\d.]*[KMkm]?))?"
)
# paks uses `<owner>--<skill>` as the directory name after install.
_OWNER_DIR_SEP = "--"


def _paks_is_installed() -> bool:
    """Return ``True`` if the ``paks`` executable is on ``PATH``."""
    return shutil.which("paks") is not None


_PAKS_DEPENDENCY = Dependency(
    name="paks",
    check=_paks_is_installed,
    install_url="https://paks.stakpak.dev",
)


def _detect_license(directory: Path) -> str | None:
    """Return the first non-blank line of a ``LICENSE*`` file, truncated.

    Mirrors the semantics of the ``skills_sh`` vendor's license
    detection so downstream metadata looks the same regardless of
    vendor.
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


def _subprocess_env() -> dict[str, str]:
    """Return the env dict passed to the ``paks`` subprocess.

    The ``paks`` CLI does not need a redirected ``HOME`` — it writes
    wherever ``--dir`` points. We forward only ``PATH`` so the
    subprocess has no accidental access to the rest of the user's
    environment.
    """
    return {"PATH": os.environ.get("PATH", "")}


@dataclass(frozen=True)
class SearchResult:
    """One hit from ``paks search <query>``.

    The CLI formatter renders ``{source}@{name}`` then an optional URL
    line, matching the ``skills_sh`` output shape. For paks:

    * ``source`` = upstream owner (e.g. ``wshpbson``)
    * ``name``   = skill name (e.g. ``k8s-manifest-generator``)

    To actually install the result, join them with ``/``:
    ``paks install <source>/<name>``.
    """

    source: str
    name: str
    description: str
    url: str
    installs: str = ""


def _run(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    """Invoke ``argv`` with ``check=False`` and return the completed process.

    Wraps ``FileNotFoundError`` (missing ``paks`` executable) as an
    :class:`ExternalError` so callers only have to catch one exception
    type. Non-zero exits are NOT raised here — the caller inspects
    ``returncode`` and builds a specific message.
    """
    try:
        return subprocess.run(  # noqa: S603 — argv built from trusted inputs
            argv,
            cwd=str(cwd),
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise ExternalError(
            "paks executable not found on PATH; install from "
            "https://paks.stakpak.dev."
        ) from exc


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes (colour + cursor movement) from text."""
    return _ANSI_ESCAPE_RE.sub("", text)


def _parse_search_text(stdout: str) -> list[SearchResult]:
    """Parse ``paks search <query>`` stdout into :class:`SearchResult` s.

    Upstream (paks 0.1.18) has no JSON output mode, so we parse the
    human-readable text. Each hit is two lines::

        <2 sp><owner>/<skill>  <U+2193>N  [#tag ...]
        <4 sp><description...>

    Followed by a single ``Install: paks install <owner>/<skill>``
    footer line, which the name regex rejects (no ``/`` inside the
    identifier char class after the ``Install:`` prefix).

    ANSI colour codes and any trailing ``#tag`` hashes are stripped
    before matching; the description is captured best-effort from the
    immediately-following indented line.
    """
    cleaned = _strip_ansi(stdout)
    lines = cleaned.splitlines()
    results: list[SearchResult] = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        match = _SEARCH_NAME_RE.match(line)
        if match is None:
            i += 1
            continue
        owner = match.group("owner")
        skill = match.group("skill")
        installs = match.group("installs") or ""

        description = ""
        if i + 1 < len(lines):
            next_line = lines[i + 1]
            # Description line uses 4+ spaces of indent; name lines use
            # exactly 2, so 4-space leading prefix rules them out.
            if next_line.startswith("    "):
                description = next_line.strip()

        results.append(
            SearchResult(
                source=owner,
                name=skill,
                description=description,
                url=f"https://paks.stakpak.dev/{owner}/{skill}",
                installs=installs,
            )
        )
        i += 2 if description else 1
    return results


@dataclass(frozen=True)
class _PaksVendor:
    """Concrete paks vendor implementing the :class:`Vendor` protocol."""

    name: str = "paks"
    display_name: str = "paks"
    description: str = "Install Claude Code skills from the paks registry."
    deps: tuple[Dependency, ...] = (_PAKS_DEPENDENCY,)

    def list_source(self, source: str) -> Iterable[str]:
        """Return a single-entry iterable — one source equals one skill.

        The paks CLI models each registry entry as a standalone skill;
        there's nothing to expand server-side. We echo ``source`` back
        so the CLI's ``vendor paks list <source>`` still produces
        output without a subprocess call.
        """
        return [source]

    def fetch(
        self,
        source: str,
        *,
        select: tuple[str, ...] | None,
        workdir: Path,
    ) -> list[FetchedItem]:
        """Run ``paks install <source> --dir <workdir/out>``.

        paks 0.1.x writes each skill into a single directory named
        ``<owner>--<skill>/`` under the ``--dir`` target (``--dir``
        overrides the ``--agent``/``--scope`` output layout). We
        enumerate the first level and strip the ``<owner>--`` prefix
        from the catalog entry name so the user can refer to it as
        ``skill:<skill>`` without the registry owner clutter.

        Args:
            source: Registry name (``<owner>/<skill>``), git URL, or
                local path accepted by ``paks install``.
            select: Must be ``None`` or empty — paks has single-skill
                semantics and has no selector flag.
            workdir: Staging directory owned by the caller.

        Returns:
            One :class:`FetchedItem` per direct child directory under
            ``<workdir>/out/``.

        Raises:
            ElementError: When ``select`` is non-empty.
            ExternalError: On non-zero exit from ``paks`` or when no
                skill directories were materialized.
        """
        if select:
            raise ElementError(
                "paks vendor does not support --select; install one source "
                "at a time."
            )

        workdir.mkdir(parents=True, exist_ok=True)
        out = workdir / "out"
        out.mkdir(parents=True, exist_ok=True)

        argv: list[str] = [
            "paks",
            "install",
            source,
            "--dir",
            str(out),
            "--force",
        ]

        result = _run(argv, cwd=workdir, env=_subprocess_env())
        if result.returncode != 0:
            raise ExternalError(f"paks install failed: {result.stderr.strip()}")

        candidate_dirs = sorted(
            entry
            for entry in out.iterdir()
            if entry.is_dir() and entry.name != ".claude"
        )

        items: list[FetchedItem] = []
        for entry in candidate_dirs:
            raw = entry.name
            # Strip the "<owner>--" prefix paks produces so the catalog
            # entry matches the user's mental model.
            pretty = raw.split(_OWNER_DIR_SEP, 1)[-1] if _OWNER_DIR_SEP in raw else raw
            items.append(
                FetchedItem(
                    kind="skill",
                    name=pretty,
                    source_dir=entry,
                    origin=f"paks:{source}",
                    license=_detect_license(entry),
                )
            )

        if not items:
            raise ExternalError(f"paks install produced no skills at {out}.")
        return items

    def search(self, query: str) -> list[SearchResult]:
        """Run ``paks search <query>`` and parse the text output.

        Args:
            query: Search term forwarded to the upstream CLI.

        Returns:
            Ordered list of :class:`SearchResult`.

        Raises:
            ExternalError: On non-zero exit or empty result.
            ValueError: If ``query`` is blank.
        """
        if not query.strip():
            raise ValueError("query must be non-empty")

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            argv = ["paks", "search", query]
            result = _run(argv, cwd=tmp_path, env=_subprocess_env())

            if result.returncode != 0:
                raise ExternalError(f"paks search failed: {result.stderr.strip()}")

            hits = _parse_search_text(result.stdout)
            if not hits:
                raise ExternalError(
                    f"paks search produced no results (query={query!r})."
                )
            return hits


PAKS: _PaksVendor = _PaksVendor()
"""Module-level singleton registered as the paks vendor."""

__all__ = ["PAKS", "SearchResult"]
