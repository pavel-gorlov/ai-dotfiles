"""End-to-end tests for the ``npx_skills`` vendor.

All tests exercise the :class:`~ai_dotfiles.vendors.base.Vendor`
protocol surface directly. ``subprocess.run`` is monkeypatched to
avoid invoking Node.js and to fake the target directory layout the
upstream CLI would produce under ``$HOME/.claude/skills/``.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ai_dotfiles.core.errors import ExternalError
from ai_dotfiles.vendors.base import Vendor
from ai_dotfiles.vendors.npx_skills import NPX_SKILLS

FakeRun = Callable[..., subprocess.CompletedProcess[str]]


def _make_completed(
    *,
    args: list[str],
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=args, returncode=returncode, stdout=stdout, stderr=stderr
    )


def _install_fake_run(
    monkeypatch: pytest.MonkeyPatch,
    *,
    captured: dict[str, Any],
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
    side_effect: Callable[[list[str], dict[str, Any]], None] | None = None,
) -> None:
    """Patch ``subprocess.run`` in the vendor module.

    Captures the invocation (argv, cwd, env) and optionally runs a
    ``side_effect`` to lay down files on disk the way the real CLI
    would.
    """

    def fake_run(
        argv: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        check: bool = False,
        capture_output: bool = False,
        text: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        captured["argv"] = list(argv)
        captured["cwd"] = cwd
        captured["env"] = dict(env) if env is not None else None
        captured["check"] = check
        captured["capture_output"] = capture_output
        captured["text"] = text
        if side_effect is not None:
            side_effect(list(argv), dict(env) if env is not None else {})
        return _make_completed(
            args=argv, returncode=returncode, stdout=stdout, stderr=stderr
        )

    monkeypatch.setattr("ai_dotfiles.vendors.npx_skills.subprocess.run", fake_run)


def _materialize_skills(
    env: dict[str, Any],
    *,
    skills: dict[str, dict[str, str]],
) -> None:
    """Create fake skill dirs under ``$HOME/.claude/skills/`` from ``env``.

    ``skills`` maps ``name -> {filename: contents}``; each entry becomes
    a directory with the given files.
    """
    home = Path(env["HOME"])
    skills_root = home / ".claude" / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    for skill_name, files in skills.items():
        skill_dir = skills_root / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        for fname, body in files.items():
            (skill_dir / fname).write_text(body, encoding="utf-8")


# ── list_source ──


def test_list_source_parses_skill_names(monkeypatch: pytest.MonkeyPatch) -> None:
    """Canonical list-output parses into ordered skill names."""
    captured: dict[str, Any] = {}
    stdout = (
        "Found skills in vercel-labs/skills:\n"
        "- skill-one\n"
        "- skill-two\n"
        "- skill-three\n"
    )
    _install_fake_run(monkeypatch, captured=captured, stdout=stdout)

    names = list(NPX_SKILLS.list_source("vercel-labs/skills"))

    assert names == ["skill-one", "skill-two", "skill-three"]
    # --list flag is present and source is passed through.
    assert "--list" in captured["argv"]
    assert "vercel-labs/skills" in captured["argv"]
    assert captured["argv"][:2] == ["npx", "-y"]


def test_list_source_empty_output_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zero skills parsed → ExternalError."""
    captured: dict[str, Any] = {}
    _install_fake_run(
        monkeypatch,
        captured=captured,
        stdout="Found skills in somewhere:\n",
    )

    with pytest.raises(ExternalError) as excinfo:
        list(NPX_SKILLS.list_source("somewhere"))
    assert "no skills" in str(excinfo.value).lower()


def test_list_source_nonzero_exit_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Upstream CLI non-zero exit is surfaced via ExternalError."""
    captured: dict[str, Any] = {}
    _install_fake_run(
        monkeypatch,
        captured=captured,
        returncode=2,
        stdout="",
        stderr="boom: bad source\n",
    )

    with pytest.raises(ExternalError) as excinfo:
        list(NPX_SKILLS.list_source("bad/src"))
    assert "boom: bad source" in str(excinfo.value)


def test_list_source_is_permissive_on_whitespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Extra leading whitespace / blank lines don't confuse the parser."""
    captured: dict[str, Any] = {}
    stdout = "Found skills in x:\n" "\n" "   - alpha\n" "- beta\n" "\n" "  - gamma\n"
    _install_fake_run(monkeypatch, captured=captured, stdout=stdout)

    assert list(NPX_SKILLS.list_source("x")) == ["alpha", "beta", "gamma"]


# ── fetch ──


def test_fetch_happy_path_returns_items(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two skills appear on disk → two FetchedItems are returned."""
    captured: dict[str, Any] = {}

    def side_effect(argv: list[str], env: dict[str, Any]) -> None:
        _materialize_skills(
            env,
            skills={
                "alpha": {"SKILL.md": "# alpha\n"},
                "beta": {"SKILL.md": "# beta\n"},
            },
        )

    _install_fake_run(monkeypatch, captured=captured, side_effect=side_effect)

    items = NPX_SKILLS.fetch("vercel-labs/skills", select=None, workdir=tmp_path)

    assert [i.name for i in items] == ["alpha", "beta"]
    for item in items:
        assert item.kind == "skill"
        assert item.source_dir.is_dir()
        assert item.origin == "npx:skills:vercel-labs/skills"
        assert (item.source_dir / "SKILL.md").is_file()
        assert item.license is None

    # Baseline argv includes --copy and -y and no -s.
    assert "--copy" in captured["argv"]
    assert "-y" in captured["argv"]
    assert "-s" not in captured["argv"]
    # HOME is redirected under workdir.
    assert captured["env"]["HOME"].startswith(str(tmp_path))


def test_fetch_with_select_passes_dash_s(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``select=('one','two')`` forwards as ``-s one two``."""
    captured: dict[str, Any] = {}

    def side_effect(argv: list[str], env: dict[str, Any]) -> None:
        _materialize_skills(
            env, skills={"one": {"SKILL.md": "# one\n"}, "two": {"SKILL.md": "# two\n"}}
        )

    _install_fake_run(monkeypatch, captured=captured, side_effect=side_effect)

    items = NPX_SKILLS.fetch(
        "vercel-labs/skills", select=("one", "two"), workdir=tmp_path
    )

    argv = captured["argv"]
    assert "-s" in argv
    s_idx = argv.index("-s")
    # The two selected names appear right after ``-s``.
    assert argv[s_idx + 1 : s_idx + 3] == ["one", "two"]
    assert {i.name for i in items} == {"one", "two"}


def test_fetch_nonzero_exit_raises_external_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-zero exit → ExternalError with stderr in the message."""
    captured: dict[str, Any] = {}
    _install_fake_run(
        monkeypatch,
        captured=captured,
        returncode=1,
        stderr="E: source not found\n",
    )

    with pytest.raises(ExternalError) as excinfo:
        NPX_SKILLS.fetch("nope", select=None, workdir=tmp_path)
    assert "E: source not found" in str(excinfo.value)


def test_fetch_success_but_empty_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zero-exit but no skills materialized → ExternalError."""
    captured: dict[str, Any] = {}

    def side_effect(argv: list[str], env: dict[str, Any]) -> None:
        # Create skills_root but leave it empty.
        home = Path(env["HOME"])
        (home / ".claude" / "skills").mkdir(parents=True, exist_ok=True)

    _install_fake_run(monkeypatch, captured=captured, side_effect=side_effect)

    with pytest.raises(ExternalError) as excinfo:
        NPX_SKILLS.fetch("empty", select=None, workdir=tmp_path)
    assert "no skill" in str(excinfo.value).lower()


def test_fetch_missing_skills_dir_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zero-exit but CLI produced nothing under HOME → ExternalError."""
    captured: dict[str, Any] = {}
    _install_fake_run(monkeypatch, captured=captured)

    with pytest.raises(ExternalError) as excinfo:
        NPX_SKILLS.fetch("nothing", select=None, workdir=tmp_path)
    assert "no skills directory" in str(excinfo.value).lower()


def test_fetch_skips_non_directory_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stray files alongside the skill dirs don't produce FetchedItems."""
    captured: dict[str, Any] = {}

    def side_effect(argv: list[str], env: dict[str, Any]) -> None:
        home = Path(env["HOME"])
        skills_root = home / ".claude" / "skills"
        skills_root.mkdir(parents=True, exist_ok=True)
        (skills_root / "real-skill").mkdir()
        (skills_root / "real-skill" / "SKILL.md").write_text("x", encoding="utf-8")
        (skills_root / "README.md").write_text("ignore me", encoding="utf-8")

    _install_fake_run(monkeypatch, captured=captured, side_effect=side_effect)

    items = NPX_SKILLS.fetch("src", select=None, workdir=tmp_path)

    assert [i.name for i in items] == ["real-skill"]


# ── license detection ──


def test_fetch_detects_license_first_line_truncated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``LICENSE`` first non-blank line becomes ``item.license``."""
    captured: dict[str, Any] = {}

    def side_effect(argv: list[str], env: dict[str, Any]) -> None:
        _materialize_skills(
            env,
            skills={
                "licensed": {
                    "SKILL.md": "# licensed\n",
                    "LICENSE": "\n\nMIT License\n\nCopyright 2026\n",
                }
            },
        )

    _install_fake_run(monkeypatch, captured=captured, side_effect=side_effect)

    items = NPX_SKILLS.fetch("src", select=None, workdir=tmp_path)
    assert len(items) == 1
    assert items[0].license == "MIT License"


def test_fetch_license_truncated_to_60_chars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}
    long_line = "X" * 200

    def side_effect(argv: list[str], env: dict[str, Any]) -> None:
        _materialize_skills(
            env,
            skills={"long": {"SKILL.md": "x", "LICENSE": long_line}},
        )

    _install_fake_run(monkeypatch, captured=captured, side_effect=side_effect)

    items = NPX_SKILLS.fetch("src", select=None, workdir=tmp_path)
    assert items[0].license is not None
    assert len(items[0].license) == 60
    assert items[0].license == "X" * 60


# ── deps ──


def test_vendor_metadata() -> None:
    """Module-level constants for the vendor."""
    assert NPX_SKILLS.name == "npx_skills"
    assert NPX_SKILLS.display_name == "npx skills"
    assert NPX_SKILLS.description == (
        "Install Claude Code skills via the 'skills' npm CLI."
    )
    # Runtime protocol check.
    assert isinstance(NPX_SKILLS, Vendor)


def test_vendor_deps_contains_npx() -> None:
    dep_names = [d.name for d in NPX_SKILLS.deps]
    assert "npx" in dep_names


def test_npx_dependency_is_installed_true_when_on_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ai_dotfiles.vendors.npx_skills.shutil.which",
        lambda _name: "/usr/bin/npx",
    )
    npx_dep = next(d for d in NPX_SKILLS.deps if d.name == "npx")
    assert npx_dep.is_installed() is True


def test_npx_dependency_is_installed_false_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ai_dotfiles.vendors.npx_skills.shutil.which", lambda _name: None
    )
    npx_dep = next(d for d in NPX_SKILLS.deps if d.name == "npx")
    assert npx_dep.is_installed() is False


def test_fetch_missing_npx_raises_external_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``FileNotFoundError`` from ``subprocess.run`` is wrapped."""

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(2, "No such file", "npx")

    monkeypatch.setattr("ai_dotfiles.vendors.npx_skills.subprocess.run", fake_run)

    with pytest.raises(ExternalError) as excinfo:
        NPX_SKILLS.fetch("x", select=None, workdir=tmp_path)
    assert "npx executable not found" in str(excinfo.value)
