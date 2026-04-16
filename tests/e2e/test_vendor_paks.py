"""End-to-end tests for the ``paks`` vendor.

All tests exercise the :class:`~ai_dotfiles.vendors.base.Vendor`
protocol surface directly. ``subprocess.run`` is monkeypatched to
avoid invoking the real ``paks`` binary and to fake the ``<--dir>``
directory layout it would produce.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ai_dotfiles.core.errors import ElementError, ExternalError
from ai_dotfiles.vendors.base import Vendor
from ai_dotfiles.vendors.paks import PAKS

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
    """Patch ``subprocess.run`` in the paks vendor module."""

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


def _argv_dir(argv: list[str]) -> Path:
    """Return the ``Path`` passed after ``--dir`` in ``argv``."""
    idx = argv.index("--dir")
    return Path(argv[idx + 1])


def _materialize_out(
    argv: list[str],
    *,
    skills: dict[str, dict[str, str]],
) -> None:
    """Lay down ``<--dir>/<owner>--<skill>/`` entries.

    Mimics what ``paks install --dir <out>`` does in reality: each skill
    lands in a single directory at the top level of ``--dir``, named
    ``<owner>--<skill>``. ``skills`` keys are the raw directory names;
    values are the files to create inside.
    """
    out = _argv_dir(argv)
    out.mkdir(parents=True, exist_ok=True)
    for raw_name, files in skills.items():
        skill_dir = out / raw_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        for fname, body in files.items():
            (skill_dir / fname).write_text(body, encoding="utf-8")


# ── list_source ──


def test_list_source_returns_source_without_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``list_source`` echoes the source back; no subprocess call."""

    def boom(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("subprocess.run must not be called by list_source")

    monkeypatch.setattr("ai_dotfiles.vendors.paks.subprocess.run", boom)

    assert list(PAKS.list_source("stakpak/kubernetes-deploy")) == [
        "stakpak/kubernetes-deploy"
    ]


# ── fetch ──


def test_fetch_happy_path_strips_owner_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """paks produces ``<owner>--<skill>/``; catalog entry is just ``<skill>``."""
    captured: dict[str, Any] = {}

    def side_effect(argv: list[str], _env: dict[str, Any]) -> None:
        _materialize_out(
            argv,
            skills={
                "wshpbson--k8s-manifest-generator": {"SKILL.md": "# k8s\n"},
            },
        )

    _install_fake_run(monkeypatch, captured=captured, side_effect=side_effect)

    items = PAKS.fetch("wshpbson/k8s-manifest-generator", select=None, workdir=tmp_path)

    assert len(items) == 1
    assert items[0].name == "k8s-manifest-generator"
    assert items[0].kind == "skill"
    assert items[0].origin == "paks:wshpbson/k8s-manifest-generator"
    assert items[0].source_dir.is_dir()
    assert (items[0].source_dir / "SKILL.md").is_file()


def test_fetch_source_without_owner_prefix_keeps_dir_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When dir name has no ``--`` separator, use it verbatim."""
    captured: dict[str, Any] = {}

    def side_effect(argv: list[str], _env: dict[str, Any]) -> None:
        _materialize_out(argv, skills={"local-skill": {"SKILL.md": "x"}})

    _install_fake_run(monkeypatch, captured=captured, side_effect=side_effect)

    items = PAKS.fetch("./local-skill", select=None, workdir=tmp_path)

    assert len(items) == 1
    assert items[0].name == "local-skill"


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


def test_fetch_argv_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """argv = ``paks install <src> --dir <workdir/out> --force``."""
    captured: dict[str, Any] = {}

    def side_effect(argv: list[str], _env: dict[str, Any]) -> None:
        _materialize_out(argv, skills={"stakpak--x": {"SKILL.md": "x"}})

    _install_fake_run(monkeypatch, captured=captured, side_effect=side_effect)

    PAKS.fetch("stakpak/x", select=None, workdir=tmp_path)

    argv = captured["argv"]
    assert argv[0] == "paks"
    assert argv[1] == "install"
    assert "stakpak/x" in argv
    assert "--force" in argv
    # No agent / scope / yes / format flags — --dir is enough.
    assert "--agent" not in argv
    assert "--scope" not in argv
    assert "--yes" not in argv

    dir_idx = argv.index("--dir")
    dir_path = Path(argv[dir_idx + 1])
    assert dir_path == tmp_path / "out"

    # Only PATH is forwarded.
    assert captured["env"] is not None
    assert set(captured["env"].keys()) == {"PATH"}


def test_fetch_detects_license(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``LICENSE`` first non-blank line becomes ``item.license``."""
    captured: dict[str, Any] = {}

    def side_effect(argv: list[str], _env: dict[str, Any]) -> None:
        _materialize_out(
            argv,
            skills={
                "owner--licensed": {
                    "SKILL.md": "# licensed\n",
                    "LICENSE": "\n\nMIT License\n\nCopyright 2026\n",
                }
            },
        )

    _install_fake_run(monkeypatch, captured=captured, side_effect=side_effect)

    items = PAKS.fetch("owner/licensed", select=None, workdir=tmp_path)

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


# Real fixture captured from ``paks search kubernetes`` (paks 0.1.18,
# April 2026). Each hit is two lines: a name line with ``<owner>/<skill>``
# at 2-space indent followed by a download count, then a 4-space-indented
# description. ANSI colour codes around the name and count are stripped
# by the parser.
_REAL_SEARCH_OUTPUT = (
    "\n"
    "  \x1b[1;36mwshpbson\x1b[0m/\x1b[1mgitops-workflow\x1b[0m \x1b[2m\u21931\x1b[0m\n"
    "    \x1b[2mImplement GitOps workflows with ArgoCD and Flux for automated,"
    " declarati\u2026\x1b[0m\n"
    "  \x1b[1;36mwshpbson\x1b[0m/\x1b[1mk8s-manifest-generator\x1b[0m"
    " \x1b[2m\u21931\x1b[0m\n"
    "    \x1b[2mCreate production-ready Kubernetes manifests for Deployments,"
    " Services, \u2026\x1b[0m\n"
    "  \x1b[1;36mstakpak\x1b[0m/\x1b[1mconfighub-usage-guide\x1b[0m"
    " \x1b[2m\u21930\x1b[0m  \x1b[33m#confighub\x1b[0m \x1b[33m#kubernetes\x1b[0m\n"
    "    \x1b[2mA comprehensive guide for using ConfigHub to manage Kubernetes"
    " configura\u2026\x1b[0m\n"
    "\n"
    "  \x1b[2mInstall: paks install <owner>/<skill>\x1b[0m\n"
)


def test_search_parses_real_upstream_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real paks search text parses into ordered SearchResult entries."""
    captured: dict[str, Any] = {}
    _install_fake_run(monkeypatch, captured=captured, stdout=_REAL_SEARCH_OUTPUT)

    results = PAKS.search("kubernetes")

    assert len(results) == 3
    assert results[0].source == "wshpbson"
    assert results[0].name == "gitops-workflow"
    assert results[0].installs == "1"
    assert "GitOps" in results[0].description
    assert results[0].url == ("https://paks.stakpak.dev/wshpbson/gitops-workflow")
    assert results[1].name == "k8s-manifest-generator"
    assert results[2].source == "stakpak"
    assert results[2].name == "confighub-usage-guide"
    # argv does NOT include --format json (upstream doesn't support it).
    argv = captured["argv"]
    assert argv[0] == "paks"
    assert argv[1] == "search"
    assert "kubernetes" in argv
    assert "--format" not in argv


def test_search_footer_is_not_parsed_as_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ``Install: paks install <owner>/<skill>`` footer is ignored."""
    captured: dict[str, Any] = {}
    stdout = (
        "  owner/name \u21932\n"
        "    description\n"
        "\n"
        "  Install: paks install <owner>/<skill>\n"
    )
    _install_fake_run(monkeypatch, captured=captured, stdout=stdout)

    results = PAKS.search("x")

    assert len(results) == 1
    assert results[0].source == "owner"
    assert results[0].name == "name"


def test_search_nonzero_exit_raises(monkeypatch: pytest.MonkeyPatch) -> None:
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
    """No parseable hits → ExternalError."""
    captured: dict[str, Any] = {}
    _install_fake_run(monkeypatch, captured=captured, stdout="no results here\n")

    with pytest.raises(ExternalError) as excinfo:
        PAKS.search("nothing")
    assert "no results" in str(excinfo.value).lower()


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
    assert isinstance(PAKS, Vendor)


def test_vendor_deps_contains_paks() -> None:
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
