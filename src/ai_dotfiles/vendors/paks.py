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

import json
import os
import shutil
import subprocess  # noqa: S404 — vendor intentionally shells out to paks
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from ai_dotfiles.core.errors import ElementError, ExternalError
from ai_dotfiles.vendors.base import Dependency, FetchedItem

_LICENSE_CANDIDATES: tuple[str, ...] = ("LICENSE", "LICENSE.md", "LICENSE.txt")
_LICENSE_MAX_LEN = 60


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
    """One hit from ``paks search <query> --format json``.

    Field names intentionally mirror the ``skills_sh`` ``SearchResult``
    so the CLI layer's duck-typed formatter can render both. Missing
    upstream fields default to an empty string; the CLI suppresses
    blanks when printing.
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


def _extract_str(obj: dict[str, object], *keys: str) -> str:
    """Return the first string-valued entry in ``obj`` among ``keys``.

    Upstream response shapes can vary across versions (e.g.
    ``"description"`` vs ``"summary"``); we accept any of a handful
    of synonyms and coerce non-string values to empty. Missing keys
    return ``""``.
    """
    for key in keys:
        value = obj.get(key)
        if isinstance(value, str):
            return value
    return ""


def _parse_search_json(stdout: str) -> list[SearchResult]:
    """Parse ``paks search --format json`` stdout into :class:`SearchResult`.

    The upstream command prints a JSON array of objects. Field names
    we care about: ``source`` / ``name`` / ``description`` / ``url``
    (plus ``installs`` if present). Missing fields default to ``""``.

    Raises:
        ExternalError: If ``stdout`` isn't valid JSON or the top-level
            value isn't an array.
    """
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ExternalError(f"paks search returned unparseable JSON: {exc}") from exc

    if not isinstance(payload, list):
        raise ExternalError(
            "paks search JSON payload was not an array "
            f"(got {type(payload).__name__})."
        )

    results: list[SearchResult] = []
    for entry in payload:
        if not isinstance(entry, dict):
            # Skip non-object entries defensively — a string-only array
            # would otherwise explode the parser.
            continue
        results.append(
            SearchResult(
                source=_extract_str(entry, "source", "id", "slug"),
                name=_extract_str(entry, "name", "title"),
                description=_extract_str(entry, "description", "summary"),
                url=_extract_str(entry, "url", "href", "link"),
                installs=_extract_str(entry, "installs", "install_count"),
            )
        )
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
        """Run ``paks install <source> --dir workdir/out --yes``.

        The upstream CLI writes to ``<dir>/.claude/skills/<name>/``
        when ``--agent claude-code --scope global`` is passed, so we
        enumerate that directory to collect :class:`FetchedItem` s.
        Some versions (or future flag combinations) may flatten the
        layout to ``<dir>/<name>/``; we fall back to that if the
        nested path is empty.

        Args:
            source: Source argument passed through to ``paks install``.
            select: Must be ``None`` or empty — paks has single-skill
                semantics and has no selector flag.
            workdir: Staging directory owned by the caller.

        Returns:
            One :class:`FetchedItem` per direct child directory found
            under ``workdir/out/.claude/skills/`` (or ``workdir/out/``
            as a fallback).

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
            "--agent",
            "claude-code",
            "--scope",
            "global",
            "--dir",
            str(out),
            "--yes",
        ]

        result = _run(argv, cwd=workdir, env=_subprocess_env())
        if result.returncode != 0:
            raise ExternalError(f"paks install failed: {result.stderr.strip()}")

        nested = out / ".claude" / "skills"
        candidate_dirs: list[Path]
        if nested.is_dir():
            candidate_dirs = sorted(
                entry for entry in nested.iterdir() if entry.is_dir()
            )
        else:
            candidate_dirs = []

        # Fallback: some paks builds / flag combos may flatten the
        # output to `<out>/<skill>/` with no `.claude/skills` prefix.
        if not candidate_dirs:
            candidate_dirs = sorted(
                entry
                for entry in out.iterdir()
                if entry.is_dir() and entry.name != ".claude"
            )

        items: list[FetchedItem] = []
        for entry in candidate_dirs:
            items.append(
                FetchedItem(
                    kind="skill",
                    name=entry.name,
                    source_dir=entry,
                    origin=f"paks:{source}",
                    license=_detect_license(entry),
                )
            )

        if not items:
            raise ExternalError(f"paks install produced no skills at {out}.")
        return items

    def search(self, query: str) -> list[SearchResult]:
        """Run ``paks search <query> --format json`` and return results.

        Args:
            query: Search term forwarded to the upstream CLI.

        Returns:
            Ordered list of :class:`SearchResult`.

        Raises:
            ExternalError: On non-zero exit, empty result, or a stdout
                payload that isn't a JSON array.
            ValueError: If ``query`` is blank.
        """
        if not query.strip():
            raise ValueError("query must be non-empty")

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            argv = ["paks", "search", query, "--format", "json"]
            result = _run(argv, cwd=tmp_path, env=_subprocess_env())

            if result.returncode != 0:
                raise ExternalError(f"paks search failed: {result.stderr.strip()}")

            hits = _parse_search_json(result.stdout)
            if not hits:
                raise ExternalError(
                    f"paks search produced no results (query={query!r})."
                )
            return hits


PAKS: _PaksVendor = _PaksVendor()
"""Module-level singleton registered as the paks vendor."""

__all__ = ["PAKS", "SearchResult"]
