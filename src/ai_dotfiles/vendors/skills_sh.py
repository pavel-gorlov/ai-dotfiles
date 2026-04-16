"""skills_sh vendor: install Claude Code skills from the skills.sh marketplace.

Implements the :class:`~ai_dotfiles.vendors.base.Vendor` protocol by
wrapping the upstream ``skills`` CLI (``vercel-labs/skills``), invoked
as ``npx -y skills add ...``. The marketplace backing the CLI is
``https://skills.sh/`` — hence the vendor name. Exposes a module-level
:data:`SKILLS_SH` instance which ``vendors/__init__.py`` registers.

The upstream CLI has no ``--output`` flag. With ``-g`` (global) it
writes to ``$HOME/.claude/skills/``; with ``--agent claude-code`` it
produces only Claude Code output (without, it scatters copies into
``.crush/skills/``, ``.roo/skills/``, etc. — one per known IDE). We
set ``HOME`` to a directory under the caller's ``workdir`` to redirect
the target, and pass both flags so the output lands exactly where we
expect, then enumerate the skills it materialized.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess  # noqa: S404 — vendor intentionally shells out to npx
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from ai_dotfiles.core.errors import ExternalError
from ai_dotfiles.vendors.base import Dependency, FetchedItem

_LICENSE_CANDIDATES: tuple[str, ...] = ("LICENSE", "LICENSE.md", "LICENSE.txt")
_LICENSE_MAX_LEN = 60

_NPX_HOME_DIRNAME = "_npx_home"


def _npx_is_installed() -> bool:
    """Return ``True`` if the ``npx`` executable is on ``PATH``."""
    return shutil.which("npx") is not None


_NPX_DEPENDENCY = Dependency(
    name="npx",
    check=_npx_is_installed,
    install_url="https://nodejs.org/",
)


def _detect_license(directory: Path) -> str | None:
    """Return the first non-blank line of a ``LICENSE*`` file, truncated.

    Mirrors the semantics of the GitHub vendor's license detection so
    downstream metadata looks the same regardless of vendor.
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


def _subprocess_env(home: Path) -> dict[str, str]:
    """Return the env dict passed to the ``npx`` subprocess.

    We pin ``HOME`` to redirect the upstream CLI's output, forward
    ``PATH`` so ``npx`` can be resolved, and (best-effort) forward
    ``NODE_OPTIONS`` if it was already set in our own environment.
    """
    env: dict[str, str] = {
        "HOME": str(home),
        "PATH": os.environ.get("PATH", ""),
    }
    node_options = os.environ.get("NODE_OPTIONS")
    if node_options is not None:
        env["NODE_OPTIONS"] = node_options
    return env


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

# ``npx skills find <query>`` prints one result per block:
#   <owner>/<repo>@<skill-name>   <NNK installs>
#   └ https://skills.sh/<owner>/<repo>/<skill-name>
# Match the first line: owner, repo, name + optional install count.
_FIND_RESULT_RE = re.compile(
    r"^(?P<source>[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*)"
    r"@(?P<name>[A-Za-z0-9][A-Za-z0-9_:.-]*)"
    r"(?:\s+(?P<installs>\S+(?:\s+installs?)?))?\s*$"
)

# Box-drawing frame lines that contain a skill name use exactly 4 spaces
# of indent after the vertical bar; description lines use 6+. The name
# itself is a valid package-style identifier (lowercase letter first,
# then alphanumerics / hyphens / underscores).
_LIST_NAME_RE = re.compile(r"^\u2502 {4}([a-z][A-Za-z0-9_-]*)\s*$")
_LIST_MARKER = "Available Skills"


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes (colour + cursor movement) from text."""
    return _ANSI_ESCAPE_RE.sub("", text)


@dataclass(frozen=True)
class FindResult:
    """One hit from ``npx skills find <query>``."""

    source: str  # "vercel-labs/agent-skills"
    name: str  # "vercel-react-best-practices"
    installs: str  # "321.7K" — human-readable install count, "" if missing
    url: str  # "https://skills.sh/..."


def _parse_find_output(stdout: str) -> list[FindResult]:
    """Parse ``npx skills find <query>`` stdout into :class:`FindResult` s.

    Blocks look like::

        <owner>/<repo>@<name>   321.7K installs
        \u2514 https://skills.sh/<owner>/<repo>/<name>

    ANSI colour codes and box-drawing glyphs are stripped before parsing.
    The ``installs`` field keeps the human-readable count without the
    trailing word (so ``"321.7K"``) — empty string when upstream omits it.
    """
    cleaned = _strip_ansi(stdout)
    results: list[FindResult] = []
    lines = cleaned.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        match = _FIND_RESULT_RE.match(line)
        if match is None:
            i += 1
            continue
        source = match.group("source")
        name = match.group("name")
        installs_raw = match.group("installs") or ""
        # Keep only the numeric prefix (e.g. "321.7K") — drop the trailing
        # " installs" / " install".
        installs = installs_raw.split(maxsplit=1)[0] if installs_raw else ""

        url = ""
        if i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            # Upstream uses U+2514 (``\u2514``) as the arrow; accept a plain
            # ASCII fallback too.
            if next_line.startswith(("\u2514 ", "\u2514\u2500", "- ", "-> ")):
                # Slice off the leading marker + one char (space or dash).
                url = next_line.split(maxsplit=1)[1] if " " in next_line else ""
            elif next_line.startswith("http"):
                url = next_line

        results.append(FindResult(source=source, name=name, installs=installs, url=url))
        i += 2 if url else 1
    return results


def _parse_list_output(stdout: str) -> list[str]:
    """Parse ``npx skills add <source> --list`` stdout into skill names.

    The upstream CLI renders a ``clack``-style frame with box-drawing
    characters and ANSI colour codes. After the ``Available Skills``
    marker, each skill name appears on its own line with exactly four
    spaces after the leading ``\u2502``; the following lines (6+ space
    indent) hold the description. We strip ANSI, find the marker, and
    match name lines via a strict regex so descriptions don't leak in.

    Returns names in the order they appear. An empty result is a
    parsing failure and should be surfaced by the caller.
    """
    cleaned = _strip_ansi(stdout)
    lines = cleaned.splitlines()

    start = 0
    for idx, line in enumerate(lines):
        if _LIST_MARKER in line:
            start = idx + 1
            break
    else:
        # No marker found — probably an error path or non-interactive mode.
        # Fall through to scan the whole output; the regex is strict enough
        # that false positives are unlikely.
        start = 0

    names: list[str] = []
    for line in lines[start:]:
        match = _LIST_NAME_RE.match(line.rstrip())
        if match is not None:
            names.append(match.group(1))
    return names


def _run(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    """Invoke ``argv`` with ``check=False`` and return the completed process.

    Wraps ``FileNotFoundError`` (missing ``npx`` executable) as an
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
            "npx executable not found on PATH; install Node.js from "
            "https://nodejs.org/."
        ) from exc


@dataclass(frozen=True)
class _SkillsShVendor:
    """Concrete skills.sh vendor implementing the :class:`Vendor` protocol."""

    name: str = "skills_sh"
    display_name: str = "skills.sh"
    description: str = "Install Claude Code skills from the skills.sh marketplace."
    deps: tuple[Dependency, ...] = (_NPX_DEPENDENCY,)

    def list_source(self, source: str) -> Iterable[str]:
        """Run ``npx skills add <source> --list`` and return skill names.

        Uses a disposable temporary directory as both ``cwd`` and
        ``HOME`` so the listing probe never touches the real user's
        ``~/.claude/``.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / _NPX_HOME_DIRNAME
            home.mkdir(parents=True, exist_ok=True)

            argv = ["npx", "-y", "skills", "add", source, "--list"]
            result = _run(argv, cwd=tmp_path, env=_subprocess_env(home))

            if result.returncode != 0:
                raise ExternalError(
                    f"npx skills add --list failed: {result.stderr.strip()}"
                )

            names = _parse_list_output(result.stdout)
            if not names:
                raise ExternalError(
                    "npx skills add --list produced no skills " f"(source={source!r})."
                )
            return names

    def fetch(
        self,
        source: str,
        *,
        select: tuple[str, ...] | None,
        workdir: Path,
    ) -> list[FetchedItem]:
        """Run ``npx skills add <source> --copy -y`` into a tmp HOME.

        The upstream CLI writes to ``$HOME/.claude/skills/``, so we set
        ``HOME=workdir/_npx_home`` and enumerate the directories it
        creates there.

        Args:
            source: Source argument passed through to ``npx skills add``.
            select: Optional tuple of skill names. When non-empty, passed
                to the CLI as ``-s name1 name2 ...``.
            workdir: Staging directory owned by the caller.

        Returns:
            One :class:`FetchedItem` per direct child directory found
            under ``workdir/_npx_home/.claude/skills/``.

        Raises:
            ExternalError: On non-zero exit from ``npx`` or when no skill
                directories were materialized.
        """
        workdir.mkdir(parents=True, exist_ok=True)
        home = workdir / _NPX_HOME_DIRNAME
        home.mkdir(parents=True, exist_ok=True)

        # -g: install globally (writes to $HOME/.claude/skills/).
        # --agent claude-code: produce only Claude Code output (without
        #   this the CLI writes a separate copy for every IDE it knows).
        # --copy: real files, not symlinks back into npx cache.
        # -y: skip interactive confirmation.
        argv: list[str] = [
            "npx",
            "-y",
            "skills",
            "add",
            source,
            "-g",
            "--agent",
            "claude-code",
            "--copy",
            "-y",
        ]
        if select:
            argv.append("--skill")
            argv.extend(select)

        result = _run(argv, cwd=workdir, env=_subprocess_env(home))
        if result.returncode != 0:
            raise ExternalError(f"npx skills add failed: {result.stderr.strip()}")

        skills_root = home / ".claude" / "skills"
        if not skills_root.is_dir():
            raise ExternalError(
                "npx skills add produced no skills directory at " f"{skills_root}."
            )

        items: list[FetchedItem] = []
        for entry in sorted(skills_root.iterdir()):
            if not entry.is_dir():
                continue
            items.append(
                FetchedItem(
                    kind="skill",
                    name=entry.name,
                    source_dir=entry,
                    origin=f"skills_sh:{source}",
                    license=_detect_license(entry),
                )
            )

        if not items:
            raise ExternalError(
                "npx skills add completed but produced no skill "
                f"directories under {skills_root}."
            )
        return items

    def find(self, query: str) -> list[FindResult]:
        """Run ``npx skills find <query>`` and return ranked results.

        Upstream's ``find`` is interactive without a query; we always
        require one so the subprocess never hangs on a prompt.
        Uses a disposable tmp dir as both ``cwd`` and ``HOME`` so the
        search probe never touches the real ``~/``.

        Args:
            query: Search term forwarded to the upstream CLI.

        Returns:
            Ordered list of :class:`FindResult`.

        Raises:
            ExternalError: On non-zero exit or empty result.
            ValueError: If ``query`` is blank.
        """
        if not query.strip():
            raise ValueError("query must be non-empty")

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / _NPX_HOME_DIRNAME
            home.mkdir(parents=True, exist_ok=True)

            argv = ["npx", "-y", "skills", "find", query]
            result = _run(argv, cwd=tmp_path, env=_subprocess_env(home))

            if result.returncode != 0:
                raise ExternalError(f"npx skills find failed: {result.stderr.strip()}")

            hits = _parse_find_output(result.stdout)
            if not hits:
                raise ExternalError(
                    f"npx skills find produced no results (query={query!r})."
                )
            return hits


SKILLS_SH: _SkillsShVendor = _SkillsShVendor()
"""Module-level singleton registered as the skills.sh vendor."""

__all__ = ["SKILLS_SH", "FindResult"]
