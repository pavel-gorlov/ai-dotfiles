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


def _make_mcp_domain(
    catalog: Path,
    name: str,
    servers: dict[str, object],
    *,
    settings: dict[str, object] | None = None,
) -> Path:
    """Create a catalog domain with ``mcp.fragment.json`` (+ optional settings)."""
    domain = catalog / name
    domain.mkdir(parents=True, exist_ok=True)
    _write(
        domain / "domain.json",
        json.dumps({"name": name, "description": f"{name} domain"}) + "\n",
    )
    _write(
        domain / "mcp.fragment.json",
        json.dumps({"mcpServers": servers}) + "\n",
    )
    if settings is not None:
        _write(domain / "settings.fragment.json", json.dumps(settings) + "\n")
    return domain


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


# ── Rules: AGENTS.md assembly + synthetic skills (Phase 2, ADR ai-1-2) ────


def test_always_on_rule_lands_in_root_agents_md(project: Path, catalog: Path) -> None:
    """An always-on rule writes a managed block to the project-root AGENTS.md."""
    _make_rule(catalog, "principles", _RULE_ALWAYS_ON)
    _write_manifest(
        project / "ai-dotfiles.json", ["rule:principles"], targets=["codex"]
    )

    code, out, _ = _run(install, project)
    assert code == 0, out

    agents_md = project / "AGENTS.md"
    assert agents_md.is_file()
    text = agents_md.read_text(encoding="utf-8")
    assert "<!-- ai-dotfiles:rule:principles START -->" in text
    assert "Always-loaded." in text
    # No skip message for rules any more.
    assert "rules have no" not in out


def test_path_scoped_rule_lands_in_nested_agents_md(
    project: Path, catalog: Path
) -> None:
    """A path-scoped rule writes a managed block to each <dir>/AGENTS.md."""
    _make_rule(catalog, "api", _RULE_PATH_SCOPED)
    _write_manifest(project / "ai-dotfiles.json", ["rule:api"], targets=["codex"])

    code, out, _ = _run(install, project)
    assert code == 0, out

    nested = project / "src" / "api" / "AGENTS.md"
    assert nested.is_file()
    assert "<!-- ai-dotfiles:rule:api START -->" in nested.read_text(encoding="utf-8")
    # The root AGENTS.md is NOT written for a path-scoped rule.
    assert not (project / "AGENTS.md").exists()


def test_description_only_rule_renders_codex_only_skill(
    project: Path, catalog: Path
) -> None:
    """A description-only rule renders as a Codex-only ``rule-<name>`` skill."""
    _make_rule(catalog, "commit-style", _RULE_DESC_ONLY)
    _write_manifest(
        project / "ai-dotfiles.json",
        ["rule:commit-style"],
        targets=["claude", "codex"],
    )

    code, out, _ = _run(install, project)
    assert code == 0, out

    skill_md = project / ".agents" / "skills" / "rule-commit-style" / "SKILL.md"
    assert skill_md.is_file()
    body = skill_md.read_text(encoding="utf-8")
    assert body.splitlines()[0] == MANAGED_BY_HEADER
    assert "name: rule-commit-style" in body
    # ADR ai-1-2: the synthetic skill is never installed for Claude.
    assert not (project / ".claude" / "skills" / "rule-commit-style").exists()
    # The rule still links into the Claude rules tree as a plain rule.
    assert (project / ".claude" / "rules" / "commit-style.md").is_symlink()


def test_remove_strips_owned_agents_md_block_preserving_user_text(
    project: Path, catalog: Path
) -> None:
    """``remove`` strips only the managed block; user AGENTS.md text survives."""
    _make_rule(catalog, "principles", _RULE_ALWAYS_ON)
    _write_manifest(
        project / "ai-dotfiles.json", ["rule:principles"], targets=["codex"]
    )
    # A user-authored AGENTS.md already exists.
    user_text = "# My project\n\nHand-written guidance.\n"
    _write(project / "AGENTS.md", user_text)

    assert _run(install, project)[0] == 0
    assert "ai-dotfiles:rule:principles" in (project / "AGENTS.md").read_text(
        encoding="utf-8"
    )

    code, _, _ = _run(remove, project, "rule:principles")
    assert code == 0
    # The file survives, the managed block is gone, user text is intact.
    remaining = (project / "AGENTS.md").read_text(encoding="utf-8")
    assert "ai-dotfiles:rule:principles" not in remaining
    assert "Hand-written guidance." in remaining


def test_remove_deletes_agents_md_that_held_only_managed_block(
    project: Path, catalog: Path
) -> None:
    """An AGENTS.md created solely for a managed block is deleted on remove."""
    _make_rule(catalog, "api", _RULE_PATH_SCOPED)
    _write_manifest(project / "ai-dotfiles.json", ["rule:api"], targets=["codex"])
    assert _run(install, project)[0] == 0
    nested = project / "src" / "api" / "AGENTS.md"
    assert nested.is_file()

    code, _, _ = _run(remove, project, "rule:api")
    assert code == 0
    # The whitespace-only AGENTS.md is removed entirely.
    assert not nested.exists()


def test_remove_drops_synthetic_rule_skill(project: Path, catalog: Path) -> None:
    """``remove`` deletes the synthetic ``rule-<name>`` skill of a desc-only rule."""
    _make_rule(catalog, "commit-style", _RULE_DESC_ONLY)
    _write_manifest(
        project / "ai-dotfiles.json", ["rule:commit-style"], targets=["codex"]
    )
    assert _run(install, project)[0] == 0
    skill_dir = project / ".agents" / "skills" / "rule-commit-style"
    assert skill_dir.is_dir()

    code, _, _ = _run(remove, project, "rule:commit-style")
    assert code == 0
    assert not skill_dir.exists()


def test_remove_preserves_user_block_in_shared_agents_md(
    project: Path, catalog: Path
) -> None:
    """Removing one rule leaves another rule's block in the same AGENTS.md."""
    _make_rule(catalog, "principles", _RULE_ALWAYS_ON)
    _make_rule(
        catalog,
        "second",
        "---\nalways_on: true\n---\n\n# Second\n\nAnother always-on rule.\n",
    )
    _write_manifest(
        project / "ai-dotfiles.json",
        ["rule:principles", "rule:second"],
        targets=["codex"],
    )
    assert _run(install, project)[0] == 0
    text = (project / "AGENTS.md").read_text(encoding="utf-8")
    assert "ai-dotfiles:rule:principles" in text
    assert "ai-dotfiles:rule:second" in text

    code, _, _ = _run(remove, project, "rule:principles")
    assert code == 0
    remaining = (project / "AGENTS.md").read_text(encoding="utf-8")
    assert "ai-dotfiles:rule:principles" not in remaining
    assert "ai-dotfiles:rule:second" in remaining


def test_install_is_idempotent_for_rules(project: Path, catalog: Path) -> None:
    """A second install does not duplicate a rule's managed block."""
    _make_rule(catalog, "principles", _RULE_ALWAYS_ON)
    _write_manifest(
        project / "ai-dotfiles.json", ["rule:principles"], targets=["codex"]
    )
    assert _run(install, project)[0] == 0
    first = (project / "AGENTS.md").read_text(encoding="utf-8")

    assert _run(install, project)[0] == 0
    second = (project / "AGENTS.md").read_text(encoding="utf-8")
    assert first == second
    assert second.count("ai-dotfiles:rule:principles START") == 1


# ── MCP: mcp.fragment.json -> [mcp_servers] (ai-15) ───────────────────────


def _read_codex_config(project: Path) -> dict[str, object]:
    import tomllib

    with (project / ".codex" / "config.toml").open("rb") as handle:
        return tomllib.load(handle)


def test_install_writes_mcp_servers_table(project: Path, catalog: Path) -> None:
    """A domain's mcp.fragment.json lands in [mcp_servers] of config.toml."""
    _make_mcp_domain(
        catalog,
        "playwright-e2e",
        {"playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]}},
    )
    _write_manifest(
        project / "ai-dotfiles.json", ["@playwright-e2e"], targets=["codex"]
    )

    code, _, _ = _run(install, project)
    assert code == 0

    parsed = _read_codex_config(project)
    assert parsed["mcp_servers"]["playwright"] == {
        "command": "npx",
        "args": ["@playwright/mcp@latest"],
    }


def test_install_mcp_and_settings_coexist_in_one_config(
    project: Path, catalog: Path
) -> None:
    """The ai-14 [ai_dotfiles] region and the ai-15 [mcp_servers] region
    share one config.toml — neither overwrites the other."""
    _make_mcp_domain(
        catalog,
        "tooling",
        {"fs": {"command": "fs-server"}},
        settings={"permissions": {"allow": ["Bash(git diff:*)"]}},
    )
    _write_manifest(project / "ai-dotfiles.json", ["@tooling"], targets=["codex"])

    code, _, _ = _run(install, project)
    assert code == 0

    parsed = _read_codex_config(project)
    assert parsed["ai_dotfiles"]["permissions"]["allow"] == ["Bash(git diff:*)"]
    assert parsed["mcp_servers"]["fs"] == {"command": "fs-server"}


def test_install_is_idempotent_for_mcp(project: Path, catalog: Path) -> None:
    """A second install does not duplicate the [mcp_servers] table."""
    _make_mcp_domain(catalog, "tooling", {"fs": {"command": "x"}})
    _write_manifest(project / "ai-dotfiles.json", ["@tooling"], targets=["codex"])

    assert _run(install, project)[0] == 0
    first = (project / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert _run(install, project)[0] == 0
    second = (project / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert first == second


def test_remove_strips_domain_mcp_servers(project: Path, catalog: Path) -> None:
    """remove drops a domain's MCP servers from [mcp_servers]."""
    _make_mcp_domain(catalog, "tooling", {"fs": {"command": "x"}})
    _write_manifest(project / "ai-dotfiles.json", ["@tooling"], targets=["codex"])
    assert _run(install, project)[0] == 0
    assert "mcp_servers" in _read_codex_config(project)

    code, _, _ = _run(remove, project, "@tooling")
    assert code == 0
    # The whole config is gone — nothing else was in it.
    assert not (project / ".codex" / "config.toml").exists()


def test_remove_preserves_user_authored_mcp_server(
    project: Path, catalog: Path
) -> None:
    """A user-defined [mcp_servers] entry survives removing a domain."""
    _make_mcp_domain(catalog, "tooling", {"fs": {"command": "x"}})
    _write_manifest(project / "ai-dotfiles.json", ["@tooling"], targets=["codex"])
    assert _run(install, project)[0] == 0

    # User hand-adds their own server into the same table.
    cfg = project / ".codex" / "config.toml"
    cfg.write_text(
        cfg.read_text(encoding="utf-8")
        + '\n[mcp_servers.my-own]\ncommand = "user-cmd"\n',
        encoding="utf-8",
    )

    code, _, _ = _run(remove, project, "@tooling")
    assert code == 0

    parsed = _read_codex_config(project)
    assert "fs" not in parsed["mcp_servers"]
    assert parsed["mcp_servers"]["my-own"] == {"command": "user-cmd"}
