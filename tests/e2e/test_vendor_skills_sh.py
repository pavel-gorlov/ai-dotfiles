"""End-to-end tests for the ``skills_sh`` vendor.

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
from ai_dotfiles.vendors.skills_sh import SKILLS_SH, FindResult

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

    monkeypatch.setattr("ai_dotfiles.vendors.skills_sh.subprocess.run", fake_run)


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


# Real-world fixture captured from ``npx skills add vercel-labs/agent-skills --list``
# (April 2026). Skill name lines use U+2502 ``│`` + 4 spaces + name; description
# lines use 6+ spaces of indent. ANSI escape sequences are part of the real
# output and must be stripped by the parser.
_REAL_LIST_OUTPUT = (
    "\x1b[38;5;250m███╗\x1b[0m\n"
    "\n"
    "┌   skills \n"
    "│\n"
    "│  Tip: use --yes (-y) and --global (-g) flags to install without prompts.\n"
    "│\n"
    "◇  Source: https://github.com/vercel-labs/agent-skills.git\n"
    "│\n"
    "\x1b[?25l◇  Found 7 skills\n"
    "\n"
    "│\n"
    "◇  Available Skills\n"
    "│\n"
    "│    vercel-composition-patterns\n"
    "│\n"
    "│      React composition patterns that scale. Use when refactoring...\n"
    "│\n"
    "│    deploy-to-vercel\n"
    "│\n"
    "│      Deploy applications and websites to Vercel.\n"
    "│\n"
    "│    vercel-react-best-practices\n"
    "│\n"
    "│      React and Next.js performance optimization guidelines.\n"
    "│\n"
    "└  Done!\n"
)


def test_list_source_parses_real_upstream_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real box-drawing output from ``skills add --list`` parses correctly."""
    captured: dict[str, Any] = {}
    _install_fake_run(monkeypatch, captured=captured, stdout=_REAL_LIST_OUTPUT)

    names = list(SKILLS_SH.list_source("vercel-labs/agent-skills"))

    assert names == [
        "vercel-composition-patterns",
        "deploy-to-vercel",
        "vercel-react-best-practices",
    ]
    assert "--list" in captured["argv"]
    assert "vercel-labs/agent-skills" in captured["argv"]
    assert captured["argv"][:2] == ["npx", "-y"]


def test_list_source_ignores_descriptions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Description lines (6+ space indent) are not mistaken for names."""
    captured: dict[str, Any] = {}
    stdout = (
        "◇  Available Skills\n"
        "│\n"
        "│    skill-a\n"
        "│\n"
        "│      Description line with spaces that looks vaguely name-ish\n"
        "│\n"
        "│    skill-b\n"
        "│\n"
        "│      Another description.\n"
    )
    _install_fake_run(monkeypatch, captured=captured, stdout=stdout)

    assert list(SKILLS_SH.list_source("x")) == ["skill-a", "skill-b"]


def test_list_source_empty_output_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """No skills parsed → ExternalError."""
    captured: dict[str, Any] = {}
    _install_fake_run(
        monkeypatch,
        captured=captured,
        stdout="◇  Available Skills\n│\n│  (nothing)\n",
    )

    with pytest.raises(ExternalError) as excinfo:
        list(SKILLS_SH.list_source("somewhere"))
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
        list(SKILLS_SH.list_source("bad/src"))
    assert "boom: bad source" in str(excinfo.value)


def test_list_source_strips_ansi_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    """ANSI colour codes around the name are removed."""
    captured: dict[str, Any] = {}
    stdout = (
        "◇  Available Skills\n"
        "│\n"
        "\x1b[32m│    coloured-name\x1b[0m\n"
        "│\n"
        "│      desc\n"
    )
    _install_fake_run(monkeypatch, captured=captured, stdout=stdout)

    assert list(SKILLS_SH.list_source("x")) == ["coloured-name"]


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

    items = SKILLS_SH.fetch("vercel-labs/skills", select=None, workdir=tmp_path)

    assert [i.name for i in items] == ["alpha", "beta"]
    for item in items:
        assert item.kind == "skill"
        assert item.source_dir.is_dir()
        assert item.origin == "skills_sh:vercel-labs/skills"
        assert (item.source_dir / "SKILL.md").is_file()
        assert item.license is None

    # Baseline argv includes -g, --agent claude-code, --copy, -y and no --skill.
    assert "-g" in captured["argv"]
    assert captured["argv"].count("--agent") == 1
    agent_idx = captured["argv"].index("--agent")
    assert captured["argv"][agent_idx + 1] == "claude-code"
    assert "--copy" in captured["argv"]
    assert "-y" in captured["argv"]
    assert "--skill" not in captured["argv"]
    # HOME is redirected under workdir.
    assert captured["env"]["HOME"].startswith(str(tmp_path))


def test_fetch_with_select_passes_dash_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``select=('one','two')`` forwards as ``--skill one two``."""
    captured: dict[str, Any] = {}

    def side_effect(argv: list[str], env: dict[str, Any]) -> None:
        _materialize_skills(
            env, skills={"one": {"SKILL.md": "# one\n"}, "two": {"SKILL.md": "# two\n"}}
        )

    _install_fake_run(monkeypatch, captured=captured, side_effect=side_effect)

    items = SKILLS_SH.fetch(
        "vercel-labs/skills", select=("one", "two"), workdir=tmp_path
    )

    argv = captured["argv"]
    assert "--skill" in argv
    s_idx = argv.index("--skill")
    # The two selected names appear right after ``--skill``.
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
        SKILLS_SH.fetch("nope", select=None, workdir=tmp_path)
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
        SKILLS_SH.fetch("empty", select=None, workdir=tmp_path)
    assert "no skill" in str(excinfo.value).lower()


def test_fetch_missing_skills_dir_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zero-exit but CLI produced nothing under HOME → ExternalError."""
    captured: dict[str, Any] = {}
    _install_fake_run(monkeypatch, captured=captured)

    with pytest.raises(ExternalError) as excinfo:
        SKILLS_SH.fetch("nothing", select=None, workdir=tmp_path)
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

    items = SKILLS_SH.fetch("src", select=None, workdir=tmp_path)

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

    items = SKILLS_SH.fetch("src", select=None, workdir=tmp_path)
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

    items = SKILLS_SH.fetch("src", select=None, workdir=tmp_path)
    assert items[0].license is not None
    assert len(items[0].license) == 60
    assert items[0].license == "X" * 60


# ── deps ──


def test_vendor_metadata() -> None:
    """Module-level constants for the vendor."""
    assert SKILLS_SH.name == "skills_sh"
    assert SKILLS_SH.display_name == "skills.sh"
    assert SKILLS_SH.description == (
        "Install Claude Code skills from the skills.sh marketplace."
    )
    # Runtime protocol check.
    assert isinstance(SKILLS_SH, Vendor)


def test_vendor_deps_contains_npx() -> None:
    dep_names = [d.name for d in SKILLS_SH.deps]
    assert "npx" in dep_names


def test_npx_dependency_is_installed_true_when_on_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ai_dotfiles.vendors.skills_sh.shutil.which",
        lambda _name: "/usr/bin/npx",
    )
    npx_dep = next(d for d in SKILLS_SH.deps if d.name == "npx")
    assert npx_dep.is_installed() is True


def test_npx_dependency_is_installed_false_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ai_dotfiles.vendors.skills_sh.shutil.which", lambda _name: None
    )
    npx_dep = next(d for d in SKILLS_SH.deps if d.name == "npx")
    assert npx_dep.is_installed() is False


# ── find ──


# Real fixture captured from ``npx skills find react`` (April 2026). Each
# result is a name line + an arrow-prefixed marketplace URL line, plus
# ANSI colour codes.
_REAL_FIND_OUTPUT = (
    "\x1b[38;5;250m███╗\x1b[0m\n"
    "\n"
    "\x1b[38;5;102mInstall with\x1b[0m npx skills add <owner/repo@skill>\n"
    "\n"
    "\x1b[38;5;145mvercel-labs/agent-skills@vercel-react-best-practices\x1b[0m "
    "\x1b[36m321.7K installs\x1b[0m\n"
    "\x1b[38;5;102m\u2514 https://skills.sh/vercel-labs/agent-skills/"
    "vercel-react-best-practices\x1b[0m\n"
    "\n"
    "\x1b[38;5;145mvercel-labs/agent-skills@vercel-react-native-skills\x1b[0m "
    "\x1b[36m92K installs\x1b[0m\n"
    "\x1b[38;5;102m\u2514 https://skills.sh/vercel-labs/agent-skills/"
    "vercel-react-native-skills\x1b[0m\n"
    "\n"
    "\x1b[38;5;145mgoogle-labs-code/stitch-skills@react:components\x1b[0m "
    "\x1b[36m36.4K installs\x1b[0m\n"
    "\x1b[38;5;102m\u2514 https://skills.sh/google-labs-code/"
    "stitch-skills/react:components\x1b[0m\n"
)


def test_find_parses_real_upstream_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real `skills find` output parses into FindResult entries."""
    captured: dict[str, Any] = {}
    _install_fake_run(monkeypatch, captured=captured, stdout=_REAL_FIND_OUTPUT)

    results = SKILLS_SH.find("react")

    assert len(results) == 3
    assert results[0] == FindResult(
        source="vercel-labs/agent-skills",
        name="vercel-react-best-practices",
        installs="321.7K",
        url="https://skills.sh/vercel-labs/agent-skills/vercel-react-best-practices",
    )
    assert results[2].source == "google-labs-code/stitch-skills"
    assert results[2].name == "react:components"
    # argv includes find + the query
    assert "find" in captured["argv"]
    assert "react" in captured["argv"]


def test_find_without_installs_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing install-count does not break parsing."""
    captured: dict[str, Any] = {}
    stdout = "alice/skills@thing\n" "\u2514 https://skills.sh/alice/skills/thing\n"
    _install_fake_run(monkeypatch, captured=captured, stdout=stdout)

    results = SKILLS_SH.find("thing")
    assert len(results) == 1
    assert results[0].installs == ""
    assert results[0].url == "https://skills.sh/alice/skills/thing"


def test_find_empty_query_raises() -> None:
    """Blank query is rejected before any subprocess call."""
    with pytest.raises(ValueError):
        SKILLS_SH.find("")
    with pytest.raises(ValueError):
        SKILLS_SH.find("   ")


def test_find_nonzero_exit_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    _install_fake_run(
        monkeypatch,
        captured=captured,
        returncode=3,
        stderr="upstream boom\n",
    )
    with pytest.raises(ExternalError) as excinfo:
        SKILLS_SH.find("query")
    assert "upstream boom" in str(excinfo.value)


def test_find_empty_result_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    _install_fake_run(
        monkeypatch,
        captured=captured,
        stdout="no matches\n",
    )
    with pytest.raises(ExternalError) as excinfo:
        SKILLS_SH.find("nothing")
    assert "no results" in str(excinfo.value).lower()


# ── subprocess errors ──


def test_fetch_missing_npx_raises_external_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``FileNotFoundError`` from ``subprocess.run`` is wrapped."""

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(2, "No such file", "npx")

    monkeypatch.setattr("ai_dotfiles.vendors.skills_sh.subprocess.run", fake_run)

    with pytest.raises(ExternalError) as excinfo:
        SKILLS_SH.fetch("x", select=None, workdir=tmp_path)
    assert "npx executable not found" in str(excinfo.value)
