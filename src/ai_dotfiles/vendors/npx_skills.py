"""npx_skills vendor: install Claude Code skills via the ``skills`` npm CLI.

Implements the :class:`~ai_dotfiles.vendors.base.Vendor` protocol by
wrapping the upstream ``skills`` CLI (vercel-labs/skills), invoked with
``npx -y skills add ...``. Exposes a module-level :data:`NPX_SKILLS`
instance which V4 registers in ``vendors/__init__.py``.

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
    install_cmd={
        "darwin": ["brew", "install", "node"],
        "linux": ["apt-get", "install", "-y", "nodejs", "npm"],
    },
    manual_hint=(
        "Install Node.js (which ships with npx) from https://nodejs.org/ "
        "or your package manager."
    ),
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

# Box-drawing frame lines that contain a skill name use exactly 4 spaces
# of indent after the vertical bar; description lines use 6+. The name
# itself is a valid package-style identifier (lowercase letter first,
# then alphanumerics / hyphens / underscores).
_LIST_NAME_RE = re.compile(r"^\u2502 {4}([a-z][A-Za-z0-9_-]*)\s*$")
_LIST_MARKER = "Available Skills"


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes (colour + cursor movement) from text."""
    return _ANSI_ESCAPE_RE.sub("", text)


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
            "npx executable not found on PATH; install Node.js (see "
            "'ai-dotfiles vendor npx_skills deps install')."
        ) from exc


@dataclass(frozen=True)
class _NpxSkillsVendor:
    """Concrete npx-skills vendor implementing the :class:`Vendor` protocol."""

    name: str = "npx_skills"
    display_name: str = "npx skills"
    description: str = "Install Claude Code skills via the 'skills' npm CLI."
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
                    origin=f"npx:skills:{source}",
                    license=_detect_license(entry),
                )
            )

        if not items:
            raise ExternalError(
                "npx skills add completed but produced no skill "
                f"directories under {skills_root}."
            )
        return items


NPX_SKILLS: _NpxSkillsVendor = _NpxSkillsVendor()
"""Module-level singleton registered as the npx-skills vendor."""

__all__ = ["NPX_SKILLS"]
