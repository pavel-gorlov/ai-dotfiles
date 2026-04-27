"""E2E tests for ``ai-dotfiles list``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_dotfiles.commands.list_cmd import list_cmd

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
def project(home: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    proj = home / "proj"
    proj.mkdir()
    (proj / ".git").mkdir()
    monkeypatch.chdir(proj)
    return proj


def _write_manifest(path: Path, packages: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"packages": packages}, indent=2) + "\n")


# ── list (project) ────────────────────────────────────────────────────────


def test_list_project_with_packages(storage: Path, project: Path) -> None:
    _write_manifest(
        project / "ai-dotfiles.json",
        [
            "@python",
            "@telegram-api",
            "skill:code-review",
            "skill:git-workflow",
            "agent:researcher",
            "rule:security",
        ],
    )

    result = CliRunner().invoke(list_cmd, [])

    assert result.exit_code == 0, result.output
    out = result.output
    assert "Project (ai-dotfiles.json):" in out
    assert "Global" in out  # header appears even when global.json is missing
    assert "Domains:" in out
    assert "@python" in out
    assert "@telegram-api" in out
    assert "Skills:" in out
    assert "skill:code-review" in out
    assert "skill:git-workflow" in out
    assert "Agents:" in out
    assert "agent:researcher" in out
    assert "Rules:" in out
    assert "rule:security" in out


def test_list_shows_project_and_global(storage: Path, project: Path) -> None:
    _write_manifest(project / "ai-dotfiles.json", ["@python", "skill:code-review"])
    _write_manifest(storage / "global.json", ["@devops", "agent:researcher"])

    result = CliRunner().invoke(list_cmd, [])

    assert result.exit_code == 0, result.output
    out = result.output
    # Both scope headers present
    assert "Project (ai-dotfiles.json):" in out
    assert "Global (global.json):" in out
    # Project content
    assert "@python" in out
    assert "skill:code-review" in out
    # Global content
    assert "@devops" in out
    assert "agent:researcher" in out
    # Project block comes before Global
    assert out.index("Project") < out.index("Global")


def test_list_project_empty(storage: Path, project: Path) -> None:
    _write_manifest(project / "ai-dotfiles.json", [])

    result = CliRunner().invoke(list_cmd, [])

    assert result.exit_code == 0, result.output
    # Project section prints the empty note (and Global note since it's missing too)
    assert "No packages installed." in result.output


def test_list_project_missing_manifest_still_shows_global(
    storage: Path, project: Path
) -> None:
    """No project manifest → friendly note, no error; global section still shown."""
    _write_manifest(storage / "global.json", ["skill:code-review"])

    result = CliRunner().invoke(list_cmd, [])

    assert result.exit_code == 0, result.output
    out = result.output
    assert "Project:" in out
    assert "No ai-dotfiles.json" in out
    assert "Global (global.json):" in out
    assert "skill:code-review" in out


# ── list -g ───────────────────────────────────────────────────────────────


def test_list_global(storage: Path) -> None:
    _write_manifest(
        storage / "global.json",
        ["@python", "skill:code-review", "agent:researcher"],
    )

    result = CliRunner().invoke(list_cmd, ["-g"])

    assert result.exit_code == 0, result.output
    out = result.output
    assert "Global (global.json):" in out
    assert "@python" in out
    assert "skill:code-review" in out
    assert "agent:researcher" in out
    # With -g only the Global section is shown; no Project header
    assert "Project" not in out


# ── list --available ──────────────────────────────────────────────────────


def test_list_available_domains(storage: Path) -> None:
    catalog = storage / "catalog"
    (catalog / "python").mkdir()
    (catalog / "go").mkdir()

    result = CliRunner().invoke(list_cmd, ["--available"])

    assert result.exit_code == 0, result.output
    out = result.output
    assert "Available in catalog:" in out
    assert "Domains:" in out
    assert "@python" in out
    assert "@go" in out


def test_list_available_standalone(storage: Path) -> None:
    catalog = storage / "catalog"
    (catalog / "skills" / "code-review").mkdir(parents=True)
    (catalog / "skills" / "code-review" / "SKILL.md").write_text("# cr\n")
    (catalog / "skills" / "git-workflow").mkdir(parents=True)
    (catalog / "skills" / "git-workflow" / "SKILL.md").write_text("# gw\n")
    (catalog / "agents").mkdir(parents=True)
    (catalog / "agents" / "researcher.md").write_text("# r\n")
    (catalog / "agents" / "reviewer.md").write_text("# rev\n")
    (catalog / "rules").mkdir(parents=True)
    (catalog / "rules" / "security.md").write_text("# sec\n")

    result = CliRunner().invoke(list_cmd, ["--available"])

    assert result.exit_code == 0, result.output
    out = result.output
    assert "skill:code-review" in out
    assert "skill:git-workflow" in out
    assert "agent:researcher" in out
    assert "agent:reviewer" in out
    assert "rule:security" in out


def test_list_available_skips_example(storage: Path) -> None:
    catalog = storage / "catalog"
    (catalog / "python").mkdir()
    (catalog / "_example").mkdir()
    # Reserved subdirs must not be listed as domains either.
    (catalog / "skills").mkdir()
    (catalog / "agents").mkdir()
    (catalog / "rules").mkdir()

    result = CliRunner().invoke(list_cmd, ["--available"])

    assert result.exit_code == 0, result.output
    out = result.output
    assert "@python" in out
    assert "@_example" not in out
    # The reserved subdirs should not appear as domain entries.
    assert "@skills" not in out
    assert "@agents" not in out
    assert "@rules" not in out


# ── install/dep markers ───────────────────────────────────────────────────


def _make_domain(catalog: Path, name: str, *, depends: list[str] | None = None) -> None:
    root = catalog / name
    root.mkdir(parents=True, exist_ok=True)
    meta: dict[str, object] = {"name": name}
    if depends is not None:
        meta["depends"] = depends
    (root / "domain.json").write_text(json.dumps(meta), encoding="utf-8")


def test_list_available_marks_global_with_g_suffix(
    storage: Path, project: Path
) -> None:
    catalog = storage / "catalog"
    _make_domain(catalog, "python")
    _write_manifest(storage / "global.json", ["@python"])

    result = CliRunner().invoke(list_cmd, ["--available"], color=True)

    assert result.exit_code == 0, result.output
    assert "@python (g)" in result.output
    # Green ANSI prefix (32) precedes the marker line.
    assert "\x1b[32m    @python (g)" in result.output


def test_list_available_marks_dependency_yellow_with_parents(
    storage: Path, project: Path
) -> None:
    """A package pulled in transitively shows yellow + (parent) annotation."""
    catalog = storage / "catalog"
    _make_domain(catalog, "python")
    _make_domain(catalog, "python-backend", depends=["@python"])
    _write_manifest(storage / "global.json", ["@python", "@python-backend"])

    result = CliRunner().invoke(list_cmd, ["--available"], color=True)

    assert result.exit_code == 0, result.output
    out = result.output
    # @python is a dep of @python-backend → yellow with the parent shown.
    assert "@python (g) (@python-backend)" in out
    assert "\x1b[33m    @python (g) (@python-backend)" in out
    # The parent itself is direct → green, no annotation.
    assert "\x1b[32m    @python-backend (g)" in out


def test_list_available_walks_transitive_chain(storage: Path, project: Path) -> None:
    """A → B → C: C must show both B and A as dependents (multi-level walk)."""
    catalog = storage / "catalog"
    _make_domain(catalog, "c")
    _make_domain(catalog, "b", depends=["@c"])
    _make_domain(catalog, "a", depends=["@b"])
    _write_manifest(storage / "global.json", ["@a", "@b", "@c"])

    result = CliRunner().invoke(list_cmd, ["--available"], color=True)

    assert result.exit_code == 0, result.output
    out = result.output
    # @c is a transitive dep of both @a and @b.
    assert "@c (g) (@a @b)" in out or "@c (g) (@b @a)" in out
    assert "\x1b[33m    @c (g)" in out


def test_list_available_uninstalled_no_marker(storage: Path, project: Path) -> None:
    catalog = storage / "catalog"
    _make_domain(catalog, "python")

    # No color flag — assert plain text, no fg color escape codes.
    result = CliRunner().invoke(list_cmd, ["--available"])

    assert result.exit_code == 0, result.output
    assert "    @python\n" in result.output
    assert "(g)" not in result.output
    assert "\x1b[" not in result.output


def test_list_project_block_cross_references_global(
    storage: Path, project: Path
) -> None:
    """In `list`, the project block flags entries that are also in global."""
    catalog = storage / "catalog"
    _make_domain(catalog, "python")
    _make_domain(catalog, "ruby")
    _write_manifest(project / "ai-dotfiles.json", ["@python", "@ruby"])
    _write_manifest(storage / "global.json", ["@python"])

    result = CliRunner().invoke(list_cmd, [])

    assert result.exit_code == 0, result.output
    out = result.output
    # Project entry that is also global gets the (g) suffix.
    assert "    @python (g)" in out
    # Project entry not in global has no suffix on its own line.
    project_block, _, global_block = out.partition("Global (global.json):")
    assert "    @ruby\n" in project_block
    # Global block lists @python without a redundant (g).
    assert "    @python\n" in global_block
    assert "@python (g)" not in global_block


def test_list_global_no_g_suffix_inside_global_block(storage: Path) -> None:
    """`list -g` lines never carry (g) — every entry is global already."""
    catalog = storage / "catalog"
    _make_domain(catalog, "python")
    _write_manifest(storage / "global.json", ["@python"])

    result = CliRunner().invoke(list_cmd, ["-g"], color=True)

    assert result.exit_code == 0, result.output
    assert "@python" in result.output
    assert "(g)" not in result.output
