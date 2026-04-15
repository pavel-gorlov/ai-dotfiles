"""E2E tests for ``ai-dotfiles status``."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_dotfiles.commands.status import status


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))
    return home_dir


@pytest.fixture
def storage(home: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    storage_dir = home / ".ai-dotfiles"
    storage_dir.mkdir()
    monkeypatch.setenv("AI_DOTFILES_HOME", str(storage_dir))
    (storage_dir / "catalog").mkdir()
    (storage_dir / "global").mkdir()
    return storage_dir


@pytest.fixture
def catalog(storage: Path) -> Path:
    return storage / "catalog"


@pytest.fixture
def project(home: Path) -> Path:
    proj = home / "proj"
    proj.mkdir()
    (proj / ".git").mkdir()
    return proj


def _write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_manifest(path: Path, packages: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"packages": packages}, indent=2) + "\n")


def _make_domain(
    catalog: Path,
    name: str,
    *,
    skills: list[str] | None = None,
    agents: list[str] | None = None,
    hooks: list[str] | None = None,
    fragment: dict | None = None,
) -> Path:
    domain = catalog / name
    domain.mkdir(parents=True, exist_ok=True)
    for skill in skills or []:
        sdir = domain / "skills" / skill
        sdir.mkdir(parents=True, exist_ok=True)
        _write(sdir / "SKILL.md", f"# {skill}\n")
    for agent in agents or []:
        _write(domain / "agents" / f"{agent}.md", f"# {agent}\n")
    for hook in hooks or []:
        _write(domain / "hooks" / hook, "#!/bin/sh\necho hi\n")
    if fragment is not None:
        _write(domain / "settings.fragment.json", json.dumps(fragment))
    return domain


def _make_standalone_agent(catalog: Path, name: str) -> Path:
    path = catalog / "agents" / f"{name}.md"
    _write(path, f"# {name}\n")
    return path


def _link(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(source.resolve())


def _run(project: Path, *args: str) -> tuple[int, str, str]:
    runner = CliRunner()
    cwd = os.getcwd()
    os.chdir(project)
    try:
        result = runner.invoke(status, list(args), catch_exceptions=False)
    finally:
        os.chdir(cwd)
    return result.exit_code, result.stdout, result.stderr


# ── Tests ─────────────────────────────────────────────────────────────────


def test_status_all_ok(project: Path, catalog: Path) -> None:
    _make_domain(catalog, "python", skills=["py-lint"], agents=["py-debug"])
    _write_manifest(project / "ai-dotfiles.json", ["@python"])

    cd = project / ".claude"
    _link(catalog / "python" / "skills" / "py-lint", cd / "skills" / "py-lint")
    _link(
        catalog / "python" / "agents" / "py-debug.md",
        cd / "agents" / "py-debug.md",
    )

    code, out, _ = _run(project)
    assert code == 0
    assert "OK" in out
    assert "@python" in out
    assert "All OK" in out


def test_status_broken_symlink(project: Path, catalog: Path) -> None:
    _make_domain(catalog, "python", skills=["py-lint"])
    _write_manifest(project / "ai-dotfiles.json", ["@python"])

    cd = project / ".claude"
    target = cd / "skills" / "py-lint"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(catalog / "python" / "skills" / "does-not-exist")

    code, out, _ = _run(project)
    assert code == 1
    assert "BROKEN" in out
    assert "Issues:" in out


def test_status_missing_symlink(project: Path, catalog: Path) -> None:
    _make_domain(catalog, "python", skills=["py-lint"])
    _write_manifest(project / "ai-dotfiles.json", ["@python"])

    # Nothing linked in .claude/.
    code, out, _ = _run(project)
    assert code == 1
    assert "NOT LINKED" in out
    assert "Issues:" in out


def test_status_settings_summary(project: Path, catalog: Path) -> None:
    fragment = {
        "_domain": "python",
        "hooks": {
            "PostToolUse": [
                {"matcher": "Write", "hooks": [{"command": "fmt"}]},
                {"matcher": "Edit", "hooks": [{"command": "lint"}]},
            ]
        },
    }
    _make_domain(catalog, "python", skills=["py-lint"], fragment=fragment)
    _write_manifest(project / "ai-dotfiles.json", ["@python"])

    cd = project / ".claude"
    _link(catalog / "python" / "skills" / "py-lint", cd / "skills" / "py-lint")

    # Write assembled settings.json (as install would).
    (cd / "settings.json").write_text(
        json.dumps({"hooks": fragment["hooks"]}, indent=2) + "\n"
    )

    code, out, _ = _run(project)
    assert code == 0
    assert "Settings:" in out
    assert "PostToolUse" in out
    assert "2 handlers" in out
    assert "Merged from: @python" in out


def test_status_empty_manifest(project: Path, catalog: Path) -> None:
    _write_manifest(project / "ai-dotfiles.json", [])

    code, out, _ = _run(project)
    assert code == 0
    assert "No packages installed" in out


def test_status_no_manifest(project: Path, catalog: Path) -> None:
    # .git present but no ai-dotfiles.json.
    code, _, err = _run(project)
    assert code != 0
    assert "ai-dotfiles.json not found" in err


def test_status_standalone_ok(project: Path, catalog: Path) -> None:
    _make_standalone_agent(catalog, "researcher")
    _write_manifest(project / "ai-dotfiles.json", ["agent:researcher"])

    cd = project / ".claude"
    _link(catalog / "agents" / "researcher.md", cd / "agents" / "researcher.md")

    code, out, _ = _run(project)
    assert code == 0
    assert "agent:researcher" in out
    assert "OK" in out


def test_status_global(home: Path, storage: Path, catalog: Path) -> None:
    _make_standalone_agent(catalog, "researcher")
    _write_manifest(storage / "global.json", ["agent:researcher"])

    claude = home / ".claude"
    _link(catalog / "agents" / "researcher.md", claude / "agents" / "researcher.md")

    runner = CliRunner()
    result = runner.invoke(status, ["-g"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "agent:researcher" in result.stdout
