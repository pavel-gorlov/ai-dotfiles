"""E2E tests for the Codex CLI target via the full ``ai-dotfiles`` CLI.

Drives ``install`` / ``add`` / ``remove`` through the top-level click
group with ``CliRunner``, covering the manifest ``targets`` field
(ADR ai-1-3):

* ``targets: ["codex"]`` — Codex-only: writes the Codex trees and *no*
  ``.claude/``;
* ``targets: ["claude", "codex"]`` — multi-target: both trees written;
* a manifest with no ``targets`` field — the regression guard: install
  behaves byte-identically to the pre-Codex Claude-only behaviour.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_dotfiles.cli import cli

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


def _make_skill(catalog: Path, name: str) -> Path:
    skill = catalog / "skills" / name
    skill.mkdir(parents=True, exist_ok=True)
    _write(skill / "SKILL.md", _SKILL_MD.format(name=name))
    return skill


def _make_agent(catalog: Path, name: str) -> Path:
    path = catalog / "agents" / f"{name}.md"
    _write(path, _AGENT_MD.format(name=name))
    return path


# Rule fixtures, one per RuleClass (epic ai-1 Phase 2 / ADR ai-1-2).
_RULE_ALWAYS_ON = "---\nalways_on: true\n---\n\n# Principles\n\nAlways-loaded.\n"
_RULE_PATH_SCOPED = (
    "---\npaths:\n  - src/api\n---\n\n# API rule\n\nScoped to the API.\n"
)
_RULE_DESC_ONLY = "# Commit style\n\nUse Conventional Commits for every commit.\n"


def _make_rule(catalog: Path, name: str, text: str) -> Path:
    path = catalog / "rules" / f"{name}.md"
    _write(path, text)
    return path


def _write_manifest(
    path: Path, packages: list[str], *, targets: list[str] | None = None
) -> None:
    data: dict[str, object] = {"packages": packages}
    if targets is not None:
        data["targets"] = targets
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _run(project: Path, *args: str) -> tuple[int, str, str]:
    """Invoke the full ``ai-dotfiles`` CLI with ``project`` as cwd."""
    runner = CliRunner()
    cwd = os.getcwd()
    os.chdir(project)
    try:
        result = runner.invoke(cli, list(args), catch_exceptions=False)
    finally:
        os.chdir(cwd)
    return result.exit_code, result.stdout, result.stderr


# ── install: codex-only target ────────────────────────────────────────────


def test_install_codex_only_writes_codex_trees(project: Path, catalog: Path) -> None:
    _make_skill(catalog, "commit")
    _make_agent(catalog, "researcher")
    _write_manifest(
        project / "ai-dotfiles.json",
        ["skill:commit", "agent:researcher"],
        targets=["codex"],
    )

    code, out, _ = _run(project, "install")
    assert code == 0, out
    assert (project / ".agents" / "skills" / "commit" / "SKILL.md").is_file()
    assert (project / ".codex" / "agents" / "researcher.toml").is_file()


def test_install_codex_only_produces_no_claude_dir(
    project: Path, catalog: Path
) -> None:
    """A codex-only manifest must not create any ``.claude/`` directory."""
    _make_skill(catalog, "commit")
    _write_manifest(project / "ai-dotfiles.json", ["skill:commit"], targets=["codex"])

    code, _, _ = _run(project, "install")
    assert code == 0
    assert not (project / ".claude").exists()


# ── install: multi-target claude + codex ──────────────────────────────────


def test_install_multi_target_writes_both_trees(project: Path, catalog: Path) -> None:
    """``targets: [claude, codex]`` writes the Claude *and* Codex trees."""
    _make_skill(catalog, "commit")
    _make_agent(catalog, "researcher")
    _write_manifest(
        project / "ai-dotfiles.json",
        ["skill:commit", "agent:researcher"],
        targets=["claude", "codex"],
    )

    code, out, _ = _run(project, "install")
    assert code == 0, out

    # Claude tree — symlinks into the catalog.
    assert (project / ".claude" / "skills" / "commit").is_symlink()
    assert (project / ".claude" / "agents" / "researcher.md").is_symlink()
    # Codex tree — generated artefacts.
    assert (project / ".agents" / "skills" / "commit" / "SKILL.md").is_file()
    assert (project / ".codex" / "agents" / "researcher.toml").is_file()


# ── Regression guard: no `targets` field ──────────────────────────────────


def test_install_no_targets_field_is_claude_only(project: Path, catalog: Path) -> None:
    """A manifest with no ``targets`` field installs exactly as before.

    ADR ai-1-3: an absent ``targets`` key resolves to ``["claude"]`` —
    no Codex artefacts, only the Claude symlink tree, byte-identical to
    pre-change behaviour.
    """
    _make_skill(catalog, "commit")
    _make_agent(catalog, "researcher")
    # Manifest written WITHOUT a `targets` field.
    _write_manifest(project / "ai-dotfiles.json", ["skill:commit", "agent:researcher"])

    code, _, _ = _run(project, "install")
    assert code == 0

    # Claude tree present.
    assert (project / ".claude" / "skills" / "commit").is_symlink()
    assert (project / ".claude" / "agents" / "researcher.md").is_symlink()
    # No Codex trees at all.
    assert not (project / ".agents").exists()
    assert not (project / ".codex").exists()


def test_install_no_targets_matches_explicit_claude(
    project: Path, catalog: Path
) -> None:
    """Absent ``targets`` and explicit ``["claude"]`` produce identical trees."""
    _make_skill(catalog, "commit")

    # Project A: no targets field.
    proj_a = project
    _write_manifest(proj_a / "ai-dotfiles.json", ["skill:commit"])
    assert _run(proj_a, "install")[0] == 0

    # Project B: explicit ["claude"].
    proj_b = project.parent / "proj-b"
    proj_b.mkdir()
    (proj_b / ".git").mkdir()
    _write_manifest(proj_b / "ai-dotfiles.json", ["skill:commit"], targets=["claude"])
    assert _run(proj_b, "install")[0] == 0

    link_a = os.readlink(proj_a / ".claude" / "skills" / "commit")
    link_b = os.readlink(proj_b / ".claude" / "skills" / "commit")
    assert link_a == link_b
    # Neither produced a Codex tree.
    assert not (proj_a / ".codex").exists()
    assert not (proj_b / ".codex").exists()


# ── add: codex and multi-target ───────────────────────────────────────────


def test_add_codex_only_links_only_codex(project: Path, catalog: Path) -> None:
    _make_skill(catalog, "commit")
    _write_manifest(project / "ai-dotfiles.json", [], targets=["codex"])

    code, out, _ = _run(project, "add", "skill:commit")
    assert code == 0, out

    assert json.loads((project / "ai-dotfiles.json").read_text())["packages"] == [
        "skill:commit"
    ]
    assert (project / ".agents" / "skills" / "commit" / "SKILL.md").is_file()
    assert not (project / ".claude" / "skills" / "commit").exists()


def test_add_multi_target_links_both(project: Path, catalog: Path) -> None:
    _make_agent(catalog, "researcher")
    _write_manifest(project / "ai-dotfiles.json", [], targets=["claude", "codex"])

    code, out, _ = _run(project, "add", "agent:researcher")
    assert code == 0, out
    assert (project / ".claude" / "agents" / "researcher.md").is_symlink()
    assert (project / ".codex" / "agents" / "researcher.toml").is_file()


def test_add_touches_only_that_elements_codex_artefact(
    project: Path, catalog: Path
) -> None:
    """Adding one element leaves an unrelated installed element untouched."""
    _make_skill(catalog, "commit")
    _make_agent(catalog, "researcher")
    _write_manifest(project / "ai-dotfiles.json", ["skill:commit"], targets=["codex"])
    assert _run(project, "install")[0] == 0
    skill_md = project / ".agents" / "skills" / "commit" / "SKILL.md"
    before = skill_md.read_text(encoding="utf-8")

    code, _, _ = _run(project, "add", "agent:researcher")
    assert code == 0
    # The new agent appeared, the pre-existing skill is unchanged.
    assert (project / ".codex" / "agents" / "researcher.toml").is_file()
    assert skill_md.read_text(encoding="utf-8") == before


# ── add: codex config.toml (settings + MCP) (ai-17) ───────────────────────


def _make_config_domain(
    catalog: Path,
    name: str,
    *,
    servers: dict[str, object],
    settings: dict[str, object],
) -> None:
    """Create a catalog domain with settings + mcp fragments."""
    domain = catalog / name
    domain.mkdir(parents=True, exist_ok=True)
    _write(
        domain / "domain.json",
        json.dumps({"name": name, "description": f"{name} domain"}) + "\n",
    )
    _write(domain / "settings.fragment.json", json.dumps(settings) + "\n")
    _write(
        domain / "mcp.fragment.json",
        json.dumps({"mcpServers": servers}) + "\n",
    )


def _read_codex_config(project: Path) -> dict[str, object]:
    import tomllib

    with (project / ".codex" / "config.toml").open("rb") as handle:
        return tomllib.load(handle)


def test_cli_add_writes_config_toml(project: Path, catalog: Path) -> None:
    """`ai-dotfiles add @domain` writes settings + MCP into config.toml."""
    _make_config_domain(
        catalog,
        "tooling",
        servers={"fs": {"command": "fs-server"}},
        settings={"permissions": {"allow": ["Bash(git diff:*)"]}},
    )
    _write_manifest(project / "ai-dotfiles.json", [], targets=["codex"])

    code, out, _ = _run(project, "add", "@tooling")
    assert code == 0, out

    parsed = _read_codex_config(project)
    assert parsed["ai_dotfiles"]["permissions"]["allow"] == ["Bash(git diff:*)"]
    assert parsed["mcp_servers"]["fs"] == {"command": "fs-server"}


def test_cli_add_second_domain_preserves_first_config(
    project: Path, catalog: Path
) -> None:
    """Adding a second domain keeps the first domain's config.toml regions."""
    _make_config_domain(
        catalog,
        "first",
        servers={"fs": {"command": "fs-server"}},
        settings={"permissions": {"allow": ["Bash(git diff:*)"]}},
    )
    _make_config_domain(
        catalog,
        "second",
        servers={"net": {"command": "net-server"}},
        settings={"permissions": {"allow": ["Bash(curl:*)"]}},
    )
    _write_manifest(project / "ai-dotfiles.json", [], targets=["codex"])

    assert _run(project, "add", "@first")[0] == 0
    assert _run(project, "add", "@second")[0] == 0

    parsed = _read_codex_config(project)
    allow = parsed["ai_dotfiles"]["permissions"]["allow"]
    assert "Bash(git diff:*)" in allow and "Bash(curl:*)" in allow
    assert parsed["mcp_servers"]["fs"] == {"command": "fs-server"}
    assert parsed["mcp_servers"]["net"] == {"command": "net-server"}


# ── remove: codex and multi-target ────────────────────────────────────────


def test_remove_codex_only_unlinks_codex(project: Path, catalog: Path) -> None:
    _make_skill(catalog, "commit")
    _write_manifest(project / "ai-dotfiles.json", ["skill:commit"], targets=["codex"])
    assert _run(project, "install")[0] == 0
    assert (project / ".agents" / "skills" / "commit").is_dir()

    code, out, _ = _run(project, "remove", "skill:commit")
    assert code == 0, out
    assert json.loads((project / "ai-dotfiles.json").read_text())["packages"] == []
    assert not (project / ".agents" / "skills" / "commit").exists()


def test_remove_multi_target_unlinks_both(project: Path, catalog: Path) -> None:
    _make_agent(catalog, "researcher")
    _write_manifest(
        project / "ai-dotfiles.json",
        ["agent:researcher"],
        targets=["claude", "codex"],
    )
    assert _run(project, "install")[0] == 0
    assert (project / ".claude" / "agents" / "researcher.md").is_symlink()
    assert (project / ".codex" / "agents" / "researcher.toml").is_file()

    code, _, _ = _run(project, "remove", "agent:researcher")
    assert code == 0
    assert not (project / ".claude" / "agents" / "researcher.md").exists()
    assert not (project / ".codex" / "agents" / "researcher.toml").exists()


def test_remove_touches_only_that_elements_codex_artefact(
    project: Path, catalog: Path
) -> None:
    """Removing one element leaves a still-installed element's artefact intact."""
    _make_skill(catalog, "commit")
    _make_agent(catalog, "researcher")
    _write_manifest(
        project / "ai-dotfiles.json",
        ["skill:commit", "agent:researcher"],
        targets=["codex"],
    )
    assert _run(project, "install")[0] == 0

    code, _, _ = _run(project, "remove", "agent:researcher")
    assert code == 0
    # The removed agent is gone; the untouched skill remains.
    assert not (project / ".codex" / "agents" / "researcher.toml").exists()
    assert (project / ".agents" / "skills" / "commit" / "SKILL.md").is_file()


# ── Rules through the full CLI (Phase 2, ADR ai-1-2) ──────────────────────


def test_cli_install_always_on_rule_writes_root_agents_md(
    project: Path, catalog: Path
) -> None:
    """``ai-dotfiles install`` lands an always-on rule in the root AGENTS.md."""
    _make_rule(catalog, "principles", _RULE_ALWAYS_ON)
    _write_manifest(
        project / "ai-dotfiles.json", ["rule:principles"], targets=["codex"]
    )

    code, out, _ = _run(project, "install")
    assert code == 0, out
    assert "<!-- ai-dotfiles:rule:principles START -->" in (
        project / "AGENTS.md"
    ).read_text(encoding="utf-8")


def test_cli_install_path_scoped_rule_writes_nested_agents_md(
    project: Path, catalog: Path
) -> None:
    """A path-scoped rule lands in <dir>/AGENTS.md, not the project root."""
    _make_rule(catalog, "api", _RULE_PATH_SCOPED)
    _write_manifest(project / "ai-dotfiles.json", ["rule:api"], targets=["codex"])

    code, out, _ = _run(project, "install")
    assert code == 0, out
    assert (project / "src" / "api" / "AGENTS.md").is_file()
    assert not (project / "AGENTS.md").exists()


def test_cli_install_description_only_rule_is_codex_only_skill(
    project: Path, catalog: Path
) -> None:
    """A description-only rule renders as a Codex-only ``rule-<name>`` skill."""
    _make_rule(catalog, "commit-style", _RULE_DESC_ONLY)
    _write_manifest(
        project / "ai-dotfiles.json",
        ["rule:commit-style"],
        targets=["claude", "codex"],
    )

    code, out, _ = _run(project, "install")
    assert code == 0, out
    assert (project / ".agents" / "skills" / "rule-commit-style" / "SKILL.md").is_file()
    # ADR ai-1-2: never installed for the Claude target.
    assert not (project / ".claude" / "skills" / "rule-commit-style").exists()


def test_cli_install_no_rule_skip_message(project: Path, catalog: Path) -> None:
    """The Phase-1 'rules skipped for the Codex target' message is gone."""
    _make_rule(catalog, "principles", _RULE_ALWAYS_ON)
    _write_manifest(
        project / "ai-dotfiles.json", ["rule:principles"], targets=["codex"]
    )

    code, out, _ = _run(project, "install")
    assert code == 0
    assert "rules have no" not in out
    assert "skipped for the Codex target" not in out


def test_cli_add_then_remove_rule_round_trips(project: Path, catalog: Path) -> None:
    """``add`` writes a rule's AGENTS.md block; ``remove`` strips it again."""
    _make_rule(catalog, "principles", _RULE_ALWAYS_ON)
    _write_manifest(project / "ai-dotfiles.json", [], targets=["codex"])

    assert _run(project, "add", "rule:principles")[0] == 0
    assert "ai-dotfiles:rule:principles" in (project / "AGENTS.md").read_text(
        encoding="utf-8"
    )

    assert _run(project, "remove", "rule:principles")[0] == 0
    # The AGENTS.md held only the managed block — it is removed entirely.
    assert not (project / "AGENTS.md").exists()


def test_cli_status_reports_rule_classes(project: Path, catalog: Path) -> None:
    """``status`` shows always-on / path-scoped / description-only rules OK."""
    _make_rule(catalog, "principles", _RULE_ALWAYS_ON)
    _make_rule(catalog, "api", _RULE_PATH_SCOPED)
    _make_rule(catalog, "commit-style", _RULE_DESC_ONLY)
    _write_manifest(
        project / "ai-dotfiles.json",
        ["rule:principles", "rule:api", "rule:commit-style"],
        targets=["codex"],
    )
    assert _run(project, "install")[0] == 0

    code, out, _ = _run(project, "status")
    assert code == 0, out
    assert "rules/principles" in out
    assert "rules/api" in out
    assert "skills/rule-commit-style" in out
    assert "NOT INSTALLED" not in out
