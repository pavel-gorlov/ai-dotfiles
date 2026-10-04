"""Fresh originals, guarded project migration and zero-write dry-run evidence."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from ai_dotfiles.core import mcp_ownership, settings_ownership
from ai_dotfiles.core.claude_copy import copy_element
from ai_dotfiles.core.dsh_install import collect_dsh_elements
from ai_dotfiles.core.dsh_layout import global_layout, project_layout
from ai_dotfiles.core.dsh_local_registry import (
    DshLocalRegistry,
    load_dsh_local_registry,
    validate_dsh_local_registry,
)
from ai_dotfiles.core.dsh_migrate import (
    collect_dsh_local_inputs,
    migrate_to_dsh,
    plan_dsh_migration,
    verify_dsh_local_inputs,
)
from ai_dotfiles.core.dsh_native import native_frontmatter, resolve_dsh_runtime
from ai_dotfiles.core.elements import parse_element
from ai_dotfiles.core.errors import ConfigError, LinkError
from ai_dotfiles.core.settings_merge import hook_signature
from ai_dotfiles.core.shared_instructions import project_instruction_plan
from tests.integration.test_dsh_bridge import _env
from tests.integration.test_dsh_bridge import (
    bridge_native_runtime as _bridge_native_runtime,
)

bridge_native_runtime = _bridge_native_runtime
pytestmark = pytest.mark.integration


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode())
    return path


def _json(path: Path, value: object) -> Path:
    return _write(path, json.dumps(value))


def _skill(
    root: Path, name: str = "local", extra: str = "", body: str = "Literal {{value}}\n"
) -> Path:
    return _write(
        root / ".claude/skills" / name / "SKILL.md",
        f"---\nname: {name}\ndescription: A local skill\n{extra}---\n{body}",
    )


def _agent(root: Path, name: str = "local", extra: str = "") -> Path:
    return _write(
        root / ".claude/agents" / f"{name}.md",
        f"---\nname: {name}\ndescription: Literal {{description}}\n{extra}---\n"
        "  Persona {{literal}}\n",
    )


def _command(
    root: Path,
    name: str = "local-command",
    extra: str = "disable-model-invocation: true\n",
    body: str = "Explain this code.\n",
) -> Path:
    return _write(
        root / ".claude/commands" / f"{name}.md",
        f"---\nname: {name}\ndescription: An explicit command\n{extra}---\n{body}",
    )


def _snapshot(root: Path) -> dict[str, tuple[str, int, int, str]]:
    return {
        str(path.relative_to(root)): (
            "link" if path.is_symlink() else "dir" if path.is_dir() else "file",
            path.lstat().st_mtime_ns,
            path.lstat().st_mode,
            (
                str(path.readlink())
                if path.is_symlink()
                else (
                    hashlib.sha256(path.read_bytes()).hexdigest()
                    if path.is_file()
                    else ""
                )
            ),
        )
        for path in root.rglob("*")
    }


@pytest.mark.parametrize("mode", ["link", "copy"])
def test_migration_preserves_whole_skill_and_literal_agent_rule_sources(
    tmp_path: Path, tmp_storage: Path, mode: str
) -> None:
    skill = _skill(tmp_path)
    script = _write(skill.parent / "scripts/run.sh", "#!/bin/sh\nexit 0\n")
    script.chmod(0o755)
    agent = _agent(tmp_path, extra="tools: Read, Bash\nmodel: sonnet\n")
    rule = _write(
        tmp_path / ".claude/rules/shared.md",
        "---\nalways_on: true\n---\n# Shared rule\n",
    )
    literal = _write(
        tmp_path / ".claude/rules/literal.md",
        "---\ndescription: Literal rule\n---\n  {{rule}}\n",
    )
    _write(tmp_path / "AGENTS.md", "User instructions\n")
    original = {
        path: path.read_bytes() for path in (skill, agent, rule, literal, script)
    }

    report = migrate_to_dsh(tmp_path, mode=mode)

    assert report.changed_paths
    assert {action.classification for action in report.actions} == {
        "MECHANICAL",
        "REFACTOR",
    }
    installed = tmp_path / ".dsh/skills/local"
    assert installed.is_symlink() == (mode == "link")
    assert (installed / "SKILL.md").read_bytes() == original[skill]
    assert (installed / "scripts/run.sh").stat().st_mode & 0o111
    row = next(
        row for row in report.plan.config.rows if row["id"] == "ai-dotfiles-agent-local"
    )
    assert row["config"]["persona"] == "  Persona {{literal}}\n"
    assert row["config"]["toolFilter"]["allow"] == ["read", "read_image", "bash"]
    assert "User instructions" in (tmp_path / "AGENTS.md").read_text()
    assert (tmp_path / "AGENTS.md").read_text().count("rule:shared START") == 1
    registry = load_dsh_local_registry(tmp_path)
    assert registry.rule_blocks == {"AGENTS.md": ["shared"]}
    assert set(registry.sources) == {
        str(path.relative_to(tmp_path)) for path in (skill, agent, rule, literal)
    }
    for key, record in registry.sources.items():
        assert (
            record["source_sha256"]
            == hashlib.sha256((tmp_path / key).read_bytes()).hexdigest()
        )
        assert record["outputs"]
        assert record["output_generators"]
    assert {path: path.read_bytes() for path in original} == original
    assert migrate_to_dsh(tmp_path, mode=mode).changed_paths == ()


def test_dry_run_writes_nothing_including_existing_profiles_and_snapshots(
    tmp_path: Path, tmp_storage: Path
) -> None:
    _skill(tmp_path)
    _agent(tmp_path)
    _command(tmp_path)
    _json(
        tmp_path / ".claude/settings.json",
        {"env": {"LOCAL_VALUE": "user"}, "permissions": {"deny": ["Bash"]}},
    )
    _json(
        tmp_path / ".claude/settings.local.json", {"env": {"LOCAL_VALUE": "override"}}
    )
    _json(
        tmp_path / ".mcp.json",
        {
            "mcpServers": {
                "local": {
                    "command": "fixture-mcp",
                    "args": ["literal"],
                    "env": {"TOKEN": "fixture"},
                }
            }
        },
    )
    _write(tmp_path / "home/profiles/custom/cordis.yml", "User profile sentinel")
    _write(tmp_path / "home/sentinel", "User home sentinel")
    before = _snapshot(tmp_path)

    report = migrate_to_dsh(tmp_path, dry_run=True)

    assert report.dry_run and not report.changed_paths
    assert _snapshot(tmp_path) == before
    assert report.plan.config.environment == {"LOCAL_VALUE": "override"}
    assert report.plan.config.permissions.deny == ("bash",)
    assert any(part.name == "mcp:local" for part in report.plan.config.contributions)
    assert not (tmp_path / ".dsh").exists()


@pytest.mark.parametrize(
    "restriction",
    [
        "tools: Agent\n",
        "disallowedTools: Bash(npm *)\n",
        "permissionMode: bypassPermissions\n",
    ],
)
def test_unsupported_agent_restriction_is_manual_and_never_unrestricted(
    tmp_path: Path, tmp_storage: Path, restriction: str
) -> None:
    source = _agent(tmp_path, extra=restriction)

    report = migrate_to_dsh(tmp_path)

    action = report.actions[0]
    assert action.source == source and action.classification == "MANUAL"
    assert action.diagnostics and all(
        item.origin == "local" and item.field and item.reason
        for item in action.diagnostics
    )
    assert not report.plan.install.ready_agents
    assert not any(
        row["id"] == "ai-dotfiles-agent-local" for row in report.plan.config.rows
    )
    assert (
        load_dsh_local_registry(tmp_path).sources[str(source.relative_to(tmp_path))][
            "status"
        ]
        == "MANUAL"
    )


@pytest.mark.parametrize(
    "metadata", ['paths: ["**/*.py"]\n', 'paths: ["**/*.py"]\nalways_on: true\n']
)
def test_path_scoped_rule_remains_manual_without_shared_or_literal_activation(
    tmp_path: Path, tmp_storage: Path, metadata: str
) -> None:
    _write(
        tmp_path / ".claude/rules/scoped.md",
        f"---\n{metadata}---\nScoped instruction\n",
    )

    report = migrate_to_dsh(tmp_path)

    assert report.actions[0].classification == "MANUAL"
    assert report.actions[0].diagnostics[0].field == "paths"
    assert (
        not report.plan.install.shared_rules and not report.plan.install.literal_rules
    )
    assert not (tmp_path / "AGENTS.md").exists()


@pytest.mark.parametrize(
    "body", ["!`git status`", "Use $ARGUMENTS", "Use $1", "Read @config.json"]
)
def test_commands_with_execution_or_import_semantics_are_manual(
    tmp_path: Path, tmp_storage: Path, body: str
) -> None:
    _command(tmp_path, body=body)
    report = migrate_to_dsh(tmp_path)
    assert report.actions[0].classification == "MANUAL"
    assert not (tmp_path / ".dsh/skills/local-command.md").exists()


@pytest.mark.parametrize(
    "extra",
    [
        "",
        "disable-model-invocation: false\n",
        "allowed-tools: Bash\ndisable-model-invocation: true\n",
    ],
)
def test_commands_need_explicit_faithful_on_demand_semantics(
    tmp_path: Path, tmp_storage: Path, extra: str
) -> None:
    _command(tmp_path, extra=extra)
    report = migrate_to_dsh(tmp_path)
    assert report.actions[0].classification == "MANUAL"
    assert not (tmp_path / ".dsh/skills/local-command.md").exists()


def test_explicit_on_demand_command_becomes_original_flat_native_skill(
    tmp_path: Path, tmp_storage: Path
) -> None:
    command = _command(tmp_path, body="Contact person@example.com.\n{{literal}}\n")
    report = migrate_to_dsh(tmp_path)
    assert report.actions[0].classification == "MECHANICAL"
    assert (
        tmp_path / ".dsh/skills/local-command.md"
    ).read_bytes() == command.read_bytes()
    registry = load_dsh_local_registry(tmp_path)
    assert set(registry.sources[str(command.relative_to(tmp_path))]["outputs"]) == {
        "skills/local-command.md",
        "ai-dotfiles/config.json",
        "ai-dotfiles/patch.json",
    }


def test_owned_settings_mcp_expose_fresh_projection_and_ledger_guard_without_duplicates(
    tmp_path: Path, tmp_storage: Path
) -> None:
    owned_hook = {"hooks": [{"type": "command", "command": "catalog-handler"}]}
    local_hook = {"hooks": [{"type": "command", "command": "local-handler"}]}
    settings = _json(
        tmp_path / ".claude/settings.json",
        {
            "permissions": {"deny": ["Read", "Bash"]},
            "hooks": {"PreToolUse": [owned_hook, local_hook]},
        },
    )
    settings_ownership.save_settings_ownership(
        tmp_path / ".claude",
        {
            "permissions_deny": ["Read"],
            "hooks_signatures": [hook_signature(owned_hook)],
        },
    )
    mcp = _json(
        tmp_path / ".mcp.json",
        {
            "mcpServers": {
                "catalog": {"command": "catalog-server"},
                "local": {"command": "local-server"},
            }
        },
    )
    mcp_ownership.save_ownership(tmp_path / ".claude", {"catalog": ["@domain"]})
    before = _snapshot(tmp_path)

    report = migrate_to_dsh(tmp_path, dry_run=True)

    assert _snapshot(tmp_path) == before
    sources = {source.path: source for source in report.plan.inputs.raw_sources}
    assert sources[settings].value == {
        "permissions": {"deny": ["Bash"]},
        "hooks": {"PreToolUse": [local_hook]},
    }
    assert sources[mcp].value == {"mcpServers": {"local": {"command": "local-server"}}}
    assert all(source.requires_value_input for source in sources.values())
    assert all(len(source.guards) == 2 for source in sources.values())
    assert not report.plan.inputs.config_sources
    assert all(
        action.classification == "REFACTOR" and action.status == "HELD"
        for action in report.actions
    )
    assert all(item.code == "LOCAL_VALUE_INPUT_PENDING" for item in report.diagnostics)
    with pytest.raises(ConfigError, match="guarded in-memory projection"):
        migrate_to_dsh(tmp_path)
    assert _snapshot(tmp_path) == before


def test_aggregate_env_has_precise_unproven_origin_and_is_never_user_only(
    tmp_path: Path, tmp_storage: Path
) -> None:
    _json(
        tmp_path / ".claude/settings.json",
        {"env": {"VALUE": "ambiguous"}, "permissions": {"deny": ["Bash"]}},
    )
    settings_ownership.save_settings_ownership(
        tmp_path / ".claude", {"permissions_deny": []}
    )
    report = migrate_to_dsh(tmp_path, dry_run=True)
    source = report.plan.inputs.raw_sources[0]
    assert source.unproven_fields == ("env",)
    assert report.actions[0].classification == "MANUAL"
    assert report.plan.config.environment == {}
    assert any(
        item.code == "LOCAL_ORIGINAL_UNPROVEN" and item.field == "env"
        for item in report.diagnostics
    )


@pytest.mark.parametrize("change", ["original", "ledger", "projection", "new-ledger"])
def test_fresh_source_and_ownership_guards_reject_changes_before_outputs(
    tmp_path: Path, tmp_storage: Path, change: str
) -> None:
    settings = _json(
        tmp_path / ".claude/settings.json", {"permissions": {"deny": ["Bash"]}}
    )
    if change != "new-ledger":
        settings_ownership.save_settings_ownership(
            tmp_path / ".claude", {"permissions_deny": []}
        )
    inputs = collect_dsh_local_inputs(tmp_path)
    if change == "original":
        _json(settings, {"permissions": {"deny": ["Read"]}})
    elif change == "projection":
        inputs.raw_sources[0].value["permissions"] = {}
    else:
        settings_ownership.save_settings_ownership(
            tmp_path / ".claude", {"permissions_deny": ["Bash"]}
        )
    with pytest.raises(LinkError, match="changed"):
        verify_dsh_local_inputs(inputs)
    assert not (tmp_path / ".dsh").exists()


def test_single_combined_hooks_preserves_settings_local_and_standalone_handlers(
    tmp_path: Path, tmp_storage: Path
) -> None:
    for filename, command in (
        ("settings.json", "first"),
        ("settings.local.json", "second"),
        ("hooks.json", "third"),
    ):
        _json(
            tmp_path / ".claude" / filename,
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Read",
                            "hooks": [{"type": "command", "command": command}],
                        }
                    ]
                }
            },
        )
    report = migrate_to_dsh(tmp_path)
    assert [
        group["hooks"][0]["command"] for group in report.plan.hooks.hooks["PreToolUse"]
    ] == ["first", "second", "third"]
    assert all(
        group["matcher"] == "read|read_image"
        for group in report.plan.hooks.hooks["PreToolUse"]
    )
    assert [part.name for part in report.plan.config.contributions] == ["hooks"]
    assert sum(row["id"] == "ai-dotfiles-hooks" for row in report.plan.config.rows) == 1
    registry = load_dsh_local_registry(tmp_path)
    assert all(
        record["contributions"] == ["hooks"] and record["resources"]
        for record in registry.sources.values()
    )


@pytest.mark.parametrize(
    "value",
    [
        {"permissions": {"deny": ["Bash(npm *)"]}},
        {
            "hooks": {
                "Notification": [{"hooks": [{"type": "command", "command": "ignored"}]}]
            }
        },
        {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Unknown",
                        "hooks": [{"type": "command", "command": "ignored"}],
                    }
                ]
            }
        },
    ],
)
def test_unsupported_config_restrictions_block_all_writes(
    tmp_path: Path, tmp_storage: Path, value: object
) -> None:
    _skill(tmp_path)
    _json(tmp_path / ".claude/settings.json", value)
    before = _snapshot(tmp_path)
    report = migrate_to_dsh(tmp_path, dry_run=True)
    assert report.plan.blocked
    assert any(action.classification == "MANUAL" for action in report.actions)
    assert any(
        item.blocking and item.field and item.reason for item in report.diagnostics
    )
    with pytest.raises(ConfigError, match="Cannot activate"):
        migrate_to_dsh(tmp_path)
    assert _snapshot(tmp_path) == before


def test_catalog_domain_copy_exclusion_and_one_catalog_local_plan(
    tmp_path: Path, tmp_storage: Path
) -> None:
    project = tmp_path / "project"
    catalog = tmp_storage / "catalog"
    _write(
        catalog / "domain/agents/catalog.md",
        "---\nname: catalog\ndescription: Catalog agent\n---\nCatalog persona\n",
    )
    copy_element(parse_element("@domain"), project / ".claude", catalog)
    _agent(project)
    catalog_plan = collect_dsh_elements(
        [parse_element("@domain")], project_layout(project), catalog
    )

    report = migrate_to_dsh(
        project, catalog_plan=catalog_plan, manifest_packages=["@domain"]
    )

    assert [action.element for action in report.actions] == ["agent:local"]
    assert {result.payload.name for result in report.plan.install.ready_agents} == {
        "catalog",
        "local",
    }
    assert (
        sum(row["id"] == "ai-dotfiles-bridge" for row in report.plan.config.rows) == 1
    )
    assert (
        sum(
            output.path == project_layout(project).bridge_path
            for output in report.plan.install.outputs
        )
        == 1
    )
    with pytest.raises(ConfigError, match="fresh merged catalog plan"):
        migrate_to_dsh(project)


def test_same_scope_catalog_local_agent_collision_refuses_before_any_write(
    tmp_path: Path, tmp_storage: Path
) -> None:
    _agent(tmp_path)
    catalog = tmp_storage / "catalog"
    _write(
        catalog / "agents/local.md",
        "---\nname: local\ndescription: Catalog\n---\nPersona\n",
    )
    catalog_plan = collect_dsh_elements(
        [parse_element("agent:local")], project_layout(tmp_path), catalog
    )
    before = _snapshot(tmp_path)
    with pytest.raises(ConfigError, match="name collision"):
        migrate_to_dsh(tmp_path, catalog_plan=catalog_plan)
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "target",
    [
        ".dsh/skills/local",
        ".dsh/ai-dotfiles/config.json",
        ".dsh/ai-dotfiles/local.json",
        ".dsh/ai-dotfiles/bridge.mjs",
    ],
)
def test_foreign_outputs_and_registries_are_preserved(
    tmp_path: Path, tmp_storage: Path, target: str
) -> None:
    _skill(tmp_path)
    _write(tmp_path / target, "Foreign sentinel")
    before = _snapshot(tmp_path)
    with pytest.raises((ConfigError, LinkError)):
        migrate_to_dsh(tmp_path, dry_run=True)
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "target", [".claude/agents", ".claude/skills/local/references", ".dsh/ai-dotfiles"]
)
def test_outside_symlink_sources_resources_and_destinations_refuse(
    tmp_path: Path, tmp_storage: Path, target: str
) -> None:
    project = tmp_path / "project"
    _skill(project)
    outside = tmp_path / "outside"
    _write(outside / "agent.md", "---\nname: agent\ndescription: Outside\n---\nPersona")
    destination = project / target
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.symlink_to(outside)
    before = _snapshot(tmp_path)
    with pytest.raises(LinkError, match="outside|symlinked"):
        migrate_to_dsh(project)
    assert _snapshot(tmp_path) == before


def test_outer_parent_alias_retains_lexical_project_paths(
    tmp_path: Path, tmp_storage: Path
) -> None:
    actual = tmp_path / "actual" / "project"
    _skill(actual)
    alias = tmp_path / "alias"
    alias.symlink_to(actual.parent)
    report = migrate_to_dsh(alias / "project")
    assert report.plan.inputs.layout.project_root == alias / "project"
    assert (actual / ".dsh/skills/local/SKILL.md").read_bytes() == (
        actual / ".claude/skills/local/SKILL.md"
    ).read_bytes()


def test_symlink_at_project_anchor_refuses_before_writes(
    tmp_path: Path, tmp_storage: Path
) -> None:
    actual = tmp_path / "actual"
    _skill(actual)
    alias = tmp_path / "alias"
    alias.symlink_to(actual)
    before = _snapshot(tmp_path)
    with pytest.raises(LinkError, match="symlinked local DSH destination"):
        migrate_to_dsh(alias)
    assert _snapshot(tmp_path) == before


def test_local_migration_refuses_global_layout(
    tmp_path: Path, tmp_storage: Path
) -> None:
    from ai_dotfiles.core.dsh_install import plan_dsh_install

    _skill(tmp_path)
    with pytest.raises(ConfigError, match="project-only"):
        collect_dsh_local_inputs(
            tmp_path, catalog_plan=plan_dsh_install(global_layout(tmp_path / "global"))
        )
    assert not (tmp_path / "global").exists()


def test_removed_originals_remain_retirement_records_and_shared_protection(
    tmp_path: Path, tmp_storage: Path
) -> None:
    skill = _skill(tmp_path)
    rule = _write(
        tmp_path / ".claude/rules/keep.md",
        "---\nalways_on: true\n---\nKeep instruction\n",
    )
    migrate_to_dsh(tmp_path)
    skill.unlink()
    rule.unlink()

    plan = plan_dsh_migration(collect_dsh_local_inputs(tmp_path))

    assert plan.retired_source_keys == {
        str(skill.relative_to(tmp_path)),
        str(rule.relative_to(tmp_path)),
    }
    protected = project_instruction_plan((), (), tmp_path, tmp_storage / "catalog")
    assert protected.protected_blocks[tmp_path / "AGENTS.md"] == {"keep"}
    assert plan.registry.rule_blocks == {"AGENTS.md": ["keep"]}


@pytest.mark.parametrize(
    "field,value",
    [
        ("outputs", ["../escape"]),
        ("resources", ["ai-dotfiles/../../escape"]),
        ("outputs", ["ai-dotfiles/local.json"]),
        ("guards", [{"source": "../outside", "source_sha256": None}]),
        ("source", "../outside"),
        ("source_sha256", "fake"),
    ],
)
def test_registry_rejects_unsafe_source_output_and_guard_metadata(
    tmp_path: Path, tmp_storage: Path, field: str, value: object
) -> None:
    _skill(tmp_path)
    plan = plan_dsh_migration(collect_dsh_local_inputs(tmp_path))
    record = next(iter(plan.registry.sources.values()))
    record[field] = value
    with pytest.raises((ConfigError, LinkError)):
        validate_dsh_local_registry(tmp_path, plan.registry)
    assert not (tmp_path / ".dsh").exists()


def test_registry_snapshot_cannot_mutate_ownership_containers(
    tmp_path: Path, tmp_storage: Path
) -> None:
    registry = DshLocalRegistry({}, {"AGENTS.md": ["safe"]})
    snapshot = registry.snapshot()
    snapshot["rule_blocks"]["AGENTS.md"].append("unsafe")
    assert registry.rule_blocks == {"AGENTS.md": ["safe"]}


def test_native_frontmatter_retry_preserves_deferred_skill_and_original_bytes(
    tmp_path: Path, tmp_storage: Path, bridge_native_runtime: Path
) -> None:
    path = _skill(tmp_path, extra="whenToUse: |\n  Explain multiline\n")
    original = path.read_bytes()
    deferred = collect_dsh_local_inputs(tmp_path)
    assert deferred.install.skills[0].status == "DEFERRED"
    assert deferred.actions[0].classification == "REFACTOR"
    runtime = resolve_dsh_runtime(
        bridge_native_runtime / "node_modules/@deepseek-ai/dsh"
    )
    env = _env(tmp_path)
    before = _snapshot(tmp_path)
    metadata = native_frontmatter(runtime, [path], cwd=tmp_path, env=env)

    report = migrate_to_dsh(tmp_path, native_frontmatter=metadata, dry_run=True)

    assert report.plan.install.skills[0].status == "READY"
    assert report.actions[0].classification == "MECHANICAL"
    assert path.read_bytes() == original
    assert _snapshot(tmp_path) == before


def test_published_native_discovers_flat_command_and_preserves_on_demand_policy(
    tmp_path: Path, tmp_storage: Path, bridge_native_runtime: Path
) -> None:
    source = _command(tmp_path, body="Literal {{command}}\n")
    migrate_to_dsh(tmp_path)
    fixture = tmp_path / "native"
    fixture.mkdir()
    (fixture / "node_modules").symlink_to(bridge_native_runtime / "node_modules")
    _json(
        fixture / "native.json",
        [
            {"id": "skills", "name": "@deepseek-ai/dsh-skill"},
            {
                "id": "filesystem",
                "name": "@deepseek-ai/dsh-skill-filesystem",
                "config": {
                    "includeDefaultRoots": False,
                    "customSkillDirs": [str(tmp_path / ".dsh/skills")],
                    "watch": False,
                },
            },
        ],
    )
    script = _write(
        fixture / "run.mjs",
        r"""
import assert from 'node:assert/strict';
import { boot } from '@deepseek-ai/dsh-app-boot';
import { isModelInvocable, isUserInvocable } from '@deepseek-ai/dsh-skill';
const ctx = await boot('dsh-local-command-test',
  new URL('./native.json', import.meta.url).pathname, undefined, undefined,
  import.meta.url);
try {
  await ctx.loader.await();
  const rows = await ctx.skills.list({ cwd: process.cwd() });
  assert.equal(rows.length, 1);
  assert.equal(rows[0].name, 'local-command');
  assert.equal(isModelInvocable(rows[0]), false);
  assert.equal(isUserInvocable(rows[0]), true);
  const command = await ctx.skills.get('local-command', { cwd: process.cwd() });
  assert.ok(command);
  assert.equal(command.content, 'Literal {{command}}');
  assert.equal(isModelInvocable(command), false);
  assert.equal(isUserInvocable(command), true);
  assert.equal(command.resourceBase.kind, 'directory');
  assert.equal(command.resourceBase.path,
    new URL('../.dsh/skills/', import.meta.url).pathname.replace(/\/$/, ''));
  console.log(JSON.stringify({ discovered: true, modelInvocable: false,
    userInvocable: true, literalBody: true }));
} finally { await ctx.fiber.dispose(); }
""",
    )
    env = _env(fixture)
    before = _snapshot(tmp_path)
    result = subprocess.run(
        ["node", str(script)],
        cwd=fixture,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1]) == {
        "discovered": True,
        "modelInvocable": False,
        "userInvocable": True,
        "literalBody": True,
    }
    assert (
        tmp_path / ".dsh/skills/local-command.md"
    ).read_bytes() == source.read_bytes()
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "value,field",
    [
        ({"permissions": {"allow": ["Bash"]}}, "permissions.allow[0]"),
        ({"customSetting": True}, "customSetting"),
    ],
)
def test_unmapped_nonblocking_settings_classify_refactor_without_granting_access(
    tmp_path: Path, tmp_storage: Path, value: object, field: str
) -> None:
    _json(tmp_path / ".claude/settings.json", value)
    report = migrate_to_dsh(tmp_path)
    assert report.actions[0].classification == "REFACTOR"
    assert any(item.field == field and not item.blocking for item in report.diagnostics)
    assert report.plan.config.permissions.deny == ()
    assert report.plan.config.permissions.ask == ()


@pytest.mark.parametrize(
    "settings,field",
    [
        ({"env": {"DSH_HOME": "outside"}}, "env.DSH_HOME"),
        ({"permissions": {"ask": ["Unknown"]}}, "permissions.ask[0]"),
    ],
)
def test_local_settings_restrictions_and_reserved_environment_are_manual(
    tmp_path: Path, tmp_storage: Path, settings: object, field: str
) -> None:
    _json(tmp_path / ".claude/settings.local.json", settings)
    before = _snapshot(tmp_path)
    report = migrate_to_dsh(tmp_path, dry_run=True)
    assert report.actions[0].classification == "MANUAL"
    assert any(item.field == field and item.blocking for item in report.diagnostics)
    assert _snapshot(tmp_path) == before


def test_local_sse_mcp_transport_is_manual_and_never_changed_to_http(
    tmp_path: Path, tmp_storage: Path
) -> None:
    _json(
        tmp_path / ".mcp.json",
        {"mcpServers": {"legacy": {"type": "sse", "url": "http://localhost:9999/sse"}}},
    )
    report = migrate_to_dsh(tmp_path, dry_run=True)
    assert report.actions[0].classification == "MANUAL"
    assert not report.plan.config.contributions
    assert any(item.field == "mcpServers.legacy.type" for item in report.diagnostics)


def test_local_hook_resources_keep_tree_source_provenance_and_executable_modes(
    tmp_path: Path, tmp_storage: Path
) -> None:
    handler = _write(tmp_path / ".claude/hooks/run.sh", "#!/bin/sh\nexit 0\n")
    handler.chmod(0o751)
    _write(handler.parent / "support.txt", "support sentinel")
    _json(
        tmp_path / ".claude/settings.json",
        {
            "hooks": {
                "PreToolUse": [
                    {
                        "hooks": [
                            {"type": "command", "command": "sh .claude/hooks/run.sh"}
                        ]
                    }
                ]
            }
        },
    )
    report = migrate_to_dsh(tmp_path)
    command = report.plan.hooks.hooks["PreToolUse"][0]["hooks"][0]["command"]
    assert str(tmp_path / ".dsh/ai-dotfiles/resources/hook-origins") in command
    resource = next(
        resource
        for resource in report.plan.hooks.resources
        if resource.source == handler.parent
    )
    target = report.plan.inputs.layout.resources_dir / resource.relative_path
    assert (target / "run.sh").stat().st_mode & 0o777 == 0o751
    assert (target / "support.txt").read_text() == "support sentinel"
    registry = load_dsh_local_registry(tmp_path)
    record = registry.sources[".claude/settings.json"]
    assert (
        str(target.relative_to(report.plan.inputs.layout.dsh_dir))
        in record["resources"]
    )
    assert record["provenance"] and record["output_generators"]


def test_outside_hook_resource_link_is_refused_without_any_migration_write(
    tmp_path: Path, tmp_storage: Path
) -> None:
    project = tmp_path / "project"
    outside = _write(tmp_path / "outside/handler.sh", "#!/bin/sh\nexit 0\n")
    handler = project / ".claude/hooks/handler.sh"
    handler.parent.mkdir(parents=True)
    handler.symlink_to(outside)
    _json(
        project / ".claude/settings.json",
        {
            "hooks": {
                "PreToolUse": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "sh .claude/hooks/handler.sh",
                            }
                        ]
                    }
                ]
            }
        },
    )
    before = _snapshot(tmp_path)
    with pytest.raises(LinkError, match="outside"):
        migrate_to_dsh(project)
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "block_path,names",
    [
        ("../AGENTS.md", ["safe"]),
        ("nested/[glob]/AGENTS.md", ["safe"]),
        ("AGENTS.md", ["unsafe-->name"]),
    ],
)
def test_shared_registry_protection_schema_refuses_unsafe_paths_and_markers(
    tmp_path: Path, tmp_storage: Path, block_path: str, names: list[str]
) -> None:
    registry = DshLocalRegistry({}, {block_path: names})
    with pytest.raises((ConfigError, LinkError)):
        validate_dsh_local_registry(tmp_path, registry)
    assert not (tmp_path / ".dsh").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        (
            "provenance",
            [{"source": "/outside", "source_sha256": "0" * 64, "generator": 1}],
        ),
        ("output_generators", {"../outside": {"render": 1}}),
        ("generator", True),
    ],
)
def test_registry_refuses_mutated_source_and_generator_provenance(
    tmp_path: Path, tmp_storage: Path, field: str, value: object
) -> None:
    _skill(tmp_path)
    plan = plan_dsh_migration(collect_dsh_local_inputs(tmp_path))
    record = next(iter(plan.registry.sources.values()))
    record[field] = value
    with pytest.raises(ConfigError):
        validate_dsh_local_registry(tmp_path, plan.registry)
    assert not (tmp_path / ".dsh").exists()


@pytest.mark.parametrize("kind", ["skill", "command"])
def test_ready_to_manual_source_retains_native_output_custody_for_reconciliation(
    tmp_path: Path, tmp_storage: Path, kind: str
) -> None:
    source = _skill(tmp_path) if kind == "skill" else _command(tmp_path)
    report = migrate_to_dsh(tmp_path)
    previous = load_dsh_local_registry(tmp_path).sources[
        str(source.relative_to(tmp_path))
    ]
    old_native = "skills/local" if kind == "skill" else "skills/local-command.md"
    assert old_native in previous["outputs"]
    source.write_text(
        source.read_text().replace("description:", "allowed-tools: Agent\ndescription:")
    )

    inputs = collect_dsh_local_inputs(tmp_path)
    plan = plan_dsh_migration(inputs)

    current = plan.registry.sources[str(source.relative_to(tmp_path))]
    assert old_native in current["outputs"]
    assert old_native not in current["desired_outputs"]
    assert old_native in plan.retired_output_keys
    assert current["status"] == "MANUAL"
    assert report.plan.inputs.layout == plan.inputs.layout


@pytest.mark.parametrize(
    "relative",
    [
        ".claude/settings.json",
        ".claude/settings.local.json",
        ".mcp.json",
        ".claude/hooks.json",
    ],
)
def test_new_original_json_after_planning_is_rejected_before_any_write(
    tmp_path: Path, tmp_storage: Path, relative: str
) -> None:
    inputs = collect_dsh_local_inputs(tmp_path)
    assert not inputs.raw_sources
    _json(tmp_path / relative, {"permissions": {"deny": ["Bash"]}})
    before = _snapshot(tmp_path)
    with pytest.raises(LinkError, match="source set changed"):
        plan_dsh_migration(inputs)
    assert _snapshot(tmp_path) == before
    assert not (tmp_path / ".dsh").exists()
