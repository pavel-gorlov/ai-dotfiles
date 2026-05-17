"""Integration tests for the Claude target ``link_mode: "copy"``.

Covers the non-symlink-capable-host path added in ai-21: ``install`` /
``add`` write real copied files into ``.claude/`` (no symlinks),
``remove`` cleans them, ``status`` does not misreport them, and a
user-authored file under ``.claude/`` is never deleted.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_dotfiles.commands.add import add
from ai_dotfiles.commands.install import install
from ai_dotfiles.commands.remove import remove
from ai_dotfiles.commands.status import status
from ai_dotfiles.core.copy_ownership import OWNERSHIP_FILENAME, load_copy_ownership

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


def _write_manifest(path: Path, packages: list[str], link_mode: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"packages": packages, "link_mode": link_mode}, indent=2) + "\n"
    )


def _make_standalone_skill(catalog: Path, name: str) -> Path:
    skill = catalog / "skills" / name
    skill.mkdir(parents=True, exist_ok=True)
    _write(skill / "SKILL.md", f"# {name}\n")
    return skill


def _make_standalone_agent(catalog: Path, name: str) -> Path:
    path = catalog / "agents" / f"{name}.md"
    _write(path, f"# {name}\n")
    return path


def _make_domain(catalog: Path, name: str, skills: list[str]) -> Path:
    domain = catalog / name
    for skill in skills:
        sdir = domain / "skills" / skill
        sdir.mkdir(parents=True, exist_ok=True)
        _write(sdir / "SKILL.md", f"# {skill}\n")
    return domain


def _run(cmd: object, project: Path, *args: str) -> tuple[int, str]:
    runner = CliRunner()
    cwd = os.getcwd()
    os.chdir(project)
    try:
        result = runner.invoke(cmd, list(args), catch_exceptions=False)  # type: ignore[arg-type]
    finally:
        os.chdir(cwd)
    return result.exit_code, result.output


# ── install in copy mode ──────────────────────────────────────────────────


def test_install_copy_mode_writes_real_files_no_symlinks(
    project: Path, catalog: Path
) -> None:
    _make_standalone_skill(catalog, "code-review")
    _make_standalone_agent(catalog, "researcher")
    _write_manifest(
        project / "ai-dotfiles.json",
        ["skill:code-review", "agent:researcher"],
        "copy",
    )

    code, _ = _run(install, project)
    assert code == 0

    cd = project / ".claude"
    skill = cd / "skills" / "code-review"
    agent = cd / "agents" / "researcher.md"

    # Real copied content, NOT symlinks.
    assert skill.is_dir() and not skill.is_symlink()
    assert agent.is_file() and not agent.is_symlink()
    assert (skill / "SKILL.md").read_text() == "# code-review\n"
    assert agent.read_text() == "# researcher\n"

    # Ownership sidecar records both copies.
    owned = load_copy_ownership(cd)
    assert owned == {"skills/code-review", "agents/researcher.md"}


def test_install_copy_mode_domain(project: Path, catalog: Path) -> None:
    _make_domain(catalog, "python", ["s1", "s2"])
    _write_manifest(project / "ai-dotfiles.json", ["@python"], "copy")

    code, _ = _run(install, project)
    assert code == 0

    cd = project / ".claude"
    for name in ("s1", "s2"):
        d = cd / "skills" / name
        assert d.is_dir() and not d.is_symlink()
    assert load_copy_ownership(cd) == {"skills/s1", "skills/s2"}


def test_install_copy_mode_refreshes_snapshot(project: Path, catalog: Path) -> None:
    skill = _make_standalone_skill(catalog, "code-review")
    _write_manifest(project / "ai-dotfiles.json", ["skill:code-review"], "copy")

    code, _ = _run(install, project)
    assert code == 0

    # Catalog changes; re-install must re-copy (a copy is a snapshot).
    (skill / "SKILL.md").write_text("# code-review v2\n")
    code, _ = _run(install, project)
    assert code == 0

    copied = project / ".claude" / "skills" / "code-review" / "SKILL.md"
    assert copied.read_text() == "# code-review v2\n"


# ── add in copy mode ──────────────────────────────────────────────────────


def test_add_copy_mode_copies_into_claude(project: Path, catalog: Path) -> None:
    _make_standalone_skill(catalog, "code-review")
    _write_manifest(project / "ai-dotfiles.json", [], "copy")

    code, _ = _run(add, project, "skill:code-review")
    assert code == 0

    skill = project / ".claude" / "skills" / "code-review"
    assert skill.is_dir() and not skill.is_symlink()
    assert load_copy_ownership(project / ".claude") == {"skills/code-review"}


# ── remove in copy mode ───────────────────────────────────────────────────


def test_remove_copy_mode_deletes_copy(project: Path, catalog: Path) -> None:
    _make_standalone_skill(catalog, "code-review")
    _make_standalone_skill(catalog, "keep-me")
    _write_manifest(
        project / "ai-dotfiles.json", ["skill:code-review", "skill:keep-me"], "copy"
    )
    _run(install, project)

    code, _ = _run(remove, project, "skill:code-review")
    assert code == 0

    cd = project / ".claude"
    assert not (cd / "skills" / "code-review").exists()
    assert (cd / "skills" / "keep-me").is_dir()
    assert load_copy_ownership(cd) == {"skills/keep-me"}


def test_remove_copy_mode_never_deletes_user_file(project: Path, catalog: Path) -> None:
    _make_standalone_skill(catalog, "code-review")
    _write_manifest(project / "ai-dotfiles.json", ["skill:code-review"], "copy")
    _run(install, project)

    # User authors their own skill of an unrelated name by hand.
    user_skill = project / ".claude" / "skills" / "my-own"
    user_skill.mkdir(parents=True)
    (user_skill / "SKILL.md").write_text("# mine\n")

    # And an unmanaged file colliding with a not-installed catalog name.
    _make_standalone_skill(catalog, "ghost")
    ghost = project / ".claude" / "skills" / "ghost"
    ghost.mkdir()
    (ghost / "SKILL.md").write_text("# user ghost\n")

    # Removing the managed skill must not touch either user file.
    code, _ = _run(remove, project, "skill:code-review")
    assert code == 0
    assert (user_skill / "SKILL.md").read_text() == "# mine\n"

    # Removing a name that exists on disk but was never ai-dotfiles-managed
    # must be a no-op on the filesystem.
    _write_manifest(
        project / "ai-dotfiles.json", ["skill:code-review", "skill:ghost"], "copy"
    )
    code, _ = _run(remove, project, "skill:ghost")
    assert code == 0
    assert (ghost / "SKILL.md").read_text() == "# user ghost\n"


# ── install --prune in copy mode ──────────────────────────────────────────


def test_install_prune_copy_mode_removes_stale_copy(
    project: Path, catalog: Path
) -> None:
    _make_standalone_skill(catalog, "code-review")
    _make_standalone_skill(catalog, "old-skill")
    _write_manifest(
        project / "ai-dotfiles.json", ["skill:code-review", "skill:old-skill"], "copy"
    )
    _run(install, project)

    # Drop one package from the manifest directly (simulating drift), then
    # install --prune must delete its now-stale copy.
    _write_manifest(project / "ai-dotfiles.json", ["skill:code-review"], "copy")
    code, out = _run(install, project, "--prune")
    assert code == 0

    cd = project / ".claude"
    assert (cd / "skills" / "code-review").is_dir()
    assert not (cd / "skills" / "old-skill").exists()
    assert "Pruned 1 copy" in out
    assert load_copy_ownership(cd) == {"skills/code-review"}


def test_install_prune_copy_mode_keeps_user_file(project: Path, catalog: Path) -> None:
    _make_standalone_skill(catalog, "code-review")
    _write_manifest(project / "ai-dotfiles.json", ["skill:code-review"], "copy")
    _run(install, project)

    user_skill = project / ".claude" / "skills" / "user-own"
    user_skill.mkdir(parents=True)
    (user_skill / "SKILL.md").write_text("# user\n")

    code, _ = _run(install, project, "--prune")
    assert code == 0
    assert (user_skill / "SKILL.md").read_text() == "# user\n"


# ── status in copy mode ───────────────────────────────────────────────────


def test_status_copy_mode_reports_ok_not_broken(project: Path, catalog: Path) -> None:
    _make_standalone_skill(catalog, "code-review")
    _write_manifest(project / "ai-dotfiles.json", ["skill:code-review"], "copy")
    _run(install, project)

    code, out = _run(status, project)
    assert code == 0
    assert "copy mode" in out
    assert "OK (copied)" in out
    assert "BROKEN" not in out


def test_status_copy_mode_flags_missing_copy(project: Path, catalog: Path) -> None:
    _make_standalone_skill(catalog, "code-review")
    _write_manifest(project / "ai-dotfiles.json", ["skill:code-review"], "copy")
    _run(install, project)

    # Delete the copied content behind ai-dotfiles' back.
    import shutil

    shutil.rmtree(project / ".claude" / "skills" / "code-review")

    code, out = _run(status, project)
    assert code == 1
    assert "NOT COPIED" in out


def test_status_copy_mode_flags_unmanaged_file(project: Path, catalog: Path) -> None:
    _make_standalone_skill(catalog, "code-review")
    _write_manifest(project / "ai-dotfiles.json", ["skill:code-review"], "copy")
    # No install — but the user drops a real file where the copy would go.
    target = project / ".claude" / "skills" / "code-review"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text("# user\n")

    code, out = _run(status, project)
    assert code == 1
    assert "BROKEN" in out


# ── symlink-mode regression guard ─────────────────────────────────────────


def test_symlink_mode_explicit_still_symlinks(project: Path, catalog: Path) -> None:
    _make_standalone_skill(catalog, "code-review")
    _write_manifest(project / "ai-dotfiles.json", ["skill:code-review"], "symlink")

    code, _ = _run(install, project)
    assert code == 0

    cd = project / ".claude"
    assert (cd / "skills" / "code-review").is_symlink()
    # No copy-ownership sidecar is written in symlink mode.
    assert not (cd / OWNERSHIP_FILENAME).exists()
