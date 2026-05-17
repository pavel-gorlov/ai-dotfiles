"""Integration tests for the Codex CLI target (real-filesystem level).

Exercises the Codex render + apply layer through the actual command
modules against a ``tmp_path`` catalog and project — asserting the
on-disk shapes that ADR ai-1-1…ai-1-4 promise:

* a Codex skill materialises as a real ``.agents/skills/<name>/``
  directory with a generated ``SKILL.md`` plus symlinked support files;
* a Codex agent materialises as a generated ``.codex/agents/<name>.toml``
  carrying the two-line managed header;
* drift detection flips ``status`` to STALE when the catalog source of
  a generated artefact changes;
* ``remove`` / ``install --prune`` clean only ai-dotfiles-managed Codex
  files — a user-authored file in the same directory survives.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_dotfiles.commands.install import install
from ai_dotfiles.commands.remove import remove
from ai_dotfiles.commands.status import status
from ai_dotfiles.core.codex_install import MANAGED_BY_HEADER

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


# ── Catalog / manifest helpers ────────────────────────────────────────────

_SKILL_MD = """\
---
name: {name}
description: First sentence here. Trailing trigger phrase to be trimmed.
---

# {name}

Skill body.
"""

_AGENT_MD = """\
---
name: {name}
description: An example {name} agent.
model: opus
---

# {name}

Agent body.
"""


def _write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_skill(catalog: Path, name: str, *, support: bool = False) -> Path:
    """Create a standalone catalog skill; optionally with support files."""
    skill = catalog / "skills" / name
    skill.mkdir(parents=True, exist_ok=True)
    _write(skill / "SKILL.md", _SKILL_MD.format(name=name))
    if support:
        _write(skill / "scripts" / "run.sh", "echo hi\n")
        _write(skill / "references" / "notes.md", "notes\n")
    return skill


def _make_agent(catalog: Path, name: str) -> Path:
    path = catalog / "agents" / f"{name}.md"
    _write(path, _AGENT_MD.format(name=name))
    return path


def _write_manifest(
    path: Path, packages: list[str], *, targets: list[str] | None = None
) -> None:
    data: dict[str, object] = {"packages": packages}
    if targets is not None:
        data["targets"] = targets
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _run(command: object, project: Path, *args: str) -> tuple[int, str, str]:
    runner = CliRunner()
    cwd = os.getcwd()
    os.chdir(project)
    try:
        result = runner.invoke(command, list(args), catch_exceptions=False)  # type: ignore[arg-type]
    finally:
        os.chdir(cwd)
    return result.exit_code, result.stdout, result.stderr


# ── Skill render + symlink ────────────────────────────────────────────────


def test_codex_skill_is_real_dir_with_generated_skill_md(
    project: Path, catalog: Path
) -> None:
    """A Codex skill is a real directory with a generated, managed SKILL.md."""
    _make_skill(catalog, "commit", support=True)
    _write_manifest(project / "ai-dotfiles.json", ["skill:commit"], targets=["codex"])

    code, _, _ = _run(install, project)
    assert code == 0

    skill_dir = project / ".agents" / "skills" / "commit"
    assert skill_dir.is_dir() and not skill_dir.is_symlink()

    skill_md = skill_dir / "SKILL.md"
    assert skill_md.is_file() and not skill_md.is_symlink()
    lines = skill_md.read_text(encoding="utf-8").splitlines()
    assert lines[0] == MANAGED_BY_HEADER
    assert lines[1].startswith("# source-sha256: ")
    # ADR ai-1-4: the description is trimmed to its first sentence.
    body = skill_md.read_text(encoding="utf-8")
    assert 'description: "First sentence here."' in body


def test_codex_skill_support_files_are_symlinked_into_catalog(
    project: Path, catalog: Path
) -> None:
    """Support files/dirs of a Codex skill are symlinks into the catalog."""
    source = _make_skill(catalog, "commit", support=True)
    _write_manifest(project / "ai-dotfiles.json", ["skill:commit"], targets=["codex"])

    code, _, _ = _run(install, project)
    assert code == 0

    skill_dir = project / ".agents" / "skills" / "commit"
    assert (skill_dir / "scripts").is_symlink()
    assert (skill_dir / "references").is_symlink()
    assert (skill_dir / "scripts").resolve() == (source / "scripts").resolve()
    # The symlink resolves to live catalog content.
    assert (skill_dir / "scripts" / "run.sh").read_text() == "echo hi\n"


# ── Agent render ──────────────────────────────────────────────────────────


def test_codex_agent_is_generated_toml_with_managed_header(
    project: Path, catalog: Path
) -> None:
    """A Codex agent is a generated, committed .toml with the managed header."""
    _make_agent(catalog, "researcher")
    _write_manifest(
        project / "ai-dotfiles.json", ["agent:researcher"], targets=["codex"]
    )

    code, _, _ = _run(install, project)
    assert code == 0

    toml_path = project / ".codex" / "agents" / "researcher.toml"
    assert toml_path.is_file() and not toml_path.is_symlink()
    lines = toml_path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == MANAGED_BY_HEADER
    assert lines[1].startswith("# source-sha256: ")
    # Frontmatter keys carried into TOML.
    body = toml_path.read_text(encoding="utf-8")
    assert 'name = "researcher"' in body
    assert "developer_instructions" in body


def test_codex_domain_expands_skills_and_agents(project: Path, catalog: Path) -> None:
    """A domain renders its skill + agent members for the Codex target."""
    domain = catalog / "python"
    skill = domain / "skills" / "py-lint"
    skill.mkdir(parents=True)
    _write(skill / "SKILL.md", _SKILL_MD.format(name="py-lint"))
    _write(domain / "agents" / "py-debug.md", _AGENT_MD.format(name="py-debug"))
    _write_manifest(project / "ai-dotfiles.json", ["@python"], targets=["codex"])

    code, _, _ = _run(install, project)
    assert code == 0

    assert (project / ".agents" / "skills" / "py-lint" / "SKILL.md").is_file()
    assert (project / ".codex" / "agents" / "py-debug.toml").is_file()


# ── Drift detection ───────────────────────────────────────────────────────


def test_status_reports_ok_when_codex_artefacts_fresh(
    project: Path, catalog: Path
) -> None:
    _make_skill(catalog, "commit")
    _make_agent(catalog, "researcher")
    _write_manifest(
        project / "ai-dotfiles.json",
        ["skill:commit", "agent:researcher"],
        targets=["codex"],
    )
    assert _run(install, project)[0] == 0

    code, out, _ = _run(status, project)
    assert code == 0
    assert "Codex target" in out
    assert "STALE" not in out


def test_status_flips_to_stale_when_catalog_source_changes(
    project: Path, catalog: Path
) -> None:
    """Editing the catalog source of a generated agent makes status STALE."""
    agent_md = _make_agent(catalog, "researcher")
    _write_manifest(
        project / "ai-dotfiles.json", ["agent:researcher"], targets=["codex"]
    )
    assert _run(install, project)[0] == 0
    assert "STALE" not in _run(status, project)[1]

    # Mutate the catalog source — the recorded source-sha256 no longer matches.
    agent_md.write_text(
        _AGENT_MD.format(name="researcher") + "\nAn extra paragraph.\n",
        encoding="utf-8",
    )

    code, out, _ = _run(status, project)
    assert code == 1
    assert "STALE" in out


def test_status_treats_garbled_header_as_stale(project: Path, catalog: Path) -> None:
    """A generated file with a corrupted source-sha256 header reads as stale."""
    _make_agent(catalog, "researcher")
    _write_manifest(
        project / "ai-dotfiles.json", ["agent:researcher"], targets=["codex"]
    )
    assert _run(install, project)[0] == 0

    toml_path = project / ".codex" / "agents" / "researcher.toml"
    text = toml_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    # Corrupt the second header line (the source-sha256 marker).
    lines[1] = "# source-sha256: not-a-real-hash"
    toml_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    code, out, _ = _run(status, project)
    assert code == 1
    assert "STALE" in out


# ── remove / prune: only managed files are touched ────────────────────────


def test_remove_cleans_managed_codex_artefacts(project: Path, catalog: Path) -> None:
    _make_skill(catalog, "commit", support=True)
    _make_agent(catalog, "researcher")
    _write_manifest(
        project / "ai-dotfiles.json",
        ["skill:commit", "agent:researcher"],
        targets=["codex"],
    )
    assert _run(install, project)[0] == 0
    skill_dir = project / ".agents" / "skills" / "commit"
    toml_path = project / ".codex" / "agents" / "researcher.toml"
    assert skill_dir.is_dir() and toml_path.is_file()

    code, _, _ = _run(remove, project, "skill:commit", "agent:researcher")
    assert code == 0
    assert not skill_dir.exists()
    assert not toml_path.exists()
    # The catalog source survives — removal only dropped the generated tree.
    assert (catalog / "skills" / "commit" / "SKILL.md").is_file()


def test_remove_preserves_user_authored_codex_files(
    project: Path, catalog: Path
) -> None:
    """A hand-written .toml / skill dir with no managed header is left alone."""
    _make_skill(catalog, "commit")
    _make_agent(catalog, "researcher")
    _write_manifest(
        project / "ai-dotfiles.json",
        ["skill:commit", "agent:researcher"],
        targets=["codex"],
    )
    assert _run(install, project)[0] == 0

    # A user-authored agent .toml and skill dir, neither managed by ai-dotfiles.
    user_toml = project / ".codex" / "agents" / "my-own.toml"
    _write(user_toml, 'name = "my-own"\n')
    user_skill = project / ".agents" / "skills" / "my-own"
    _write(user_skill / "SKILL.md", "---\nname: my-own\n---\n\nbody\n")

    code, _, _ = _run(remove, project, "skill:commit", "agent:researcher")
    assert code == 0

    # Managed artefacts gone, user-authored ones untouched.
    assert not (project / ".codex" / "agents" / "researcher.toml").exists()
    assert not (project / ".agents" / "skills" / "commit").exists()
    assert user_toml.is_file()
    assert user_toml.read_text(encoding="utf-8") == 'name = "my-own"\n'
    assert (user_skill / "SKILL.md").is_file()


def test_install_prune_drops_orphaned_managed_codex_files(
    project: Path, catalog: Path
) -> None:
    """install --prune removes managed Codex files no longer in the manifest."""
    _make_skill(catalog, "commit")
    _make_agent(catalog, "researcher")
    _write_manifest(
        project / "ai-dotfiles.json",
        ["skill:commit", "agent:researcher"],
        targets=["codex"],
    )
    assert _run(install, project)[0] == 0
    assert (project / ".codex" / "agents" / "researcher.toml").is_file()

    # Drop the agent from the manifest, then prune.
    _write_manifest(project / "ai-dotfiles.json", ["skill:commit"], targets=["codex"])
    code, out, _ = _run(install, project, "--prune")
    assert code == 0
    assert "pruned Codex agents/researcher.toml" in out
    assert not (project / ".codex" / "agents" / "researcher.toml").exists()
    # The still-listed skill is kept.
    assert (project / ".agents" / "skills" / "commit").is_dir()


def test_install_prune_preserves_user_authored_codex_files(
    project: Path, catalog: Path
) -> None:
    """install --prune never touches user-authored (unmanaged) Codex files."""
    _make_skill(catalog, "commit")
    _write_manifest(project / "ai-dotfiles.json", ["skill:commit"], targets=["codex"])
    assert _run(install, project)[0] == 0

    # User-authored, unmanaged artefacts that are NOT in the manifest.
    user_toml = project / ".codex" / "agents" / "hand-rolled.toml"
    _write(user_toml, 'name = "hand-rolled"\n')
    user_skill = project / ".agents" / "skills" / "hand-rolled"
    _write(user_skill / "SKILL.md", "---\nname: hand-rolled\n---\n\nbody\n")

    code, _, _ = _run(install, project, "--prune")
    assert code == 0
    assert user_toml.is_file()
    assert (user_skill / "SKILL.md").is_file()
