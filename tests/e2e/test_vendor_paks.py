"""End-to-end tests for the ``paks`` vendor.

All tests exercise the :class:`~ai_dotfiles.vendors.base.Vendor`
protocol surface directly. ``subprocess.run`` is monkeypatched to
avoid invoking the real ``paks`` binary and to fake the target
directory layout it would produce under ``<workdir>/out/``.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ai_dotfiles.core.errors import ElementError, ExternalError
from ai_dotfiles.vendors.base import Vendor
from ai_dotfiles.vendors.paks import PAKS, SearchResult

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
    """Patch ``subprocess.run`` in the paks vendor module.

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

    monkeypatch.setattr("ai_dotfiles.vendors.paks.subprocess.run", fake_run)


def _materialize_nested(
    argv: list[str],
    *,
    skills: dict[str, dict[str, str]],
) -> None:
    """Lay down ``<--dir>/.claude/skills/<name>/`` entries.

    Reads the ``--dir`` argument from the captured argv so the
    side-effect matches the real command's output layout.
    """
    out = _argv_dir(argv)
    skills_root = out / ".claude" / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    for skill_name, files in skills.items():
        skill_dir = skills_root / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        for fname, body in files.items():
            (skill_dir / fname).write_text(body, encoding="utf-8")


def _materialize_flat(
    argv: list[str],
    *,
    skills: dict[str, dict[str, str]],
) -> None:
    """Lay down ``<--dir>/<name>/`` entries (fallback layout)."""
    out = _argv_dir(argv)
    out.mkdir(parents=True, exist_ok=True)
    for skill_name, files in skills.items():
        skill_dir = out / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        for fname, body in files.items():
            (skill_dir / fname).write_text(body, encoding="utf-8")


def _argv_dir(argv: list[str]) -> Path:
    """Return the ``Path`` passed after ``--dir`` in ``argv``."""
    idx = argv.index("--dir")
    return Path(argv[idx + 1])


# ── list_source ──


def test_list_source_returns_source_without_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``list_source`` echoes the source back; no subprocess call."""

    def boom(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("subprocess.run must not be called by list_source")

    monkeypatch.setattr("ai_dotfiles.vendors.paks.subprocess.run", boom)

    assert list(PAKS.list_source("kubernetes-deploy")) == ["kubernetes-deploy"]


# ── fetch ──


def test_fetch_happy_path_nested_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``out/.claude/skills/<name>/`` dirs materialize → FetchedItems."""
    captured: dict[str, Any] = {}

    def side_effect(argv: list[str], _env: dict[str, Any]) -> None:
        _materialize_nested(
            argv,
            skills={
                "alpha": {"SKILL.md": "# alpha\n"},
                "beta": {"SKILL.md": "# beta\n"},
            },
        )

    _install_fake_run(monkeypatch, captured=captured, side_effect=side_effect)

    items = PAKS.fetch("stakpak/alpha", select=None, workdir=tmp_path)

    assert [i.name for i in items] == ["alpha", "beta"]
    for item in items:
        assert item.kind == "skill"
        assert item.source_dir.is_dir()
        assert item.origin == "paks:stakpak/alpha"
        assert (item.source_dir / "SKILL.md").is_file()
        assert item.license is None


def test_fetch_fallback_flat_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When ``out/.claude/skills`` is missing, enumerate ``out/*/``."""
    captured: dict[str, Any] = {}

    def side_effect(argv: list[str], _env: dict[str, Any]) -> None:
        _materialize_flat(argv, skills={"only-skill": {"SKILL.md": "# only\n"}})

    _install_fake_run(monkeypatch, captured=captured, side_effect=side_effect)

    items = PAKS.fetch("stakpak/only", select=None, workdir=tmp_path)

    assert len(items) == 1
    assert items[0].name == "only-skill"
    assert items[0].source_dir.is_dir()
    assert items[0].origin == "paks:stakpak/only"


def test_fetch_with_select_raises_element_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """paks has single-skill semantics — ``--select`` is rejected."""

    def boom(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("subprocess.run must not be called when --select is set")

    monkeypatch.setattr("ai_dotfiles.vendors.paks.subprocess.run", boom)

    with pytest.raises(ElementError) as excinfo:
        PAKS.fetch("stakpak/thing", select=("x",), workdir=tmp_path)
    assert "--select" in str(excinfo.value)


def test_fetch_nonzero_exit_raises_external_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-zero exit → ExternalError with stderr in the message."""
    captured: dict[str, Any] = {}
    _install_fake_run(
        monkeypatch,
        captured=captured,
        returncode=2,
        stderr="E: bad source\n",
    )

    with pytest.raises(ExternalError) as excinfo:
        PAKS.fetch("nope", select=None, workdir=tmp_path)
    assert "E: bad source" in str(excinfo.value)


def test_fetch_empty_result_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zero-exit but no skills materialized → ExternalError."""
    captured: dict[str, Any] = {}
    _install_fake_run(monkeypatch, captured=captured)

    with pytest.raises(ExternalError) as excinfo:
        PAKS.fetch("empty", select=None, workdir=tmp_path)
    assert "no skills" in str(excinfo.value).lower()


def test_fetch_argv_contains_required_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """argv includes ``--agent claude-code --scope global --dir <...> --yes``."""
    captured: dict[str, Any] = {}

    def side_effect(argv: list[str], _env: dict[str, Any]) -> None:
        _materialize_nested(argv, skills={"x": {"SKILL.md": "x"}})

    _install_fake_run(monkeypatch, captured=captured, side_effect=side_effect)

    PAKS.fetch("stakpak/x", select=None, workdir=tmp_path)

    argv = captured["argv"]
    assert argv[0] == "paks"
    assert argv[1] == "install"
    assert "stakpak/x" in argv

    agent_idx = argv.index("--agent")
    assert argv[agent_idx + 1] == "claude-code"

    scope_idx = argv.index("--scope")
    assert argv[scope_idx + 1] == "global"

    dir_idx = argv.index("--dir")
    # The --dir value lives under the caller's workdir, inside an ``out`` subdir.
    dir_path = Path(argv[dir_idx + 1])
    assert dir_path == tmp_path / "out"

    assert "--yes" in argv
    # Only PATH is forwarded.
    assert captured["env"] is not None
    assert set(captured["env"].keys()) == {"PATH"}


def test_fetch_detects_license(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``LICENSE`` first non-blank line becomes ``item.license``."""
    captured: dict[str, Any] = {}

    def side_effect(argv: list[str], _env: dict[str, Any]) -> None:
        _materialize_nested(
            argv,
            skills={
                "licensed": {
                    "SKILL.md": "# licensed\n",
                    "LICENSE": "\n\nMIT License\n\nCopyright 2026\n",
                }
            },
        )

    _install_fake_run(monkeypatch, captured=captured, side_effect=side_effect)

    items = PAKS.fetch("stakpak/licensed", select=None, workdir=tmp_path)

    assert len(items) == 1
    assert items[0].license == "MIT License"


def test_fetch_missing_paks_binary_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``FileNotFoundError`` from ``subprocess.run`` is wrapped."""

    def fake_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(2, "No such file", "paks")

    monkeypatch.setattr("ai_dotfiles.vendors.paks.subprocess.run", fake_run)

    with pytest.raises(ExternalError) as excinfo:
        PAKS.fetch("stakpak/x", select=None, workdir=tmp_path)
    assert "paks executable not found" in str(excinfo.value)


# ── search ──


def _search_payload() -> str:
    return json.dumps(
        [
            {
                "source": "stakpak/kubernetes-deploy",
                "name": "kubernetes-deploy",
                "description": "Deploy to Kubernetes clusters.",
                "url": "https://paks.stakpak.dev/stakpak/kubernetes-deploy",
            },
            {
                "source": "stakpak/helm-charts",
                "name": "helm-charts",
                "description": "Render and apply Helm charts.",
                "url": "https://paks.stakpak.dev/stakpak/helm-charts",
            },
        ]
    )


def test_search_parses_json_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """JSON array from ``paks search --format json`` parses correctly."""
    captured: dict[str, Any] = {}
    _install_fake_run(monkeypatch, captured=captured, stdout=_search_payload())

    results = PAKS.search("kubernetes")

    assert len(results) == 2
    assert results[0] == SearchResult(
        source="stakpak/kubernetes-deploy",
        name="kubernetes-deploy",
        description="Deploy to Kubernetes clusters.",
        url="https://paks.stakpak.dev/stakpak/kubernetes-deploy",
        installs="",
    )
    argv = captured["argv"]
    assert argv[0] == "paks"
    assert argv[1] == "search"
    assert "kubernetes" in argv
    assert "--format" in argv and "json" in argv


def test_search_handles_missing_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing JSON fields default to empty strings."""
    captured: dict[str, Any] = {}
    stdout = json.dumps([{"name": "lonely"}])
    _install_fake_run(monkeypatch, captured=captured, stdout=stdout)

    results = PAKS.search("lonely")

    assert len(results) == 1
    assert results[0].name == "lonely"
    assert results[0].source == ""
    assert results[0].description == ""
    assert results[0].url == ""


def test_search_nonzero_exit_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-zero exit → ExternalError with stderr in message."""
    captured: dict[str, Any] = {}
    _install_fake_run(
        monkeypatch,
        captured=captured,
        returncode=3,
        stderr="upstream boom\n",
    )

    with pytest.raises(ExternalError) as excinfo:
        PAKS.search("query")
    assert "upstream boom" in str(excinfo.value)


def test_search_empty_result_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty JSON array → ExternalError."""
    captured: dict[str, Any] = {}
    _install_fake_run(monkeypatch, captured=captured, stdout="[]")

    with pytest.raises(ExternalError) as excinfo:
        PAKS.search("nothing")
    assert "no results" in str(excinfo.value).lower()


def test_search_unparseable_json_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-JSON stdout is surfaced as ExternalError rather than silently empty."""
    captured: dict[str, Any] = {}
    _install_fake_run(monkeypatch, captured=captured, stdout="not json at all")

    with pytest.raises(ExternalError) as excinfo:
        PAKS.search("anything")
    assert "unparseable" in str(excinfo.value).lower()


def test_search_empty_query_raises() -> None:
    """Blank query is rejected before any subprocess call."""
    with pytest.raises(ValueError):
        PAKS.search("")
    with pytest.raises(ValueError):
        PAKS.search("   ")


# ── deps / metadata ──


def test_vendor_metadata() -> None:
    """Module-level constants for the vendor."""
    assert PAKS.name == "paks"
    assert PAKS.display_name == "paks"
    assert PAKS.description == ("Install Claude Code skills from the paks registry.")
    # Runtime protocol check.
    assert isinstance(PAKS, Vendor)


def test_vendor_deps_contains_paks() -> None:
    """The ``paks`` dep is declared with the upstream install URL."""
    dep_names = [d.name for d in PAKS.deps]
    assert dep_names == ["paks"]
    dep = PAKS.deps[0]
    assert dep.install_url == "https://paks.stakpak.dev"


def test_paks_dependency_is_installed_true_when_on_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ai_dotfiles.vendors.paks.shutil.which",
        lambda _name: "/opt/homebrew/bin/paks",
    )
    paks_dep = next(d for d in PAKS.deps if d.name == "paks")
    assert paks_dep.is_installed() is True


def test_paks_dependency_is_installed_false_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("ai_dotfiles.vendors.paks.shutil.which", lambda _name: None)
    paks_dep = next(d for d in PAKS.deps if d.name == "paks")
    assert paks_dep.is_installed() is False


def test_registered_in_vendor_registry() -> None:
    """The vendor is accessible via the shared registry under ``paks``."""
    from ai_dotfiles.vendors import REGISTRY

    assert "paks" in REGISTRY
    assert REGISTRY["paks"].name == "paks"
