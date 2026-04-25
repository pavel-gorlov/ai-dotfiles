"""Integration tests for ``ai-dotfiles install`` (project and global)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_dotfiles.commands.install import install

pytestmark = pytest.mark.integration


# ── Fixtures ──────────────────────────────────────────────────────────────


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
    rules: list[str] | None = None,
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
    for rule in rules or []:
        _write(domain / "rules" / f"{rule}.md", f"# {rule}\n")
    for hook in hooks or []:
        _write(domain / "hooks" / hook, "#!/bin/sh\necho hi\n")
    if fragment is not None:
        _write(domain / "settings.fragment.json", json.dumps(fragment))
    return domain


def _make_standalone_skill(catalog: Path, name: str) -> Path:
    skill = catalog / "skills" / name
    skill.mkdir(parents=True, exist_ok=True)
    _write(skill / "SKILL.md", f"# {name}\n")
    return skill


def _make_standalone_agent(catalog: Path, name: str) -> Path:
    path = catalog / "agents" / f"{name}.md"
    _write(path, f"# {name}\n")
    return path


def _make_standalone_rule(catalog: Path, name: str) -> Path:
    path = catalog / "rules" / f"{name}.md"
    _write(path, f"# {name}\n")
    return path


def _run(project: Path, *args: str) -> tuple[int, str, str]:
    runner = CliRunner()
    cwd = os.getcwd()
    os.chdir(project)
    try:
        result = runner.invoke(install, list(args), catch_exceptions=False)
    finally:
        os.chdir(cwd)
    return result.exit_code, result.stdout, result.stderr


def _run_global() -> tuple[int, str, str]:
    runner = CliRunner()
    result = runner.invoke(install, ["-g"], catch_exceptions=False)
    return result.exit_code, result.stdout, result.stderr


# ── Project install tests ─────────────────────────────────────────────────


def test_install_project_domain(project: Path, catalog: Path) -> None:
    _make_domain(
        catalog,
        "python",
        skills=["pytest-helper"],
        agents=["researcher"],
        rules=["style"],
        hooks=["lint.sh"],
    )
    _write_manifest(project / "ai-dotfiles.json", ["@python"])

    code, _, _ = _run(project)
    assert code == 0

    cd = project / ".claude"
    assert (cd / "skills" / "pytest-helper").is_symlink()
    assert (cd / "agents" / "researcher.md").is_symlink()
    assert (cd / "rules" / "style.md").is_symlink()
    assert (cd / "hooks" / "lint.sh").is_symlink()


def test_install_project_standalone_skill(project: Path, catalog: Path) -> None:
    _make_standalone_skill(catalog, "code-review")
    _write_manifest(project / "ai-dotfiles.json", ["skill:code-review"])

    code, _, _ = _run(project)
    assert code == 0
    assert (project / ".claude" / "skills" / "code-review").is_symlink()


def test_install_project_standalone_agent(project: Path, catalog: Path) -> None:
    _make_standalone_agent(catalog, "researcher")
    _write_manifest(project / "ai-dotfiles.json", ["agent:researcher"])

    code, _, _ = _run(project)
    assert code == 0
    assert (project / ".claude" / "agents" / "researcher.md").is_symlink()


def test_install_project_standalone_rule(project: Path, catalog: Path) -> None:
    _make_standalone_rule(catalog, "security")
    _write_manifest(project / "ai-dotfiles.json", ["rule:security"])

    code, _, _ = _run(project)
    assert code == 0
    assert (project / ".claude" / "rules" / "security.md").is_symlink()


def test_install_project_mixed(project: Path, catalog: Path) -> None:
    _make_domain(catalog, "python", skills=["s1"])
    _make_standalone_skill(catalog, "code-review")
    _make_standalone_agent(catalog, "researcher")
    _make_standalone_rule(catalog, "security")
    _write_manifest(
        project / "ai-dotfiles.json",
        ["@python", "skill:code-review", "agent:researcher", "rule:security"],
    )

    code, out, _ = _run(project)
    assert code == 0

    cd = project / ".claude"
    assert (cd / "skills" / "s1").is_symlink()
    assert (cd / "skills" / "code-review").is_symlink()
    assert (cd / "agents" / "researcher.md").is_symlink()
    assert (cd / "rules" / "security.md").is_symlink()
    assert "Installed 4 packages" in out


def test_install_project_settings_merge(project: Path, catalog: Path) -> None:
    fragment = {
        "hooks": {"PostToolUse": [{"matcher": "Write", "hooks": [{"command": "fmt"}]}]},
    }
    _make_domain(catalog, "python", skills=["s1"], fragment=fragment)
    _write_manifest(project / "ai-dotfiles.json", ["@python"])

    code, out, _ = _run(project)
    assert code == 0

    settings_path = project / ".claude" / "settings.json"
    assert settings_path.is_file()
    data = json.loads(settings_path.read_text())
    assert "hooks" in data
    assert "PostToolUse" in data["hooks"]
    assert "merged 1 domain fragment" in out


def test_install_project_no_manifest(project: Path, catalog: Path) -> None:
    # No ai-dotfiles.json; .git present.
    code, _, err = _run(project)
    assert code != 0
    assert "ai-dotfiles.json not found" in err


def test_install_project_empty_packages(project: Path, catalog: Path) -> None:
    _write_manifest(project / "ai-dotfiles.json", [])

    code, out, _ = _run(project)
    assert code == 0
    assert "Nothing to install" in out


def test_install_project_missing_package(project: Path, catalog: Path) -> None:
    _write_manifest(project / "ai-dotfiles.json", ["@does-not-exist"])

    code, _, err = _run(project)
    assert code != 0
    assert "does-not-exist" in err
    assert "not found" in err.lower()


def test_install_project_idempotent(project: Path, catalog: Path) -> None:
    _make_domain(
        catalog,
        "python",
        skills=["pytest-helper"],
        hooks=["lint.sh"],
        fragment={"hooks": {"PostToolUse": [{"matcher": "X"}]}},
    )
    _write_manifest(project / "ai-dotfiles.json", ["@python"])

    code1, _, _ = _run(project)
    assert code1 == 0
    settings1 = (project / ".claude" / "settings.json").read_text()
    link1 = os.readlink(project / ".claude" / "skills" / "pytest-helper")

    code2, _, _ = _run(project)
    assert code2 == 0
    settings2 = (project / ".claude" / "settings.json").read_text()
    link2 = os.readlink(project / ".claude" / "skills" / "pytest-helper")

    assert settings1 == settings2
    assert link1 == link2


# ── Global install tests ──────────────────────────────────────────────────


def test_install_global(home: Path, storage: Path) -> None:
    global_dir = storage / "global"
    _write(global_dir / "CLAUDE.md", "# global claude\n")
    _write(global_dir / "settings.json", "{}\n")
    _write(global_dir / "hooks" / "pre.sh", "#!/bin/sh\n")
    # Empty global manifest.
    _write_manifest(storage / "global.json", [])

    code, _, _ = _run_global()
    assert code == 0

    claude = home / ".claude"
    assert (claude / "CLAUDE.md").is_symlink()
    assert (claude / "settings.json").is_symlink()
    assert (claude / "hooks" / "pre.sh").is_symlink()


def test_install_global_with_packages(home: Path, storage: Path, catalog: Path) -> None:
    _write(storage / "global" / "CLAUDE.md", "# g\n")
    _make_domain(catalog, "python", skills=["s1"])
    _make_standalone_agent(catalog, "researcher")
    _write_manifest(storage / "global.json", ["@python", "agent:researcher"])

    code, _, _ = _run_global()
    assert code == 0

    claude = home / ".claude"
    assert (claude / "CLAUDE.md").is_symlink()
    assert (claude / "skills" / "s1").is_symlink()
    assert (claude / "agents" / "researcher.md").is_symlink()


def test_install_global_no_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home_dir = tmp_path / "h"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))
    missing_storage = tmp_path / "missing-storage"
    monkeypatch.setenv("AI_DOTFILES_HOME", str(missing_storage))

    code, _, err = _run_global()
    assert code != 0
    assert "Storage not found" in err
