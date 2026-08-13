"""E2E tests for the Codex GLOBAL (user-scope) target.

Drives ``install -g`` / ``remove -g`` / ``status -g`` / ``reconcile -g``
through the top-level click group with ``CliRunner``, covering the
``targets`` field of ``global.json`` (codex-global-target, superseding
ADR ai-1-3's project-only restriction):

* ``targets: ["claude", "codex"]`` — renders the global packages into
  ``$CODEX_HOME`` (gated symlink / render for skills, agent ``.toml``,
  rule dispatch, the ``~/.claude/CLAUDE.md`` bridge, config/hooks);
* no ``targets`` field — the regression guard: ``install -g`` behaves
  byte-identically to the Claude-only behaviour and never touches
  ``$CODEX_HOME``;
* foreign content in ``$CODEX_HOME`` (the user's own ``config.toml``
  keys, hook groups, ``AGENTS.md`` paragraphs, hand-authored skills)
  survives install, remove and prune.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import tomllib
from click.testing import CliRunner

from ai_dotfiles.cli import cli
from ai_dotfiles.core.codex_install import SKILL_DESCRIPTION_MAX

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
def codex_home(home: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point CODEX_HOME at a distinct dir (NOT ~/.codex) — proves the env
    override is honoured. Deliberately not created: install must mkdir."""
    codex = home / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(codex))
    return codex


# ── Catalog / manifest helpers ────────────────────────────────────────────

_SKILL_MD = """\
---
name: {name}
description: {description}
---

# {name}

Skill body.
"""

_AGENT_MD = """\
---
name: {name}
description: An example {name} agent.
---

# {name}

Agent body.
"""

_RULE_ALWAYS_ON = "---\nalways_on: true\n---\n\n# Principles\n\nAlways-loaded.\n"
_RULE_PATH_SCOPED = "---\npaths:\n  - src/api\n---\n\n# API rule\n\nScoped body.\n"
_RULE_DESC_ONLY = "# Commit style\n\nUse Conventional Commits.\n"


def _write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_skill(catalog: Path, name: str, description: str = "Short one.") -> Path:
    skill = catalog / "skills" / name
    _write(skill / "SKILL.md", _SKILL_MD.format(name=name, description=description))
    return skill


def _make_agent(catalog: Path, name: str) -> Path:
    path = catalog / "agents" / f"{name}.md"
    _write(path, _AGENT_MD.format(name=name))
    return path


def _make_rule(catalog: Path, name: str, text: str) -> Path:
    path = catalog / "rules" / f"{name}.md"
    _write(path, text)
    return path


def _make_domain_with_hooks(catalog: Path, name: str) -> Path:
    """A domain carrying a settings fragment (permissions + hooks)."""
    domain = catalog / name
    _write(
        domain / "settings.fragment.json",
        json.dumps(
            {
                "permissions": {"allow": ["Bash(git *)"]},
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/g.sh",
                                }
                            ],
                        }
                    ]
                },
            }
        ),
    )
    _write(
        domain / "skills" / f"{name}-skill" / "SKILL.md",
        _SKILL_MD.format(name=f"{name}-skill", description="Domain skill."),
    )
    return domain


def _write_global_manifest(
    storage: Path, packages: list[str], *, targets: list[str] | None = None
) -> None:
    data: dict[str, object] = {"packages": packages}
    if targets is not None:
        data["targets"] = targets
    (storage / "global.json").write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )


def _run(cwd: Path, *args: str) -> tuple[int, str, str]:
    runner = CliRunner()
    prev = os.getcwd()
    os.chdir(cwd)
    try:
        result = runner.invoke(cli, list(args), catch_exceptions=False)
    finally:
        os.chdir(prev)
    return result.exit_code, result.stdout, result.stderr


def _read_toml(path: Path) -> dict[str, object]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


# Foreign $CODEX_HOME content that every mutation must preserve.
_MOSHI_GROUP = {
    "matcher": "*",
    "hooks": [{"type": "command", "command": "moshi-hook notify"}],
}


def _seed_foreign_codex_home(codex: Path) -> None:
    codex.mkdir(parents=True, exist_ok=True)
    (codex / "config.toml").write_text(
        'model = "gpt-5.2"\n\n[user_table]\nkey = "value"\n', encoding="utf-8"
    )
    (codex / "hooks.json").write_text(
        json.dumps({"hooks": {"PreToolUse": [_MOSHI_GROUP]}}, indent=2) + "\n",
        encoding="utf-8",
    )
    (codex / "AGENTS.md").write_text("My own global paragraph.\n", encoding="utf-8")


def _assert_foreign_content_survived(codex: Path) -> None:
    config = _read_toml(codex / "config.toml")
    assert config["model"] == "gpt-5.2"
    assert config["user_table"] == {"key": "value"}
    hooks = json.loads((codex / "hooks.json").read_text(encoding="utf-8"))
    assert _MOSHI_GROUP in hooks["hooks"]["PreToolUse"]
    assert "My own global paragraph." in (codex / "AGENTS.md").read_text(
        encoding="utf-8"
    )


# ── install -g: the codex target renders into $CODEX_HOME ─────────────────


def test_install_global_codex_renders_all_artefact_kinds(
    home: Path, storage: Path, catalog: Path, codex_home: Path
) -> None:
    _make_skill(catalog, "commit")
    over_cap_tail = "y" * (SKILL_DESCRIPTION_MAX + 1)
    over_cap = f"First sentence. {over_cap_tail}"
    _make_skill(catalog, "verbose", description=over_cap)
    _make_agent(catalog, "researcher")
    _make_rule(catalog, "principles", _RULE_ALWAYS_ON)
    _make_rule(catalog, "api", _RULE_PATH_SCOPED)
    _make_rule(catalog, "commits", _RULE_DESC_ONLY)
    _write(home / ".claude" / "CLAUDE.md", "# Prefs\n\nAnswer in Russian.\n")
    _write_global_manifest(
        storage,
        [
            "skill:commit",
            "skill:verbose",
            "agent:researcher",
            "rule:principles",
            "rule:api",
            "rule:commits",
        ],
        targets=["claude", "codex"],
    )

    code, out, err = _run(home, "install", "-g")
    assert code == 0, out + err

    # In-limits skill: an ABSOLUTE symlink into the catalog (auto-fresh).
    link = codex_home / "skills" / "commit"
    assert link.is_symlink()
    assert os.path.isabs(os.readlink(link))
    assert link.resolve() == (catalog / "skills" / "commit").resolve()

    # Over-cap skill: rendered with the trim + drift sidecar.
    rendered = codex_home / "skills" / "verbose"
    assert rendered.is_dir() and not rendered.is_symlink()
    assert (rendered / ".ai-dotfiles-meta").is_file()
    skill_md = (rendered / "SKILL.md").read_text(encoding="utf-8")
    assert over_cap_tail not in skill_md
    assert "First sentence." in skill_md

    # Agent: rendered TOML with the managed + sha headers.
    toml_text = (codex_home / "agents" / "researcher.toml").read_text(encoding="utf-8")
    assert toml_text.startswith("# managed-by: ai-dotfiles\n# source-sha256: ")

    # Rules: always-on -> block in the global AGENTS.md; description-only
    # AND path-scoped (demoted, with a warning) -> rule-skills.
    agents_md = (codex_home / "AGENTS.md").read_text(encoding="utf-8")
    assert "<!-- ai-dotfiles:rule:principles START -->" in agents_md
    assert (codex_home / "skills" / "rule-commits" / "SKILL.md").is_file()
    assert (codex_home / "skills" / "rule-api" / "SKILL.md").is_file()
    assert "path-scoped" in err and "rule-api" in err

    # The instructions bridge from ~/.claude/CLAUDE.md.
    assert "<!-- ai-dotfiles:rule:claude-global-instructions START -->" in agents_md
    assert "Answer in Russian." in agents_md

    # config.toml: Codex reads CLAUDE.md as a project-doc fallback.
    config = _read_toml(codex_home / "config.toml")
    assert config["project_doc_fallback_filenames"] == ["CLAUDE.md"]

    # The Claude target was rendered too (multi-target).
    assert (home / ".claude" / "skills" / "commit").is_symlink()


def test_install_global_without_targets_is_byte_identical(
    home: Path, storage: Path, catalog: Path, codex_home: Path
) -> None:
    """The regression guard: no `targets` field -> $CODEX_HOME untouched."""
    _make_skill(catalog, "commit")
    _write(home / ".claude" / "CLAUDE.md", "# Prefs\n")
    _write_global_manifest(storage, ["skill:commit"])  # no targets

    code, out, err = _run(home, "install", "-g")
    assert code == 0, out + err

    assert not codex_home.exists()
    assert (home / ".claude" / "skills" / "commit").is_symlink()


def test_install_global_codex_preserves_foreign_codex_home(
    home: Path, storage: Path, catalog: Path, codex_home: Path
) -> None:
    """The user's own config.toml keys, hook groups and AGENTS.md text stay."""
    _seed_foreign_codex_home(codex_home)
    domain = _make_domain_with_hooks(catalog, "web")
    assert domain.is_dir()
    _make_rule(catalog, "principles", _RULE_ALWAYS_ON)
    _write_global_manifest(
        storage, ["@web", "rule:principles"], targets=["claude", "codex"]
    )

    code, out, err = _run(home, "install", "-g")
    assert code == 0, out + err

    _assert_foreign_content_survived(codex_home)
    # Domain content landed next to the foreign content.
    config = _read_toml(codex_home / "config.toml")
    assert config["ai_dotfiles"] == {"permissions": {"allow": ["Bash(git *)"]}}
    hooks = json.loads((codex_home / "hooks.json").read_text(encoding="utf-8"))
    domain_groups = [g for g in hooks["hooks"]["PreToolUse"] if g != _MOSHI_GROUP]
    assert len(domain_groups) == 1
    command = domain_groups[0]["hooks"][0]["command"]
    # Relative — Codex sets no project-root variable and runs hooks from the
    # session root. (At global scope that root is whatever project the user
    # is in, which is the same place `.claude/hooks/` lives.)
    assert command == ".claude/hooks/g.sh"
    agents_md = (codex_home / "AGENTS.md").read_text(encoding="utf-8")
    assert "My own global paragraph." in agents_md
    assert "<!-- ai-dotfiles:rule:principles START -->" in agents_md


def test_install_global_codex_only_skips_claude_linking(
    home: Path, storage: Path, catalog: Path, codex_home: Path
) -> None:
    _make_skill(catalog, "commit")
    _write_global_manifest(storage, ["skill:commit"], targets=["codex"])

    code, out, err = _run(home, "install", "-g")
    assert code == 0, out + err

    assert (codex_home / "skills" / "commit").is_symlink()
    assert not (home / ".claude" / "skills" / "commit").exists()


# ── install -g --prune ────────────────────────────────────────────────────


def test_install_global_prune_removes_orphans_keeps_foreign(
    home: Path, storage: Path, catalog: Path, codex_home: Path
) -> None:
    _make_skill(catalog, "commit")
    _make_skill(catalog, "old")
    _make_agent(catalog, "researcher")
    _make_rule(catalog, "principles", _RULE_ALWAYS_ON)
    _write(home / ".claude" / "CLAUDE.md", "# Prefs\n")
    _write_global_manifest(
        storage,
        ["skill:commit", "skill:old", "agent:researcher", "rule:principles"],
        targets=["claude", "codex"],
    )
    code, out, err = _run(home, "install", "-g")
    assert code == 0, out + err

    # A user-authored skill (no sidecar, no catalog link) sits alongside.
    _write(
        codex_home / "skills" / "mine" / "SKILL.md",
        "---\nname: mine\ndescription: Mine.\n---\n\nbody\n",
    )

    # Drop skill:old + the rule from the manifest and prune.
    _write_global_manifest(
        storage,
        ["skill:commit", "agent:researcher"],
        targets=["claude", "codex"],
    )
    code, out, err = _run(home, "install", "-g", "--prune")
    assert code == 0, out + err

    assert not (codex_home / "skills" / "old").exists()
    agents_md = (codex_home / "AGENTS.md").read_text(encoding="utf-8")
    assert "ai-dotfiles:rule:principles" not in agents_md
    # Kept: the wanted symlink, the user skill, and the bridge block.
    assert (codex_home / "skills" / "commit").is_symlink()
    assert (codex_home / "skills" / "mine" / "SKILL.md").is_file()
    assert "claude-global-instructions" in agents_md


# ── remove -g ─────────────────────────────────────────────────────────────


def test_remove_global_strips_only_owned_artefacts(
    home: Path, storage: Path, catalog: Path, codex_home: Path
) -> None:
    _seed_foreign_codex_home(codex_home)
    _make_skill(catalog, "commit")
    _make_agent(catalog, "researcher")
    _make_rule(catalog, "principles", _RULE_ALWAYS_ON)
    _write_global_manifest(
        storage,
        ["skill:commit", "agent:researcher", "rule:principles"],
        targets=["claude", "codex"],
    )
    code, out, err = _run(home, "install", "-g")
    assert code == 0, out + err

    code, out, err = _run(
        home, "remove", "-g", "skill:commit", "agent:researcher", "rule:principles"
    )
    assert code == 0, out + err

    assert not (codex_home / "skills" / "commit").exists()
    assert not (codex_home / "agents" / "researcher.toml").exists()
    assert "ai-dotfiles:rule:principles" not in (codex_home / "AGENTS.md").read_text(
        encoding="utf-8"
    )
    _assert_foreign_content_survived(codex_home)


# ── status -g ─────────────────────────────────────────────────────────────


def test_status_global_reports_codex_artefacts(
    home: Path, storage: Path, catalog: Path, codex_home: Path
) -> None:
    _make_skill(catalog, "commit")
    _make_agent(catalog, "researcher")
    _write(home / ".claude" / "CLAUDE.md", "# Prefs\n")
    _write_global_manifest(
        storage,
        ["skill:commit", "agent:researcher"],
        targets=["claude", "codex"],
    )

    # Before install: NOT INSTALLED, exit 1.
    code, out, err = _run(home, "status", "-g")
    assert code == 1
    assert "Codex target (global)" in out
    assert "NOT INSTALLED" in out

    code, out, err = _run(home, "install", "-g")
    assert code == 0, out + err

    code, out, err = _run(home, "status", "-g")
    assert code == 0, out
    assert "OK (symlink)" in out
    assert "AGENTS.md (global instructions)" in out

    # Edit the agent source -> STALE.
    _make_agent(catalog, "researcher")  # same content — still OK
    (catalog / "agents" / "researcher.md").write_text(
        _AGENT_MD.format(name="researcher") + "\nMore.\n", encoding="utf-8"
    )
    code, out, err = _run(home, "status", "-g")
    assert code == 1
    assert "STALE (source changed)" in out


def test_status_global_flags_symlinked_skill_gone_over_cap(
    home: Path, storage: Path, catalog: Path, codex_home: Path
) -> None:
    """A symlinked skill whose description grew over the cap is surfaced —
    otherwise it would silently fail to load in every Codex session."""
    skill = _make_skill(catalog, "commit")
    _write_global_manifest(storage, ["skill:commit"], targets=["codex"])
    code, out, err = _run(home, "install", "-g")
    assert code == 0, out + err

    _write(
        skill / "SKILL.md",
        _SKILL_MD.format(name="commit", description="z" * (SKILL_DESCRIPTION_MAX + 1)),
    )

    code, out, err = _run(home, "status", "-g")
    assert code == 1
    assert "exceeds Codex skill limits" in out


# ── reconcile -g ──────────────────────────────────────────────────────────


def test_reconcile_global_check_detects_and_fix_repairs(
    home: Path, storage: Path, catalog: Path, codex_home: Path
) -> None:
    _make_agent(catalog, "researcher")
    _write(home / ".claude" / "CLAUDE.md", "# Prefs\n")
    _write_global_manifest(storage, ["agent:researcher"], targets=["codex"])
    code, out, err = _run(home, "install", "-g")
    assert code == 0, out + err

    # Drift: edit the agent source and the global CLAUDE.md.
    (catalog / "agents" / "researcher.md").write_text(
        _AGENT_MD.format(name="researcher") + "\nMore.\n", encoding="utf-8"
    )
    (home / ".claude" / "CLAUDE.md").write_text("# Prefs\n\nNew.\n", encoding="utf-8")

    toml_before = (codex_home / "agents" / "researcher.toml").read_text(
        encoding="utf-8"
    )
    code, out, err = _run(home, "reconcile", "-g", "--check")
    assert code == 1
    assert "agents/researcher.toml" in out
    assert "AGENTS.md (global instructions)" in out
    # --check wrote nothing.
    assert (codex_home / "agents" / "researcher.toml").read_text(
        encoding="utf-8"
    ) == toml_before

    code, out, err = _run(home, "reconcile", "-g")
    assert code == 0, out + err
    assert "Reconciled" in out

    code, out, err = _run(home, "reconcile", "-g", "--check")
    assert code == 0, out
    assert "up to date" in out


def test_reconcile_global_converts_over_cap_symlink_to_render(
    home: Path, storage: Path, catalog: Path, codex_home: Path
) -> None:
    skill = _make_skill(catalog, "commit")
    _write_global_manifest(storage, ["skill:commit"], targets=["codex"])
    code, out, err = _run(home, "install", "-g")
    assert code == 0, out + err
    assert (codex_home / "skills" / "commit").is_symlink()

    _write(
        skill / "SKILL.md",
        _SKILL_MD.format(name="commit", description="z" * (SKILL_DESCRIPTION_MAX + 1)),
    )

    code, out, err = _run(home, "reconcile", "-g")
    assert code == 0, out + err

    target = codex_home / "skills" / "commit"
    assert target.is_dir() and not target.is_symlink()
    assert (target / ".ai-dotfiles-meta").is_file()
    # The catalog source stayed clean — nothing was written through the link.
    assert not (skill / ".ai-dotfiles-meta").exists()


def test_reconcile_global_noop_when_codex_not_in_targets(
    home: Path, storage: Path, catalog: Path, codex_home: Path
) -> None:
    _make_skill(catalog, "commit")
    _write_global_manifest(storage, ["skill:commit"])  # claude-only

    code, out, err = _run(home, "reconcile", "-g")
    assert code == 0, out + err
    assert "not a global target" in out
    assert not codex_home.exists()


# ── add -g ────────────────────────────────────────────────────────────────


def test_add_global_renders_codex_artefacts(
    home: Path, storage: Path, catalog: Path, codex_home: Path
) -> None:
    _make_skill(catalog, "commit")
    _make_agent(catalog, "researcher")
    _write_global_manifest(storage, [], targets=["claude", "codex"])

    code, out, err = _run(home, "add", "-g", "skill:commit", "agent:researcher")
    assert code == 0, out + err

    assert (codex_home / "skills" / "commit").is_symlink()
    assert (codex_home / "agents" / "researcher.toml").is_file()
    assert (home / ".claude" / "skills" / "commit").is_symlink()
