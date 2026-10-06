"""Full CLI contracts for DSH status, reconciliation and local migration."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from click.shell_completion import BashComplete
from click.testing import CliRunner, Result

from ai_dotfiles.cli import cli
from ai_dotfiles.core import agents_md
from ai_dotfiles.core.copy_ownership import save_copy_ownership
from ai_dotfiles.core.dsh_install import read_dsh_inventory
from ai_dotfiles.core.dsh_layout import global_layout, project_layout
from ai_dotfiles.core.dsh_local_registry import load_dsh_local_registry
from ai_dotfiles.core.dsh_migrate import (
    collect_dsh_local_inputs,
    verify_dsh_local_inputs,
)
from ai_dotfiles.core.dsh_reconcile import reconcile_dsh
from ai_dotfiles.core.errors import LinkError
from ai_dotfiles.core.settings_ownership import save_settings_ownership
from ai_dotfiles.core.targets import Target
from tests.integration.test_dsh_reconcile import _snapshot


@pytest.fixture(autouse=True)
def isolated_homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (tmp_path / "storage/catalog").mkdir(parents=True)
    (tmp_path / "storage/global").mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("DSH_HOME", str(home / "dsh"))
    monkeypatch.setenv("CODEX_HOME", str(home / "codex"))
    monkeypatch.setenv("AI_DOTFILES_HOME", str(tmp_path / "storage"))


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode())
    return path


def _json(path: Path, value: object) -> Path:
    return _write(path, json.dumps(value))


def _skill(root: Path, name: str, description: str = "Local skill") -> Path:
    return _write(
        root / "skills" / name / "SKILL.md",
        f"---\nname: {name}\ndescription: {description}\n---\n{name} body\n",
    )


def _rule(path: Path, body: str = "Local original body") -> Path:
    return _write(path, f"---\nalways_on: true\n---\n{body}\n")


def _project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    packages: list[str] | None = None,
    targets: list[str] | None = None,
    mode: str = "symlink",
) -> Path:
    root = tmp_path / "project"
    (root / ".git").mkdir(parents=True)
    value: dict[str, object] = {"packages": packages or [], "link_mode": mode}
    if targets is not None:
        value["targets"] = targets
    _json(root / "ai-dotfiles.json", value)
    monkeypatch.chdir(root)
    return root


def _invoke(*args: str, exit_code: int = 0) -> Result:
    result = CliRunner().invoke(cli, list(args))
    assert result.exit_code == exit_code, (result.output, result.exception)
    return result


def _domain(catalog: Path) -> None:
    domain = catalog / "alpha"
    _skill(domain, "catalog-skill")
    _rule(domain / "rules/shared.md", "Catalog original body")
    _write(
        domain / "agents/catalog-agent.md",
        "---\nname: catalog-agent\ndescription: Catalog child\n---\nCatalog child\n",
    )
    _json(domain / "settings.fragment.json", {"env": {"CATALOG": "kept"}})
    _json(
        domain / "mcp.fragment.json",
        {"mcpServers": {"catalog": {"command": "node", "args": ["fake.mjs"]}}},
    )
    _json(
        domain / "dsh.fragment.json",
        [{"insert": [{"id": "native-note", "name": "./native.mjs", "config": {}}]}],
    )
    _write(domain / "native.mjs", "export function apply() {}\n")
    _write(domain / "fake.mjs", "process.exit(0);\n")


def test_migration_help_default_and_unknown_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, monkeypatch)
    _skill(root / ".claude", "local")
    before = _snapshot(tmp_path)
    help_result = _invoke("migrate", "--help")
    assert "[codex|dsh]" in help_result.output
    assert "default: codex" in help_result.output
    assert "--global" not in help_result.output
    for args in (("--to", "unknown"), ("--to", "dsh", "-g")):
        rejected = _invoke("migrate", *args, exit_code=2)
        assert "Error:" in rejected.output
        assert _snapshot(tmp_path) == before
    _invoke("migrate", "--dry-run")
    assert _snapshot(tmp_path) == before
    _invoke("migrate")
    assert (root / ".agents/skills/local").is_symlink()
    assert not (root / ".dsh").exists()


@pytest.mark.parametrize("prefix,expected", [("", ["codex", "dsh"]), ("d", ["dsh"])])
def test_migrate_choice_shell_completion_is_read_only(
    tmp_path: Path, prefix: str, expected: list[str]
) -> None:
    before = _snapshot(tmp_path)
    complete = BashComplete(cli, {}, "ai-dotfiles", "_AI_DOTFILES_COMPLETE")
    assert [
        item.value for item in complete.get_completions(["migrate", "--to"], prefix)
    ] == expected
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "args", [("migrate", "--to", "dsh"), ("status",), ("reconcile", "--check")]
)
def test_project_manifest_required_even_with_global_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, args: tuple[str, ...]
) -> None:
    monkeypatch.chdir(tmp_path)
    _json(tmp_path / "storage/global.json", {"packages": [], "targets": ["dsh"]})
    before = _snapshot(tmp_path)
    assert "ai-dotfiles.json not found" in _invoke(*args, exit_code=1).output
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("mode", ["symlink", "copy"])
def test_safe_local_migration_classifies_and_preserves_manual_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    root = _project(tmp_path, monkeypatch, mode=mode)
    _skill(root / ".claude", "local")
    _rule(root / ".claude/rules/local.md")
    _write(
        root / ".claude/agents/child.md",
        "---\nname: child\ndescription: Literal child\n"
        "model: sonnet\n---\n{{literal}}\n",
    )
    _write(
        root / ".claude/agents/restricted.md",
        "---\nname: restricted\ndescription: Restricted\ntools: Task\n---\nKeep me\n",
    )
    _write(root / ".claude/rules/scoped.md", "---\npaths: [src/**]\n---\nKeep scoped\n")
    _write(
        root / ".claude/commands/on-demand.md",
        "---\nname: on-demand\ndescription: On demand\n"
        "disable-model-invocation: true\n---\nLiteral command\n",
    )
    manual = _write(
        root / ".claude/commands/executable.md",
        "---\nname: executable\ndescription: Manual\n"
        "disable-model-invocation: true\n---\n!`ls` $ARGUMENTS\n",
    )
    _json(root / ".claude/settings.local.json", {"env": {"LOCAL": "value"}})
    _json(root / ".mcp.json", {"mcpServers": {"local": {"command": "node"}}})
    _json(
        root / ".claude/hooks.json",
        {
            "hooks": {
                "SessionStart": [
                    {"hooks": [{"type": "command", "command": "echo local"}]}
                ]
            }
        },
    )
    originals = _snapshot(root / ".claude")
    manual_bytes = manual.read_bytes()
    before = _snapshot(tmp_path)
    dry = _invoke("migrate", "--to", "dsh", "--dry-run")
    assert "[MECHANICAL]" in dry.output
    assert "[REFACTOR]" in dry.output
    assert "[MANUAL]" in dry.output
    assert "local agent:restricted tools" in dry.output
    assert "MODEL_UNMAPPED" in dry.output
    assert "COMMAND_EXECUTION_UNMAPPED" in dry.output
    assert _snapshot(tmp_path) == before
    _invoke("migrate", "--to", "dsh")
    layout = project_layout(root)
    assert (layout.skills_dir / "local").is_symlink() == (mode == "symlink")
    assert (layout.skills_dir / "on-demand.md").is_file()
    config = json.loads(layout.config_path.read_bytes())
    assert config["environment"] == {"LOCAL": "value"}
    assert (
        len([part for part in config["contributions"] if part["name"] == "hooks"]) == 1
    )
    assert "Local original body" in layout.root_agents_md.read_text()
    assert manual.read_bytes() == manual_bytes
    assert _snapshot(root / ".claude") == originals
    registry = load_dsh_local_registry(root)
    assert (
        registry.sources[".claude/commands/executable.md"]["classification"] == "MANUAL"
    )
    assert (
        registry.sources[".claude/agents/restricted.md"]["classification"] == "MANUAL"
    )
    assert not any(
        row["id"] == "ai-dotfiles-agent-restricted" for row in config["rows"]
    )
    before = _snapshot(tmp_path)
    status = _invoke("status")
    assert "DSH target" in status.output
    assert "[MANUAL] local command:executable" in status.output
    assert "Runtime audit: run" in status.output
    assert "READY" not in status.output
    assert _snapshot(tmp_path) == before


def test_migration_retains_fresh_catalog_native_hooks_and_local_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, monkeypatch, ["@alpha"], ["dsh"])
    catalog = tmp_path / "storage/catalog"
    _domain(catalog)
    _json(
        catalog / "alpha/settings.fragment.json",
        {
            "env": {"CATALOG": "kept"},
            "hooks": {
                "SessionStart": [
                    {"hooks": [{"type": "command", "command": "echo catalog"}]}
                ]
            },
        },
    )
    _invoke("install")
    _skill(root / ".claude", "local")
    _json(root / ".claude/settings.local.json", {"env": {"LOCAL": "fresh"}})
    _json(root / ".mcp.json", {"mcpServers": {"local": {"command": "node"}}})
    before = _snapshot(tmp_path)
    _invoke("migrate", "--to", "dsh", "--dry-run")
    assert _snapshot(tmp_path) == before
    _invoke("migrate", "--to", "dsh")
    layout = project_layout(root)
    config = json.loads(layout.config_path.read_bytes())
    assert config["environment"] == {"CATALOG": "kept", "LOCAL": "fresh"}
    names = [part["name"] for part in config["contributions"]]
    assert {"mcp:catalog", "mcp:local", "hooks"} <= set(names)
    assert len(names) == len(set(names))
    assert len(config["domainPatches"]) == 1
    row = config["domainPatches"][0]["insert"][0]
    assert row["id"] == "native-note"
    assert row["name"].endswith("/resources/domains/alpha/native.mjs")
    assert (
        len([source for source in config["sources"] if source["kind"] == "native"]) == 1
    )
    assert (layout.skills_dir / "catalog-skill/SKILL.md").is_file()
    assert (layout.skills_dir / "local/SKILL.md").is_file()
    before = _snapshot(tmp_path)
    _invoke("migrate", "--to", "dsh")
    assert _snapshot(tmp_path) == before
    assert not reconcile_dsh(root, ["@alpha"], catalog, check_only=True).drift
    check = _invoke("reconcile", "--check", exit_code=1)
    assert "Codex drift detected" in check.output
    assert "DSH drift detected" not in check.output
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("scope", ["project", "global"])
@pytest.mark.parametrize(
    "targets", [["dsh"], ["codex", "dsh"], ["claude", "codex", "dsh"]]
)
@pytest.mark.parametrize("mode", ["symlink", "copy"])
def test_status_and_reconcile_catalog_drift_both_scopes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scope: str,
    targets: list[str],
    mode: str,
) -> None:
    root = _project(tmp_path, monkeypatch, ["@alpha"], targets, mode)
    catalog = tmp_path / "storage/catalog"
    _domain(catalog)
    args = ("-g",) if scope == "global" else ()
    if scope == "global":
        _json(
            tmp_path / "storage/global.json",
            {"packages": ["@alpha"], "targets": targets},
        )
    layout = global_layout() if scope == "global" else project_layout(root)
    profile = _write(layout.dsh_dir / "profiles/user/cordis.yml", "User profile\n")
    _invoke("install", *args)
    before = _snapshot(tmp_path)
    _invoke("status", *args)
    _invoke("reconcile", *args, "--check")
    assert _snapshot(tmp_path) == before
    _rule(catalog / "alpha/rules/shared.md", "Fresh shared body")
    _write(
        catalog / "alpha/agents/catalog-agent.md",
        "---\nname: catalog-agent\ndescription: Fresh child\n---\nFresh child\n",
    )
    before = _snapshot(tmp_path)
    status = _invoke("status", *args, exit_code=1)
    assert "DSH target" in status.output and "STALE" in status.output
    assert "READY" not in status.output
    check = _invoke("reconcile", *args, "--check", exit_code=1)
    assert "DSH drift detected" in check.output
    if "codex" in targets:
        assert "Codex drift detected" in check.output
    assert _snapshot(tmp_path) == before
    _invoke("reconcile", *args)
    _invoke("reconcile", *args, "--check")
    _invoke("status", *args)
    assert layout.root_agents_md.read_text().count("Fresh shared body") == 1
    assert profile.read_bytes() == b"User profile\n"


@pytest.mark.parametrize("change", ["missing", "resource", "generator"])
def test_dsh_drift_reports_missing_resource_and_generator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    root = _project(tmp_path, monkeypatch, ["@alpha"], ["dsh"])
    _domain(tmp_path / "storage/catalog")
    _invoke("install")
    layout = project_layout(root)
    if change == "missing":
        layout.bridge_path.unlink()
    elif change == "resource":
        _write(tmp_path / "storage/catalog/alpha/fake.mjs", "// Fresh resource\n")
    else:
        value = json.loads(layout.provenance_path.read_bytes())
        value["records"][str(layout.bridge_path.relative_to(layout.dsh_dir))][
            "generators"
        ]["bridge"] = 999
        _json(layout.provenance_path, value)
    before = _snapshot(tmp_path)
    status = _invoke("status", exit_code=1)
    assert "DSH target" in status.output and "STALE" in status.output
    _invoke("reconcile", "--check", exit_code=1)
    assert _snapshot(tmp_path) == before
    _invoke("reconcile")
    _invoke("reconcile", "--check")


@pytest.mark.parametrize("different", [False, True])
def test_registered_namesake_original_is_never_false_retirement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, different: bool
) -> None:
    root = _project(tmp_path, monkeypatch)
    original = _rule(root / ".claude/rules/shared.md")
    _invoke("migrate", "--to", "dsh")
    catalog = tmp_path / "storage/catalog"
    _rule(
        catalog / "rules/shared.md",
        "Different catalog body" if different else "Local original body",
    )
    _json(
        root / "ai-dotfiles.json", {"packages": ["rule:shared"], "targets": ["codex"]}
    )
    if different:
        before = _snapshot(tmp_path)
        assert (
            "Conflicting shared target union"
            in _invoke("install", "--prune", exit_code=1).output
        )
        assert _snapshot(tmp_path) == before
    else:
        _invoke("install", "--prune")
    inputs = collect_dsh_local_inputs(
        root, manifest_packages=["rule:shared"], catalog_plan=None
    )
    assert original in [action.source for action in inputs.actions]
    before = _snapshot(tmp_path)
    check = _invoke("reconcile", "--check", exit_code=int(different))
    assert "retired" not in check.output
    if different:
        assert "Conflicting shared target union" in check.output
    else:
        assert not reconcile_dsh(
            root,
            ["rule:shared"],
            catalog,
            targets=(Target.CODEX,),
            include_catalog=False,
            check_only=True,
        ).drift
    assert _snapshot(tmp_path) == before
    assert original.read_bytes().endswith(b"Local original body\n")


def test_deleted_namesake_retires_dsh_custody_and_keeps_codex_catalog_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, monkeypatch)
    original = _rule(root / ".claude/rules/shared.md")
    _invoke("migrate", "--to", "dsh")
    _rule(tmp_path / "storage/catalog/rules/shared.md")
    _json(
        root / "ai-dotfiles.json", {"packages": ["rule:shared"], "targets": ["codex"]}
    )
    _invoke("install")
    original.unlink()
    before = _snapshot(tmp_path)
    assert "retired" in _invoke("reconcile", "--check", exit_code=1).output
    assert _snapshot(tmp_path) == before
    _invoke("reconcile")
    assert not load_dsh_local_registry(root).sources
    assert not load_dsh_local_registry(root).rule_blocks
    assert "shared" in agents_md.iter_rule_block_names((root / "AGENTS.md").read_text())
    assert read_dsh_inventory(project_layout(root)).rule_blocks == {}
    _invoke("reconcile", "--check")


def test_full_reconcile_discovers_new_locals_but_excludes_unregistered_manifest_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, monkeypatch)
    _skill(root / ".claude", "registered")
    _invoke("migrate", "--to", "dsh")
    _skill(root / ".claude", "new-local")
    _rule(root / ".claude/rules/shared.md")
    _rule(tmp_path / "storage/catalog/rules/shared.md")
    _json(
        root / "ai-dotfiles.json", {"packages": ["rule:shared"], "targets": ["codex"]}
    )
    before = _snapshot(tmp_path)
    _invoke("reconcile", "--check", exit_code=1)
    assert _snapshot(tmp_path) == before
    _invoke("reconcile")
    registry = load_dsh_local_registry(root)
    assert ".claude/skills/new-local/SKILL.md" in registry.sources
    assert ".claude/rules/shared.md" not in registry.sources
    _invoke("reconcile", "--check")


@pytest.mark.parametrize("ownership", ["link", "copy"])
def test_registered_original_exception_never_adopts_catalog_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ownership: str
) -> None:
    root = _project(tmp_path, monkeypatch)
    original = _rule(root / ".claude/rules/shared.md")
    _invoke("migrate", "--to", "dsh")
    catalog_original = _rule(tmp_path / "storage/catalog/rules/shared.md")
    if ownership == "link":
        original.unlink()
        original.symlink_to(catalog_original)
        before = _snapshot(tmp_path)
        with pytest.raises(LinkError, match="resolves outside project"):
            collect_dsh_local_inputs(root, manifest_packages=["rule:shared"])
        assert _snapshot(tmp_path) == before
    else:
        save_copy_ownership(root / ".claude", {"rules/shared.md"})
        inputs = collect_dsh_local_inputs(root, manifest_packages=["rule:shared"])
        assert not inputs.actions


@pytest.mark.parametrize("scope", ["project", "global"])
@pytest.mark.parametrize("redirected", [False, True])
def test_disabled_targets_ignore_foreign_dsh_and_global_codex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scope: str, redirected: bool
) -> None:
    root = _project(tmp_path, monkeypatch)
    args = ("-g",) if scope == "global" else ()
    if scope == "global":
        _json(tmp_path / "storage/global.json", {"packages": []})
    layout = global_layout() if scope == "global" else project_layout(root)
    foreign = _write(tmp_path / "foreign/config.json", "foreign invalid JSON\n")
    if redirected:
        layout.dsh_dir.parent.mkdir(parents=True, exist_ok=True)
        layout.dsh_dir.symlink_to(foreign.parent, target_is_directory=True)
    else:
        _write(layout.config_path, "foreign invalid JSON\n")
    _write(tmp_path / "home/codex/config.toml", "foreign invalid TOML\n")
    before = _snapshot(tmp_path)
    _invoke("status", *args)
    _invoke("reconcile", *args, "--check")
    _invoke("reconcile", *args)
    assert _snapshot(tmp_path) == before


def test_disabled_codex_local_only_reconcile_is_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, monkeypatch)
    source = _skill(root / ".claude", "big", "x" * 1100)
    _invoke("migrate")
    _write(source, source.read_text().replace("x" * 1100, "y" * 1100))
    before = _snapshot(tmp_path)
    _invoke("reconcile", "--check", exit_code=1)
    assert _snapshot(tmp_path) == before
    _invoke("reconcile")
    assert "y" * 1100 in (root / ".agents/skills/big/SKILL.md").read_text()
    assert not (root / ".dsh").exists()


def test_unproven_aggregate_env_refuses_with_origin_field_and_zero_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, monkeypatch)
    _json(root / ".claude/settings.json", {"env": {"AMBIGUOUS": "never inferred"}})
    save_settings_ownership(
        root / ".claude", {"permissions_deny": [], "hooks_signatures": []}
    )
    before = _snapshot(tmp_path)
    dry = _invoke("migrate", "--to", "dsh", "--dry-run")
    assert "[MANUAL]" in dry.output and "LOCAL_ORIGINAL_UNPROVEN" in dry.output
    assert "local .claude/settings.json env" in dry.output
    refused = _invoke("migrate", "--to", "dsh", exit_code=1)
    assert "original local-user origin" in refused.output
    assert _snapshot(tmp_path) == before


def test_unsupported_raw_permission_dry_run_reports_manual_without_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, monkeypatch)
    _json(
        root / ".claude/settings.local.json",
        {"permissions": {"deny": ["Bash(git *)"]}},
    )
    before = _snapshot(tmp_path)
    dry = _invoke("migrate", "--to", "dsh", "--dry-run")
    assert "[MANUAL]" in dry.output
    assert "local .claude/settings.local.json" in dry.output
    assert "PERMISSION_UNMAPPED" in dry.output
    assert "arguments" in dry.output
    _invoke("migrate", "--to", "dsh", exit_code=1)
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("command", ["status", "reconcile"])
def test_empty_dsh_manifest_check_creates_no_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    _project(tmp_path, monkeypatch, targets=["dsh"])
    before = _snapshot(tmp_path)
    _invoke(command, *(("--check",) if command == "reconcile" else ()))
    assert _snapshot(tmp_path) == before


def test_deleted_local_skill_retirement_preserves_foreign_output_and_profiles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, monkeypatch)
    source = _skill(root / ".claude", "local")
    _invoke("migrate", "--to", "dsh")
    foreign = _write(root / ".dsh/skills/foreign/SKILL.md", "Foreign\n")
    profile = _write(root / ".dsh/profiles/user/cordis.yml", "Profile\n")
    shutil.rmtree(source.parent)
    before = _snapshot(tmp_path)
    _invoke("status", exit_code=1)
    _invoke("reconcile", "--check", exit_code=1)
    assert _snapshot(tmp_path) == before
    _invoke("reconcile")
    assert not (root / ".dsh/skills/local").exists()
    assert foreign.read_bytes() == b"Foreign\n"
    assert profile.read_bytes() == b"Profile\n"
    _invoke("reconcile", "--check")


@pytest.mark.parametrize("targets", [["codex"], ["claude"], [], ["unknown"]])
def test_empty_non_dsh_manifest_retains_no_packages_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, targets: list[str]
) -> None:
    root = _project(tmp_path, monkeypatch, targets=targets)
    before = _snapshot(tmp_path)
    result = _invoke("status")
    assert "No packages installed" in result.output
    assert "DSH target" not in result.output
    assert not (root / ".codex").exists()
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("scope", ["project", "global"])
def test_disabled_own_dsh_catalog_is_reported_and_retired_without_foreign_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scope: str
) -> None:
    root = _project(tmp_path, monkeypatch, ["@alpha"], ["dsh"])
    _domain(tmp_path / "storage/catalog")
    args = ("-g",) if scope == "global" else ()
    if scope == "global":
        manifest_path = tmp_path / "storage/global.json"
        _json(manifest_path, {"packages": ["@alpha"], "targets": ["dsh"]})
        layout = global_layout()
    else:
        manifest_path = root / "ai-dotfiles.json"
        layout = project_layout(root)
    _invoke("install", *args)
    foreign = _write(layout.skills_dir / "foreign/SKILL.md", "Foreign\n")
    profile = _write(layout.dsh_dir / "profiles/user/cordis.yml", "Profile\n")
    _json(manifest_path, {"packages": [], "targets": ["claude"]})
    before = _snapshot(tmp_path)
    assert "retired" in _invoke("status", *args, exit_code=1).output
    _invoke("reconcile", *args, "--check", exit_code=1)
    assert _snapshot(tmp_path) == before
    _invoke("reconcile", *args)
    assert read_dsh_inventory(layout).records == {}
    assert foreign.read_bytes() == b"Foreign\n"
    assert profile.read_bytes() == b"Profile\n"
    _invoke("reconcile", *args, "--check")


@pytest.mark.parametrize("changed", ["original", "copies", "registry"])
def test_registered_manifest_exception_keeps_fresh_original_and_ownership_guards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed: str
) -> None:
    root = _project(tmp_path, monkeypatch)
    original = _rule(root / ".claude/rules/shared.md")
    _invoke("migrate", "--to", "dsh")
    inputs = collect_dsh_local_inputs(root, manifest_packages=["rule:shared"])
    assert original in [action.source for action in inputs.actions]
    if changed == "original":
        _write(original, original.read_text() + "Fresh edit\n")
    elif changed == "copies":
        save_copy_ownership(root / ".claude", {"rules/shared.md"})
    else:
        path = project_layout(root).local_registry_path
        _write(path, path.read_text() + "\n")
    before = _snapshot(tmp_path)
    with pytest.raises(LinkError, match="original/ownership changed"):
        verify_dsh_local_inputs(inputs)
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("scope", ["project", "global"])
def test_stock_gitflow_catalog_lifecycle_is_reported_idempotent_and_owned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scope: str
) -> None:
    from tests.integration.test_dsh_gitflow import copy_stock_catalog

    root = _project(tmp_path, monkeypatch, ["@gitflow", "@python"], ["dsh"])
    copy_stock_catalog(tmp_path / "storage/catalog")
    args = ("-g",) if scope == "global" else ()
    manifest = (
        tmp_path / "storage/global.json"
        if scope == "global"
        else root / "ai-dotfiles.json"
    )
    _json(manifest, {"packages": ["@gitflow", "@python"], "targets": ["dsh"]})
    first = _invoke("install", *args, "--no-gitignore")
    assert "HOOK_GITFLOW_POLICY_FALLBACK" in first.output
    layout = global_layout() if scope == "global" else project_layout(root)
    hooks = json.loads(layout.hooks_path.read_bytes())
    assert hooks["hooks"] == {}
    config = json.loads(layout.config_path.read_bytes())
    bridge = next(row for row in config["rows"] if row["id"] == "ai-dotfiles-bridge")
    assert len([r for r in bridge["config"]["rules"] if r["name"] == "gitflow"]) == 1
    agent = next(
        row
        for row in config["rows"]
        if row["id"] == "ai-dotfiles-agent-git-workflow-assistant"
    )
    assert "agentOptions" not in agent["config"]
    assert config["permissions"]["deny"] == config["permissions"]["ask"] == []
    foreign = _write(layout.dsh_dir / "profiles/user/cordis.yml", "User profile\n")
    before = _snapshot(tmp_path)
    _invoke("install", *args, "--no-gitignore")
    _invoke("reconcile", *args, "--check")
    _invoke("reconcile", *args)
    assert _snapshot(tmp_path) == before
    _json(manifest, {"packages": [], "targets": ["dsh"]})
    _invoke("reconcile", *args)
    assert not layout.hooks_path.exists()
    assert read_dsh_inventory(layout).records == {}
    assert foreign.read_bytes() == b"User profile\n"
    _invoke("reconcile", *args, "--check")


def test_stock_gitflow_migration_preserves_claude_codex_and_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.integration.test_dsh_gitflow import copy_stock_catalog

    root = _project(tmp_path, monkeypatch, ["@gitflow", "@python"], ["claude", "codex"])
    copy_stock_catalog(tmp_path / "storage/catalog")
    _invoke("install", "--no-gitignore")
    _json(
        root / "ai-dotfiles.json",
        {"packages": ["@gitflow", "@python"], "targets": ["claude", "codex", "dsh"]},
    )
    original_claude = _snapshot(root / ".claude")
    original_codex = _snapshot(root / ".codex")
    original_home = _snapshot(tmp_path / "home")
    before = _snapshot(tmp_path)
    preview = _invoke("migrate", "--to", "dsh", "--dry-run")
    assert "Activation: READY for apply" in preview.output
    assert "[BLOCKER]" not in preview.output
    assert preview.output.count("ALLOW_UNMAPPED") == 55
    assert preview.output.count("HOOK_GITFLOW_POLICY_FALLBACK") == 2
    assert "per-command hook nudge is absent" in preview.output
    assert _snapshot(tmp_path) == before
    applied = _invoke("migrate", "--to", "dsh")
    assert "HOOK_GITFLOW_POLICY_FALLBACK" in applied.output
    assert json.loads(project_layout(root).hooks_path.read_bytes())["hooks"] == {}
    assert _snapshot(root / ".claude") == original_claude
    assert _snapshot(root / ".codex") == original_codex
    assert _snapshot(tmp_path / "home") == original_home
    after = _snapshot(tmp_path)
    _invoke("migrate", "--to", "dsh")
    _invoke("reconcile", "--check")
    assert _snapshot(tmp_path) == after


@pytest.mark.parametrize(
    "failure",
    [
        "script-changed",
        "script-missing",
        "rule-changed",
        "rule-missing",
        "rule-scoped",
        "agent-missing",
        "agent-manual",
        "local-origin",
        "unrelated-if",
        "deny",
        "ask",
    ],
)
def test_stock_fallback_negative_preview_and_refused_apply_are_write_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    from tests.integration.test_dsh_gitflow import copy_stock_catalog

    root = _project(tmp_path, monkeypatch, ["@gitflow", "@python"], ["dsh"])
    catalog = tmp_path / "storage/catalog"
    copy_stock_catalog(catalog)
    domain = catalog / "gitflow"
    script = domain / "hooks/route-to-agent.sh"
    rule = domain / "rules/gitflow.md"
    agent = domain / "agents/git-workflow-assistant.md"
    if failure == "script-changed":
        _write(script, script.read_text() + "\nexit 2\n")
    elif failure == "script-missing":
        script.unlink()
    elif failure == "rule-changed":
        _write(
            rule,
            rule.read_text().replace(
                "invoke `git-workflow-assistant`", "mutate directly"
            ),
        )
    elif failure == "rule-missing":
        rule.unlink()
    elif failure == "rule-scoped":
        _write(rule, "---\npaths: [src/**]\n---\n" + rule.read_text())
    elif failure == "agent-missing":
        agent.unlink()
    elif failure == "agent-manual":
        _write(
            agent,
            agent.read_text().replace("model: sonnet", "model: sonnet\ntools: Task"),
        )
    elif failure == "local-origin":
        _json(
            root / ".claude/settings.local.json",
            json.loads((domain / "settings.fragment.json").read_text()),
        )
    elif failure == "unrelated-if":
        _json(
            root / ".claude/settings.local.json",
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "exit 2",
                                    "if": "Bash(other *)",
                                }
                            ],
                        }
                    ]
                }
            },
        )
    else:
        _json(
            root / ".claude/settings.local.json",
            {"permissions": {failure: ["Bash(git *)"]}},
        )
    before = _snapshot(tmp_path)
    dry = _invoke("migrate", "--to", "dsh", "--dry-run")
    assert "[BLOCKER]" in dry.output
    assert "[LIMITATION]" in dry.output
    assert "Activation: BLOCKED" in dry.output
    assert "Re-run without --dry-run to apply" not in dry.output
    assert _snapshot(tmp_path) == before
    refused = _invoke("migrate", "--to", "dsh", exit_code=1)
    assert "Cannot activate local DSH migration" in refused.output
    assert _snapshot(tmp_path) == before


def test_changed_stock_source_refusal_preserves_existing_outputs_and_ownership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.integration.test_dsh_gitflow import copy_stock_catalog

    root = _project(tmp_path, monkeypatch, ["@gitflow", "@python"], ["dsh"])
    catalog = tmp_path / "storage/catalog"
    copy_stock_catalog(catalog)
    _json(root / ".claude/settings.local.json", {"env": {"LOCAL": "preserved"}})
    _invoke("migrate", "--to", "dsh")
    script = catalog / "gitflow/hooks/route-to-agent.sh"
    _write(script, script.read_text() + "\nexit 2\n")
    before = _snapshot(tmp_path)
    dry = _invoke("migrate", "--to", "dsh", "--dry-run")
    assert "Activation: BLOCKED" in dry.output
    _invoke("migrate", "--to", "dsh", exit_code=1)
    _invoke("install", "--no-gitignore", exit_code=1)
    _invoke("reconcile", "--check", exit_code=1)
    _invoke("reconcile", exit_code=1)
    assert _snapshot(tmp_path) == before
