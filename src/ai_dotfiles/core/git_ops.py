"""Git operations for ai-dotfiles.

Used by ``init -g --from`` (clone storage) and ``vendor`` (download external
elements from GitHub URLs).

All subprocess calls are wrapped so failures become :class:`ExternalError`.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from ai_dotfiles.core.errors import ExternalError

# ── GitHub URL parsing ─────────────────────────────────────────────────────

_HTTPS_TREE_RE = re.compile(
    r"^https?://github\.com/"
    r"(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?"
    r"(?:/tree/(?P<branch>[^/]+)(?:/(?P<subpath>.+?))?)?"
    r"/?$"
)

_SSH_RE = re.compile(r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$")


def parse_github_url(url: str) -> tuple[str, str, str, str] | None:
    """Parse a GitHub URL into ``(repo_url, branch, subpath, name)``.

    Accepts:

    - ``https://github.com/owner/repo`` — branch defaults to ``main``,
      subpath is empty, name is ``repo``.
    - ``https://github.com/owner/repo/tree/<branch>/<subpath>`` — branch and
      subpath are extracted; name is the last subpath segment.
    - ``https://github.com/owner/repo.git`` — treated like the root form.
    - ``git@github.com:owner/repo[.git]`` — SSH form; branch defaults to
      ``main``; name is ``repo``.

    Returns ``None`` if the URL does not look like a GitHub repository URL.
    """
    url = url.strip()

    ssh_match = _SSH_RE.match(url)
    if ssh_match is not None:
        owner = ssh_match.group("owner")
        repo = ssh_match.group("repo")
        repo_url = f"git@github.com:{owner}/{repo}.git"
        return repo_url, "main", "", repo

    https_match = _HTTPS_TREE_RE.match(url)
    if https_match is not None:
        owner = https_match.group("owner")
        repo = https_match.group("repo")
        branch = https_match.group("branch") or "main"
        subpath = (https_match.group("subpath") or "").strip("/")
        repo_url = f"https://github.com/{owner}/{repo}.git"
        name = subpath.rstrip("/").split("/")[-1] if subpath else repo
        return repo_url, branch, subpath, name

    return None


# ── git subprocess wrappers ────────────────────────────────────────────────


def _run_git(
    args: list[str], cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run ``git <args>`` with ``check=True``. Wrap failures in ``ExternalError``."""
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd is not None else None,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise ExternalError("git executable not found on PATH") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        cmd = " ".join(["git", *args])
        msg = f"git command failed: {cmd}"
        if stderr:
            msg = f"{msg}\n{stderr}"
        raise ExternalError(msg) from exc


def git_clone(url: str, dest: Path, branch: str | None = None) -> None:
    """Clone ``url`` into ``dest``.

    Runs ``git clone [--branch <branch>] <url> <dest>``. The parent of
    ``dest`` must exist; ``dest`` itself must not exist (git enforces this).
    """
    args = ["clone"]
    if branch:
        args += ["--branch", branch]
    args += [url, str(dest)]
    _run_git(args)


def git_sparse_checkout(
    url: str,
    subpath: str,
    dest: Path,
    branch: str | None = None,
) -> None:
    """Clone only ``subpath`` from ``url`` into ``dest``.

    Strategy:

    1. ``git clone --filter=blob:none --no-checkout [--branch <branch>] <url> <tmp>``
    2. ``git -C <tmp> sparse-checkout set <subpath>``
    3. ``git -C <tmp> checkout``
    4. Move ``<tmp>/<subpath>`` to ``<dest>``.

    If the sparse-checkout command fails (e.g. git is too old), falls back to
    a full clone followed by a copy of ``subpath``.
    """
    if not subpath:
        git_clone(url, dest, branch=branch)
        return

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / "repo"

        clone_args = ["clone", "--filter=blob:none", "--no-checkout"]
        if branch:
            clone_args += ["--branch", branch]
        clone_args += [url, str(tmp_path)]

        try:
            _run_git(clone_args)
            _run_git(["sparse-checkout", "set", subpath], cwd=tmp_path)
            _run_git(["checkout"], cwd=tmp_path)
        except ExternalError:
            # Fallback: full clone into a fresh tmp dir.
            shutil.rmtree(tmp_path, ignore_errors=True)
            git_clone(url, tmp_path, branch=branch)

        source = tmp_path / subpath
        if not source.exists():
            raise ExternalError(f"subpath {subpath!r} not found in repository {url!r}")

        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            raise ExternalError(f"destination already exists: {dest}")
        shutil.copytree(source, dest)


# ── Element type detection ─────────────────────────────────────────────────

_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(?P<body>.*?)\n---\s*(?:\n|$)",
    re.DOTALL,
)


def _read_frontmatter(path: Path) -> dict[str, str] | None:
    """Return the YAML-ish frontmatter of a markdown file as a dict, or None."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return None
    result: dict[str, str] = {}
    for line in match.group("body").splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        result[key.strip().lower()] = value.strip().strip("\"'")
    return result


def detect_element_type(path: Path) -> str | None:
    """Detect the kind of element at ``path``.

    Returns one of ``"skill"``, ``"agent"``, ``"rule"``, or ``None``.

    - A directory containing ``SKILL.md`` is a skill.
    - A single ``.md`` file whose frontmatter declares ``type: agent`` (or
      that lives in an ``agents/`` directory) is an agent.
    - A single ``.md`` file whose frontmatter declares ``type: rule`` (or
      that lives in a ``rules/`` directory) is a rule.
    - Otherwise ``None`` is returned.
    """
    if path.is_dir():
        if (path / "SKILL.md").is_file():
            return "skill"
        return None

    if path.is_file() and path.suffix.lower() == ".md":
        fm = _read_frontmatter(path) or {}
        declared = fm.get("type") or fm.get("kind")
        if declared in {"agent", "rule", "skill"}:
            return declared

        parents = {p.name.lower() for p in path.parents}
        if "agents" in parents:
            return "agent"
        if "rules" in parents:
            return "rule"

        # Heuristic: presence of an ``agent``/``rule`` key in frontmatter.
        if "agent" in fm:
            return "agent"
        if "rule" in fm:
            return "rule"

    return None
