"""Required pinned native read-only composition plus bounded config ownership."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Literal

import pytest

from ai_dotfiles.core.dsh_config import (
    DshConfigSource,
    attach_dsh_config_outputs,
    collect_dsh_config_sources,
    collect_dsh_configuration,
    compose_dsh_configuration,
    dsh_config_drift,
    inspect_dsh_configuration,
    read_dsh_config_snapshot,
)
from ai_dotfiles.core.dsh_install import (
    apply_dsh_install,
    collect_dsh_elements,
    plan_dsh_install,
)
from ai_dotfiles.core.dsh_layout import global_layout, project_layout
from ai_dotfiles.core.dsh_native import (
    DshNativeRuntime,
    native_frontmatter,
    resolve_dsh_runtime,
)
from ai_dotfiles.core.dsh_render import render_agent, render_rule, validate_skill
from ai_dotfiles.core.elements import parse_element
from ai_dotfiles.core.errors import ConfigError, LinkError
from tests.integration.test_dsh_bridge import _env
from tests.integration.test_dsh_bridge import (
    bridge_native_runtime as _bridge_native_runtime,
)

bridge_native_runtime = _bridge_native_runtime

pytestmark = pytest.mark.integration
HELPER = (
    Path(__file__).parents[2] / "src/ai_dotfiles/scaffold/templates/dsh_compose.mjs"
)


@pytest.fixture
def runtime(bridge_native_runtime: Path) -> DshNativeRuntime:
    return resolve_dsh_runtime(bridge_native_runtime / "node_modules/@deepseek-ai/dsh")


def snapshot(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


def profile(
    tmp_path: Path,
    rows: list[dict[str, object]] | None = None,
    *,
    bundles: list[str] | None = None,
) -> tuple[Path, Path]:
    directory = tmp_path / "home/profiles/fixture"
    directory.mkdir(parents=True)
    (directory / "package.json").write_text(
        json.dumps({"dsh": {"profile": {"bundles": bundles or []}}})
    )
    (directory / "cordis.patch.yml").write_text(json.dumps([{"insert": rows or []}]))
    (directory / "cordis.yml").write_text(
        "User sentinel; never rewritten by inspection\n"
    )
    (tmp_path / "home/sentinel").write_text("User home sentinel\n")
    return directory, tmp_path / "home"


def source(
    tmp_path: Path,
    value: object,
    kind: Literal["settings", "mcp", "native"] = "settings",
    name: str = "source",
) -> DshConfigSource:
    path = tmp_path / (name + ".json")
    path.write_text(json.dumps(value))
    return DshConfigSource(
        path, kind, "project", "@" + name, "@" + name, tmp_path / "bound"
    )


def compose(
    tmp_path: Path,
    runtime: DshNativeRuntime,
    *,
    rows: list[dict[str, object]] | None = None,
    sources: list[DshConfigSource] | None = None,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    directory, home = profile(tmp_path, rows)
    config = compose_dsh_configuration(
        collect_dsh_configuration(sources or [], project_layout(tmp_path))
    )
    before = snapshot(tmp_path)
    result = inspect_dsh_configuration(
        config,
        runtime,
        profile_dir=directory,
        home=home,
        cwd=tmp_path,
        process_env=_env(tmp_path),
        **(extra or {}),
    )
    assert snapshot(tmp_path) == before
    return result


def test_required_native_probe_profile_order_and_full_config_replacement(
    tmp_path: Path, runtime: DshNativeRuntime
) -> None:
    rows = [
        {
            "id": "foreign",
            "name": "fixture-unimported",
            "config": {"keep": "profile", "removed": "yes"},
        }
    ]
    directory, home = profile(tmp_path, rows)
    (home / "cordis.patch.yml").write_text(
        json.dumps([{"id": "foreign", "config": {"home": True}}])
    )
    domain = source(tmp_path, [{"id": "foreign", "config": {"domain": True}}], "native")
    cli = tmp_path / "cli.json"
    cli.write_text(json.dumps([{"id": "foreign", "config": {"cli": True}}]))
    config = compose_dsh_configuration(
        collect_dsh_configuration([domain], project_layout(tmp_path))
    )
    before = snapshot(tmp_path)
    result = inspect_dsh_configuration(
        config,
        runtime,
        profile_dir=directory,
        home=home,
        cwd=tmp_path,
        process_env=_env(tmp_path),
        cli_patch_files=[cli],
    )
    assert next(
        row["config"] for row in result["entries"] if row["id"] == "foreign"
    ) == {"cli": True}
    assert result["selection"] == {"kind": "global"}
    assert snapshot(tmp_path) == before
    assert (directory / "cordis.yml").read_text().startswith("User sentinel")


def test_native_retired_bundle_is_refused_before_manifest_write(
    tmp_path: Path, runtime: DshNativeRuntime
) -> None:
    directory, home = profile(
        tmp_path, bundles=["@deepseek-ai/dsh-experimental-schedule-bundle"]
    )
    before = snapshot(tmp_path)
    config = compose_dsh_configuration(
        collect_dsh_configuration([], project_layout(tmp_path))
    )
    with pytest.raises(ConfigError, match="rewrite package.json"):
        inspect_dsh_configuration(
            config,
            runtime,
            profile_dir=directory,
            home=home,
            cwd=tmp_path,
            process_env=_env(tmp_path),
        )
    assert snapshot(tmp_path) == before


def test_missing_profile_refuses_without_initialization(
    tmp_path: Path, runtime: DshNativeRuntime
) -> None:
    config = compose_dsh_configuration(
        collect_dsh_configuration([], project_layout(tmp_path))
    )
    directory = tmp_path / "missing/profile"
    with pytest.raises(ConfigError, match="package.json"):
        inspect_dsh_configuration(
            config,
            runtime,
            profile_dir=directory,
            home=tmp_path / "home",
            cwd=tmp_path,
            process_env=_env(tmp_path),
        )
    assert not directory.exists()


def test_native_frontmatter_retries_block_escaped_nested_skill_agent_rule(
    tmp_path: Path, runtime: DshNativeRuntime
) -> None:
    catalog = tmp_path / "catalog"
    skill = catalog / "skills/skill/SKILL.md"
    agent = catalog / "agents/agent.md"
    rule = catalog / "rules/rule.md"
    for path in (skill, agent, rule):
        path.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text(
        "---\nname: skill\ndescription: |\n  Multiline native\n"
        "  description {{ literal }}\nmetadata:\n  constructor: allowed\n"
        "  nested:\n    passive: yes\n---\nFull skill body\n"
    )
    agent.write_text(
        '---\nname: agent\ndescription: "escaped\\x0Avalue"\n---\nLiteral {{ agent }}\n'
    )
    rule.write_text(
        "---\ndescription: |\n  Literal native rule\n---\nRule {{ body }}\n"
    )
    assert validate_skill(skill).status == "DEFERRED"
    assert render_agent(agent).status == "DEFERRED"
    assert render_rule(rule).status == "DEFERRED"
    before = snapshot(catalog)
    metadata = native_frontmatter(
        runtime, [skill, agent, rule], cwd=tmp_path, env=_env(tmp_path)
    )
    assert (
        metadata[skill]["description"]
        == "Multiline native\ndescription {{ literal }}\n"
    )
    assert metadata[skill]["metadata"]["constructor"] == "allowed"
    assert metadata[agent]["description"] == "escaped\nvalue"
    plan = collect_dsh_elements(
        [
            parse_element("skill:skill"),
            parse_element("agent:agent"),
            parse_element("rule:rule"),
        ],
        project_layout(tmp_path),
        catalog,
        native_frontmatter=metadata,
    )
    assert [item.status for item in (*plan.skills, *plan.agents, *plan.rules)] == [
        "READY",
        "READY",
        "READY",
    ]
    assert plan.agents[0].payload.persona == "Literal {{ agent }}\n"
    assert snapshot(catalog) == before


@pytest.mark.parametrize(
    "raw",
    [
        "---\nname: [invalid\n---\nbody",
        "---\n- not mapping\n---\nbody",
        "body without YAML",
    ],
)
def test_native_frontmatter_invalid_is_precise_not_placeholder(
    tmp_path: Path, runtime: DshNativeRuntime, raw: str
) -> None:
    path = tmp_path / "SKILL.md"
    path.write_text(raw)
    with pytest.raises(ConfigError, match="frontmatter"):
        native_frontmatter(runtime, [path], cwd=tmp_path, env=_env(tmp_path))


@pytest.mark.parametrize(
    "row",
    [
        {"id": "ai-dotfiles-bridge", "name": "foreign"},
        {
            "id": "foreign",
            "name": "foreign",
            "config": {"toolName": "ai_dotfiles_agent_helper"},
        },
        {"id": "foreign", "name": "foreign", "config": {"serverName": "server"}},
    ],
)
def test_foreign_user_id_tool_server_collision_stops_activation(
    tmp_path: Path, runtime: DshNativeRuntime, row: dict[str, object]
) -> None:
    directory, home = profile(tmp_path, [row])
    path = tmp_path / "agent.md"
    path.write_text("---\nname: helper\ndescription: Helper\n---\nLiteral\n")
    install = plan_dsh_install(project_layout(tmp_path), agents=[render_agent(path)])
    config = compose_dsh_configuration(
        collect_dsh_configuration(
            [
                source(
                    tmp_path, {"mcpServers": {"server": {"command": "unused"}}}, "mcp"
                )
            ],
            project_layout(tmp_path),
        ),
        [install],
    )
    before = snapshot(tmp_path)
    with pytest.raises(ConfigError, match="collides"):
        inspect_dsh_configuration(
            config,
            runtime,
            profile_dir=directory,
            home=home,
            cwd=tmp_path,
            process_env=_env(tmp_path),
        )
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "row",
    [
        {
            "id": "foreign",
            "name": "foreign",
            "config": {"toolName": {"__jsExpr": "process.env.TOOL"}},
        },
        {
            "id": "foreign",
            "name": "foreign",
            "config": {"__jsExpr": "({serverName:'managed'})"},
        },
        {"id": {"__jsExpr": "'id'"}, "name": "foreign"},
    ],
)
def test_native_dynamic_identity_conflict_is_not_evaluated(
    tmp_path: Path, runtime: DshNativeRuntime, row: dict[str, object]
) -> None:
    with pytest.raises(ConfigError, match="expression|literal"):
        compose(tmp_path, runtime, rows=[row])


def test_actual_native_stdio_http_config_schema_preserves_headers(
    tmp_path: Path, runtime: DshNativeRuntime
) -> None:
    mcp = source(
        tmp_path,
        {
            "mcpServers": {
                "stdio": {
                    "command": "unused",
                    "args": ["./literal"],
                    "env": {"TOKEN": "local"},
                },
                "http": {
                    "type": "http",
                    "url": "http://127.0.0.1:1/mcp",
                    "headers": {"constructor": "./literal"},
                },
            }
        },
        "mcp",
    )
    result = compose(tmp_path, runtime, sources=[mcp])
    rows = {row["id"]: row for row in result["entries"]}
    assert rows["ai-dotfiles-mcp-http"]["config"]["headers"] == {
        "constructor": "./literal"
    }
    assert rows["ai-dotfiles-mcp-stdio"]["config"]["args"] == ["./literal"]
    assert set(rows["ai-dotfiles-audit"]["config"]["requiredIds"]) >= {
        "ai-dotfiles-mcp-stdio",
        "ai-dotfiles-mcp-http",
    }


def test_preset_one_aggregate_preserves_provider_configuration_and_native_fields(
    tmp_path: Path, runtime: DshNativeRuntime
) -> None:
    result = compose(
        tmp_path,
        runtime,
        rows=[
            {
                "id": "registry",
                "name": "@deepseek-ai/dsh-agent-preset-registry",
                "config": {"default": "parent"},
            },
            {
                "id": "preset",
                "name": "@deepseek-ai/dsh-agent-preset",
                "config": {
                    "id": "parent",
                    "name": "User parent",
                    "description": "Literal {{ user }}",
                    "plugins": [
                        {
                            "id": "skills",
                            "name": "@deepseek-ai/dsh-skill-filesystem",
                            "config": {
                                "customSkillDirs": ["/user/skills"],
                                "watch": False,
                            },
                        }
                    ],
                },
            },
        ],
    )
    assert result["selection"] == {
        "kind": "preset",
        "id": "parent",
        "entryId": "preset",
    }
    assert not any(row["id"] == "ai-dotfiles-bridge" for row in result["entries"])
    preset = next(row for row in result["entries"] if row["id"] == "preset")
    assert preset["config"]["description"] == "Literal {{ user }}"
    assert preset["config"]["plugins"][0]["config"] == {
        "customSkillDirs": ["/user/skills"],
        "watch": False,
    }
    group = next(
        row for row in preset["config"]["plugins"] if row["id"] == "ai-dotfiles-managed"
    )
    assert [row["id"] for row in group["config"]].count("ai-dotfiles-bridge") == 1


@pytest.mark.parametrize("scope", ["global", "preset"])
def test_native_routes_update_bridge_preserving_literal_and_filters(
    tmp_path: Path, runtime: DshNativeRuntime, scope: str
) -> None:
    rows: list[dict[str, object]] = []
    if scope == "preset":
        rows = [
            {
                "id": "registry",
                "name": "@deepseek-ai/dsh-agent-preset-registry",
                "config": {"default": "parent"},
            },
            {
                "id": "preset",
                "name": "@deepseek-ai/dsh-agent-preset",
                "config": {"id": "parent", "plugins": []},
            },
        ]
    directory, home = profile(tmp_path, rows)
    path = tmp_path / "agent.md"
    path.write_text(
        "---\nname: helper\ndescription: Helper\ntools: Read\n"
        "model: sonnet\n---\n./literal {{ body }}\n"
    )
    agent = render_agent(path)
    install = plan_dsh_install(project_layout(tmp_path), agents=[agent])
    native_config = {
        **agent.payload.row["config"],
        "agentOptions": {"provider": "local", "model": "native", "maxTokens": 123},
    }
    fragment = source(
        tmp_path, [{"id": agent.payload.row["id"], "config": native_config}], "native"
    )
    plan = compose_dsh_configuration(
        collect_dsh_configuration([fragment], project_layout(tmp_path)), [install]
    )
    result = inspect_dsh_configuration(
        plan,
        runtime,
        profile_dir=directory,
        home=home,
        cwd=tmp_path,
        process_env=_env(tmp_path),
    )
    chosen = (
        result["entries"]
        if scope == "global"
        else next(
            row
            for row in next(row for row in result["entries"] if row["id"] == "preset")[
                "config"
            ]["plugins"]
            if row["id"] == "ai-dotfiles-managed"
        )["config"]
    )
    bridge = next(row for row in chosen if row["id"] == "ai-dotfiles-bridge")
    final_agent = next(row for row in chosen if row["id"] == agent.payload.row["id"])
    assert final_agent["config"] == native_config
    assert (
        bridge["config"]["agents"][0]["agentOptions"] == native_config["agentOptions"]
    )
    assert bridge["config"]["agents"][0]["persona"] == "./literal {{ body }}\n"
    assert (
        bridge["config"]["agents"][0]["toolFilter"]
        == agent.payload.row["config"]["toolFilter"]
    )
    cli = tmp_path / "route.json"
    cli_patch = {
        "id": agent.payload.row["id"],
        "config": {**native_config, "agentOptions": {"model": "CLI-partial"}},
    }
    if scope == "preset":
        preset = next(row for row in result["entries"] if row["id"] == "preset")
        group = next(
            row
            for row in preset["config"]["plugins"]
            if row["id"] == "ai-dotfiles-managed"
        )
        next(row for row in group["config"] if row["id"] == agent.payload.row["id"])[
            "config"
        ] = cli_patch["config"]
        cli_patch = {"id": "preset", "config": preset["config"]}
    cli.write_text(json.dumps([cli_patch]))
    result = inspect_dsh_configuration(
        plan,
        runtime,
        profile_dir=directory,
        home=home,
        cwd=tmp_path,
        process_env=_env(tmp_path),
        cli_patch_files=[cli],
    )
    chosen = (
        result["entries"]
        if scope == "global"
        else next(
            row
            for row in next(row for row in result["entries"] if row["id"] == "preset")[
                "config"
            ]["plugins"]
            if row["id"] == "ai-dotfiles-managed"
        )["config"]
    )
    assert next(row for row in chosen if row["id"] == "ai-dotfiles-bridge")["config"][
        "agents"
    ][0]["agentOptions"] == {"model": "CLI-partial"}


@pytest.mark.parametrize(
    "replacement",
    [
        {"agentOptions": {"model": "native"}},
        {
            "provider": "spawn",
            "toolName": "ai_dotfiles_agent_helper",
            "persona": "changed",
        },
    ],
)
def test_native_replacement_cannot_drop_source_restrictions(
    tmp_path: Path, runtime: DshNativeRuntime, replacement: object
) -> None:
    directory, home = profile(tmp_path)
    path = tmp_path / "agent.md"
    path.write_text(
        "---\nname: helper\ndescription: Helper\ntools: Read\n---\nLiteral\n"
    )
    install = plan_dsh_install(project_layout(tmp_path), agents=[render_agent(path)])
    fragment = source(
        tmp_path, [{"id": "ai-dotfiles-agent-helper", "config": replacement}], "native"
    )
    plan = compose_dsh_configuration(
        collect_dsh_configuration([fragment], project_layout(tmp_path)), [install]
    )
    with pytest.raises(ConfigError, match="restrictions"):
        inspect_dsh_configuration(
            plan,
            runtime,
            profile_dir=directory,
            home=home,
            cwd=tmp_path,
            process_env=_env(tmp_path),
        )


def test_config_ownership_idempotent_drift_and_local_source_changed_after_attach(
    tmp_path: Path,
) -> None:
    layout = project_layout(tmp_path)
    local = source(tmp_path, {"env": {"A": "initial"}})
    base = plan_dsh_install(layout)
    config = compose_dsh_configuration(collect_dsh_configuration([local], layout))
    install = attach_dsh_config_outputs(base, config)
    apply_dsh_install(install)
    before = snapshot(tmp_path)
    apply_dsh_install(attach_dsh_config_outputs(base, config))
    assert snapshot(tmp_path) == before
    assert dsh_config_drift(config) == ()
    attached = attach_dsh_config_outputs(base, config)
    local.path.write_text('{"env":{"A":"changed"}}')
    after_edit = snapshot(tmp_path)
    with pytest.raises(LinkError, match="source changed"):
        apply_dsh_install(attached)
    assert snapshot(tmp_path) == after_edit
    refreshed = compose_dsh_configuration(collect_dsh_configuration([local], layout))
    assert "STALE (source changed)" in dsh_config_drift(refreshed)
    apply_dsh_install(attach_dsh_config_outputs(base, refreshed))
    assert dsh_config_drift(refreshed) == ()
    assert refreshed.environment["A"] == "changed"


def test_foreign_snapshot_not_adopted_or_backed_up(tmp_path: Path) -> None:
    layout = project_layout(tmp_path)
    layout.owned_dir.mkdir(parents=True)
    layout.config_path.write_text("foreign sentinel")
    config = compose_dsh_configuration(collect_dsh_configuration([], layout))
    before = snapshot(tmp_path)
    with pytest.raises(LinkError, match="foreign"):
        apply_dsh_install(attach_dsh_config_outputs(plan_dsh_install(layout), config))
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "change", ["version", "unknown", "checksum", "generator", "source", "nested"]
)
def test_snapshot_schema_generator_source_contribution_drift_read_only(
    tmp_path: Path, change: str
) -> None:
    layout = project_layout(tmp_path)
    config = compose_dsh_configuration(collect_dsh_configuration([], layout))
    apply_dsh_install(attach_dsh_config_outputs(plan_dsh_install(layout), config))
    value = json.loads(layout.config_path.read_text())
    if change == "version":
        value["schemaVersion"] = 999
    elif change == "unknown":
        value["unknown"] = True
    elif change == "checksum":
        value["environment"] = {"A": "changed"}
    elif change == "generator":
        value["generator"] = 2
    elif change == "source":
        value["sources"] = [{}]
    else:
        value["permissions"] = {"schemaVersion": 999}
    if change in {"generator", "source", "nested"}:
        body = {
            key: child for key, child in value.items() if key != "contributionSha256"
        }
        value["contributionSha256"] = hashlib.sha256(
            (
                json.dumps(body, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
            ).encode()
        ).hexdigest()
    layout.config_path.write_text(json.dumps(value))
    before = snapshot(tmp_path)
    if change == "generator":
        assert "STALE (generator changed)" in dsh_config_drift(config)
    else:
        with pytest.raises(ConfigError):
            read_dsh_config_snapshot(layout.config_path)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("missing_required", [False, True])
def test_actual_native_preset_scope_audit_before_ready_no_durable_agent(
    tmp_path: Path, runtime: DshNativeRuntime, missing_required: bool
) -> None:
    directory, home = profile(
        tmp_path,
        [
            {"id": "typert", "name": "@deepseek-ai/dsh-typert-registry"},
            {"id": "session", "name": "@deepseek-ai/dsh-session"},
            {"id": "projections", "name": "@deepseek-ai/dsh-session-projection"},
            {"id": "tools", "name": "@deepseek-ai/dsh-tools"},
            {"id": "prompt", "name": "@deepseek-ai/dsh-system-prompt"},
            {
                "id": "registry",
                "name": "@deepseek-ai/dsh-agent-preset-registry",
                "config": {"default": "parent"},
            },
            {
                "id": "parent",
                "name": "@deepseek-ai/dsh-agent-preset",
                "config": {"id": "parent", "plugins": []},
            },
        ],
    )
    layout = project_layout(tmp_path)
    plan = compose_dsh_configuration(collect_dsh_configuration([], layout))
    if missing_required:
        next(row for row in plan.rows if row["id"] == "ai-dotfiles-audit")["config"][
            "requiredIds"
        ].append("missing-managed-row")
    install = attach_dsh_config_outputs(plan_dsh_install(layout), plan)
    apply_dsh_install(install)
    result = inspect_dsh_configuration(
        plan,
        runtime,
        profile_dir=directory,
        home=home,
        cwd=tmp_path,
        process_env=_env(tmp_path),
    )
    host = tmp_path / "host"
    host.mkdir()
    (host / "node_modules").symlink_to(runtime.package_dir.parents[1])
    (host / "fixture.json").write_text(json.dumps(result))
    (host / "native.json").write_text(json.dumps(result["entries"]))
    script = host / "test.mjs"
    script.write_text(
        r"""
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { boot } from '@deepseek-ai/dsh-app-boot';
import { createScope } from '@deepseek-ai/dsh-scope';
import { provideCmdline } from '@deepseek-ai/dsh-cmdline';
import { auditBeforeReady, mountSelectedComposition } from 'HELPER_URL';
const fixture = JSON.parse(
  readFileSync(new URL('./fixture.json', import.meta.url)));
const events = [];
let commit;
const ctx = await boot('managed-host-proof',
  new URL('./native.json', import.meta.url).pathname,
  undefined, host => {
    const listeners = new Set();
    const ready = { onReady(listener) {
      listeners.add(listener); return () => listeners.delete(listener);
    } };
    commit = () => {
      events.push('commit'); for (const listener of listeners) listener();
    };
    provideCmdline(host, { args: [], ready, exit: () => {} });
    ready.onReady(() => events.push('surface-ready'));
  }, import.meta.url);
const scope = {};
Object.assign(scope, createScope(ctx, scope));
try {
  assert.equal(ctx.get('aiDotfilesAudit'), undefined,
    'managed audit must remain preset-scoped');
  await assert.rejects(
    auditBeforeReady(ctx, { selection: fixture.selection, commit }),
    /COMPOSITION_NOT_SELECTED/);
  assert.deepEqual(events, []);
  const selected = await ctx.agentPresets.resolve(fixture.selection.id);
  assert.equal(selected.id, fixture.selection.id);
  const lease = await ctx.agentPresets.acquireScope(fixture.selection.id);
  try { assert.equal(typeof lease.key, 'object'); }
  finally { await lease[Symbol.asyncDispose](); }
  await mountSelectedComposition(scope.ctx, fixture.selection);
  assert.equal(ctx.agentPresets.composedPreset(scope.ctx), fixture.selection.id);
  assert.equal(typeof ctx.agentPresets.serviceFor(scope, 'aiDotfilesAudit').run,
    'function');
  const missing = fixture.entries.find(row => row.id === 'parent').config.plugins
    .find(row => row.id === 'ai-dotfiles-managed').config
    .find(row => row.id === 'ai-dotfiles-audit').config.requiredIds
    .includes('missing-managed-row');
  if (missing) {
    await assert.rejects(
      auditBeforeReady(ctx, { selection: fixture.selection, scope, commit }),
      error => {
        assert.deepEqual(error.report.failures.map(item => item.id),
          ['missing-managed-row'], 'loaded scoped bridge/audit cannot be missing');
        return true;
      });
    assert.deepEqual(events, []);
  } else {
    const report = await auditBeforeReady(ctx,
      { selection: fixture.selection, scope, commit });
    assert.equal(report.ready, true);
    assert.equal(report.composition, 'selected');
    assert.deepEqual(events, ['commit', 'surface-ready']);
  }
  assert.equal(ctx.sessions.list().length, 0,
    'no synthetic user Session may be created');
  process.stdout.write(JSON.stringify({ selected: selected.id, events, missing }));
} finally { await scope.dispose(); await ctx.fiber.dispose(); }
""".replace(
            "HELPER_URL", HELPER.as_uri()
        )
    )
    before = snapshot(directory)
    process = subprocess.run(
        [str(runtime.node), str(script)],
        cwd=host,
        env=_env(tmp_path),
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )
    assert process.returncode == 0, process.stderr
    evidence = json.loads(process.stdout)
    assert evidence["events"] == (
        [] if missing_required else ["commit", "surface-ready"]
    )
    assert snapshot(directory) == before
    assert not (home / "sessions").exists()


def test_explicit_cli_default_preset_selection_uses_effective_native_order(
    tmp_path: Path, runtime: DshNativeRuntime
) -> None:
    directory, home = profile(
        tmp_path,
        [
            {
                "id": "registry",
                "name": "@deepseek-ai/dsh-agent-preset-registry",
                "config": {"default": "A"},
            },
            {
                "id": "preset-a",
                "name": "@deepseek-ai/dsh-agent-preset",
                "config": {"id": "A", "plugins": []},
            },
            {
                "id": "preset-b",
                "name": "@deepseek-ai/dsh-agent-preset",
                "config": {"id": "B", "plugins": []},
            },
        ],
    )
    cli = tmp_path / "selection.json"
    cli.write_text(json.dumps([{"id": "registry", "config": {"default": "B"}}]))
    config = compose_dsh_configuration(
        collect_dsh_configuration([], project_layout(tmp_path))
    )
    result = inspect_dsh_configuration(
        config,
        runtime,
        profile_dir=directory,
        home=home,
        cwd=tmp_path,
        process_env=_env(tmp_path),
        cli_patch_files=[cli],
    )
    assert result["selection"] == {"kind": "preset", "id": "B", "entryId": "preset-b"}
    presets = {
        row["id"]: row
        for row in result["entries"]
        if row["name"] == "@deepseek-ai/dsh-agent-preset"
    }
    assert presets["preset-a"]["config"]["plugins"] == []
    assert presets["preset-b"]["config"]["plugins"][0]["id"] == "ai-dotfiles-managed"


@pytest.mark.parametrize("project_id", ["domain-same", "project-same"])
def test_domain_shadow_retires_targeted_patches_and_preserves_other_sources(
    tmp_path: Path, runtime: DshNativeRuntime, project_id: str
) -> None:
    global_value = [
        {
            "insert": [
                {
                    "id": "domain-same",
                    "name": "fixture-unimported",
                    "config": {"serverName": "same", "obsolete": "initial"},
                }
            ]
        },
        {
            "id": "domain-same",
            "config": {"serverName": "same", "value": "stale-global"},
        },
    ]
    global_source = source(tmp_path, global_value, "native", "global")
    global_source = DshConfigSource(
        global_source.path,
        "native",
        "global",
        "@global",
        "@global",
        global_source.binding_root,
    )
    project_value = [
        {
            "insert": [
                {
                    "id": project_id,
                    "name": "fixture-unimported",
                    "config": {"serverName": "same", "obsolete": "project"},
                }
            ]
        },
        {"id": project_id, "config": {"serverName": "same", "value": "project"}},
    ]
    project_source = source(tmp_path, project_value, "native", "project")
    other = source(
        tmp_path,
        [
            {
                "insert": [
                    {
                        "id": "other-domain",
                        "name": "fixture-unimported",
                        "config": {"obsolete": True},
                    }
                ]
            },
            {"id": "other-domain", "config": {"retained": "exact"}},
        ],
        "native",
        "other",
    )
    directory, home = profile(tmp_path)
    config = compose_dsh_configuration(
        collect_dsh_configuration(
            [project_source, global_source, other], project_layout(tmp_path)
        )
    )
    raw_sources = config.snapshot()["sources"]
    before = snapshot(tmp_path)
    result = inspect_dsh_configuration(
        config,
        runtime,
        profile_dir=directory,
        home=home,
        cwd=tmp_path,
        process_env=_env(tmp_path),
    )
    winner = [
        row
        for row in result["entries"]
        if row.get("config", {}).get("serverName") == "same"
    ]
    assert len(winner) == 1
    assert winner[0]["id"] == project_id
    assert winner[0]["config"] == {"serverName": "same", "value": "project"}
    assert next(row for row in result["entries"] if row["id"] == "other-domain")[
        "config"
    ] == {"retained": "exact"}
    assert not any(
        patch.get("config", {}).get("value") == "stale-global"
        for patch in result["patches"]
    )
    assert config.snapshot()["sources"] == raw_sources
    assert raw_sources[0]["value"] == global_value
    assert len(raw_sources) == 3
    assert snapshot(tmp_path) == before
    removed = compose_dsh_configuration(
        collect_dsh_configuration([global_source, other], project_layout(tmp_path))
    )
    result = inspect_dsh_configuration(
        removed,
        runtime,
        profile_dir=directory,
        home=home,
        cwd=tmp_path,
        process_env=_env(tmp_path),
    )
    assert next(row for row in result["entries"] if row["id"] == "domain-same")[
        "config"
    ] == {"serverName": "same", "value": "stale-global"}
    assert next(row for row in result["entries"] if row["id"] == "other-domain")[
        "config"
    ] == {"retained": "exact"}
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("identity", ["id", "toolName", "serverName"])
@pytest.mark.parametrize("placement", ["direct", "group", "targeted"])
def test_retired_insertion_cannot_shadow_surviving_other_domain(
    tmp_path: Path, runtime: DshNativeRuntime, identity: str, placement: str
) -> None:
    anchor = {"id": "anchor", "name": "cordis:group", "group": True, "config": []}
    other_row = {
        "id": "other-domain-client",
        "name": "fixture-never-imported",
        "config": {"value": "other-domain"},
    }
    retired_row = {
        "id": "other-domain-client" if identity == "id" else "retired-child",
        "name": "fixture-never-imported",
        "config": {"value": "retired"},
    }
    if identity != "id":
        other_row["config"][identity] = "same"
        retired_row["config"][identity] = "same"
    insertion = retired_row
    if placement != "direct":
        insertion = {
            "id": "retired-group",
            "name": "cordis:group",
            "group": True,
            "config": [retired_row] if placement == "group" else [],
        }
    retired_patches = [{"id": "anchor", "insert": [insertion]}]
    if placement == "targeted":
        retired_patches.append({"id": "retired-group", "insert": [retired_row]})
    replacement = {**retired_row["config"], "value": "retired-final"}
    retired_patches.append({"id": retired_row["id"], "config": replacement})
    values = [
        [{"insert": [anchor]}],
        [{"insert": [other_row]}],
        retired_patches,
        [{"insert": [anchor]}],
    ]
    sources = []
    for index, value in enumerate(values):
        item = source(tmp_path, value, "native", f"domain-{index}")
        sources.append(
            DshConfigSource(
                item.path,
                item.kind,
                "project" if index == 3 else "global",
                item.origin,
                item.element,
                item.binding_root,
            )
        )
    directory, home = profile(tmp_path)
    before = snapshot(tmp_path)
    package_before = runtime.install_anchor.read_bytes()
    for selected, expected in (
        (sources, other_row),
        (sources[:-1], {**retired_row, "config": replacement}),
        ([sources[0], sources[1], sources[3]], other_row),
    ):
        config = compose_dsh_configuration(
            collect_dsh_configuration(selected, project_layout(tmp_path))
        )
        original_sources = config.snapshot()["sources"]
        result = inspect_dsh_configuration(
            config,
            runtime,
            profile_dir=directory,
            home=home,
            cwd=tmp_path,
            process_env=_env(tmp_path),
        )
        # Native composition flattens groups only at activation, so inspect
        # their actual entry payload without importing the sentinel plugin.
        rows = list(result["entries"])
        for row in rows:
            if row.get("group"):
                rows.extend(row["config"])
        matches = [
            row
            for row in rows
            if (
                row.get("id") == "other-domain-client"
                if identity == "id"
                else isinstance(row.get("config"), dict)
                and row["config"].get(identity) == "same"
            )
        ]
        assert matches == [expected]
        if len(selected) == 4:
            assert next(row for row in rows if row["id"] == "anchor")["config"] == []
            assert not any(row["id"] == "retired-group" for row in rows)
            assert not any(patch.get("id") == "anchor" for patch in result["patches"])
            audit = next(row for row in rows if row["id"] == "ai-dotfiles-audit")
            assert "other-domain-client" in audit["config"]["requiredIds"]
            if identity != "id":
                assert "retired-child" not in audit["config"]["requiredIds"]
        assert config.snapshot()["sources"] == original_sources
        assert [item["value"] for item in original_sources] == [
            values[sources.index(item)] for item in selected
        ]
        assert result["valid"] is True
        assert snapshot(tmp_path) == before
        assert runtime.install_anchor.read_bytes() == package_before


def test_shadowed_competitor_cannot_claim_another_native_identity(
    tmp_path: Path, runtime: DshNativeRuntime
) -> None:
    rows = [
        {"id": "original", "name": "fixture-never-imported", "config": {"value": 1}},
        {
            "id": "original",
            "name": "fixture-never-imported",
            "config": {"serverName": "same", "value": 2},
        },
        {
            "id": "winner",
            "name": "fixture-never-imported",
            "config": {"serverName": "same", "value": 3},
        },
    ]
    sources = [
        source(tmp_path, [{"insert": [row]}], "native", f"domain-{index}")
        for index, row in enumerate(rows)
    ]
    result = compose(tmp_path, runtime, sources=sources)
    assert [
        row for row in result["entries"] if row["name"] == "fixture-never-imported"
    ] == [
        rows[0],
        rows[2],
    ]


def test_cyclic_native_precedence_refuses_exact_insertion_origin(
    tmp_path: Path, runtime: DshNativeRuntime
) -> None:
    parent = source(
        tmp_path,
        [
            {
                "insert": [
                    {
                        "id": "anchor",
                        "name": "cordis:group",
                        "group": True,
                        "config": [],
                    }
                ]
            }
        ],
        "native",
        "parent",
    )
    child = source(
        tmp_path,
        [
            {
                "id": "anchor",
                "insert": [{"id": "anchor", "name": "fixture-never-imported"}],
            }
        ],
        "native",
        "cyclic-child",
    )
    directory, home = profile(tmp_path)
    config = compose_dsh_configuration(
        collect_dsh_configuration([parent, child], project_layout(tmp_path))
    )
    before = snapshot(tmp_path)
    with pytest.raises(
        ConfigError, match=r"@cyclic-child.*patches\[0\].insert\[0\].*precedence.*cycle"
    ):
        inspect_dsh_configuration(
            config,
            runtime,
            profile_dir=directory,
            home=home,
            cwd=tmp_path,
            process_env=_env(tmp_path),
        )
    assert snapshot(tmp_path) == before


def test_custom_skill_provider_additions_preserve_existing_config(
    tmp_path: Path, runtime: DshNativeRuntime
) -> None:
    from ai_dotfiles.core.dsh_targets import DshTargetPlan

    layout = project_layout(tmp_path)
    directory, home = profile(
        tmp_path,
        [
            {
                "id": "skills",
                "name": "@deepseek-ai/dsh-skill-filesystem",
                "config": {
                    "customSkillDirs": ["/existing"],
                    "includeDefaultRoots": False,
                    "watch": False,
                },
            }
        ],
    )
    config = compose_dsh_configuration(
        collect_dsh_configuration([], layout),
        target_plans=[DshTargetPlan(layout, tmp_path, tmp_path, (layout.skills_dir,))],
    )
    result = inspect_dsh_configuration(
        config,
        runtime,
        profile_dir=directory,
        home=home,
        cwd=tmp_path,
        process_env=_env(tmp_path),
    )
    assert next(row for row in result["entries"] if row["id"] == "skills")[
        "config"
    ] == {
        "customSkillDirs": ["/existing", str(layout.skills_dir)],
        "includeDefaultRoots": False,
        "watch": False,
    }


def test_missing_domain_target_retains_precise_source_diagnostic(
    tmp_path: Path, runtime: DshNativeRuntime
) -> None:
    directory, home = profile(tmp_path)
    fragment = source(
        tmp_path,
        [{"id": "missing-target", "config": {"native": True}}],
        "native",
        "precise",
    )
    config = compose_dsh_configuration(
        collect_dsh_configuration([fragment], project_layout(tmp_path))
    )
    before = snapshot(tmp_path)
    with pytest.raises(ConfigError, match="@precise.*missing-target"):
        inspect_dsh_configuration(
            config,
            runtime,
            profile_dir=directory,
            home=home,
            cwd=tmp_path,
            process_env=_env(tmp_path),
        )
    assert snapshot(tmp_path) == before


def test_domain_copied_relative_plugin_preserves_sibling_resource_and_literal_payload(
    tmp_path: Path, runtime: DshNativeRuntime
) -> None:
    layout = project_layout(tmp_path)
    catalog = tmp_path / "catalog"
    domain = catalog / "bundle"
    (domain / "plugins").mkdir(parents=True)
    (domain / "plugins/plugin.mjs").write_text(
        "throw new Error('inspection must never import user plugin');\n"
    )
    (domain / "plugins/data.txt").write_text("sibling literal resource")
    (domain / "dsh.fragment.json").write_text(
        json.dumps(
            [
                {
                    "insert": [
                        {
                            "id": "local-plugin",
                            "name": "./plugins/plugin.mjs",
                            "config": {
                                "persona": "./literal {{ x }}",
                                "args": ["./literal"],
                            },
                        }
                    ]
                }
            ]
        )
    )
    from ai_dotfiles.core.dsh_config import collect_dsh_config_sources

    elements = [parse_element("@bundle")]
    config = compose_dsh_configuration(
        collect_dsh_configuration(
            collect_dsh_config_sources(elements, catalog, layout), layout
        )
    )
    install = attach_dsh_config_outputs(
        collect_dsh_elements(elements, layout, catalog), config
    )
    apply_dsh_install(install)
    directory, home = profile(tmp_path)
    result = inspect_dsh_configuration(
        config,
        runtime,
        profile_dir=directory,
        home=home,
        cwd=tmp_path,
        process_env=_env(tmp_path),
    )
    plugin = next(row for row in result["entries"] if row["id"] == "local-plugin")
    assert (
        plugin["name"]
        == (layout.resources_dir / "domains/bundle/plugins/plugin.mjs").as_uri()
    )
    assert plugin["config"] == {"persona": "./literal {{ x }}", "args": ["./literal"]}
    assert (
        layout.resources_dir / "domains/bundle/plugins/data.txt"
    ).read_text() == "sibling literal resource"


@pytest.mark.parametrize("transport", ["stdio", "http"])
def test_actual_native_fake_mcp_ready_and_origin_fields(
    tmp_path: Path, runtime: DshNativeRuntime, transport: str
) -> None:
    directory, home = profile(
        tmp_path,
        [
            {"id": "tools", "name": "@deepseek-ai/dsh-tools"},
            {"id": "prompt", "name": "@deepseek-ai/dsh-system-prompt"},
        ],
    )
    host = tmp_path / "fake-mcp"
    host.mkdir()
    (host / "node_modules").symlink_to(runtime.package_dir.parents[1])
    server = host / "stdio.mjs"
    server.write_text(
        r"""
import { createInterface } from 'node:readline';
const input = createInterface({ input: process.stdin });
input.on('line', line => {
  const req = JSON.parse(line);
  if (req.id === undefined) return;
  const result = req.method === 'initialize'
    ? { protocolVersion: req.params.protocolVersion, capabilities: { tools: {} },
        serverInfo: { name: 'local', version: '1' } }
    : req.method === 'tools/list'
      ? { tools: [{ name: 'ping', description: JSON.stringify({
          cwd: process.cwd(), args: process.argv.slice(2),
          env: process.env.FAKE_MCP_TOKEN }),
          inputSchema: { type: 'object', properties: {} } }] }
      : { content: [{ type: 'text', text: 'local-only' }] };
  process.stdout.write(JSON.stringify({ jsonrpc: '2.0', id: req.id, result }) + '\n');
});
"""
    )
    (tmp_path / "bound/worker").mkdir(parents=True)
    if transport == "stdio":
        mcp_server = {
            "command": str(runtime.node),
            "args": [str(server), "./literal arg"],
            "cwd": "./worker",
            "env": {"FAKE_MCP_TOKEN": "explicit-local"},
        }
    else:
        mcp_server = {
            "type": "http",
            "url": "http://127.0.0.1:1/mcp",
            "headers": {"X-Local-Sentinel": "./literal-header"},
        }
    source_item = source(tmp_path, {"mcpServers": {"server": mcp_server}}, "mcp")
    layout = project_layout(tmp_path)
    config = compose_dsh_configuration(collect_dsh_configuration([source_item], layout))
    apply_dsh_install(attach_dsh_config_outputs(plan_dsh_install(layout), config))
    result = inspect_dsh_configuration(
        config,
        runtime,
        profile_dir=directory,
        home=home,
        cwd=tmp_path,
        process_env=_env(tmp_path),
    )
    (host / "fixture.json").write_text(json.dumps(result))
    script = host / "host.mjs"
    script.write_text(
        r"""
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { boot } from '@deepseek-ai/dsh-app-boot';
import { auditBeforeReady } from 'HELPER_URL';
const fixture = JSON.parse(readFileSync(new URL('./fixture.json', import.meta.url)));
const client = fixture.entries.find(row => row.id === 'ai-dotfiles-mcp-server');
let http;
let headers;
if (client.config.transport === 'streamable-http') {
  http = createServer(async (req, res) => {
    if (req.method !== 'POST') { res.writeHead(405).end(); return; }
    headers = req.headers;
    let body = '';
    for await (const chunk of req) body += chunk;
    const call = JSON.parse(body);
    if (call.id === undefined) { res.writeHead(202).end(); return; }
    const result = call.method === 'initialize'
      ? { protocolVersion: call.params.protocolVersion, capabilities: { tools: {} },
          serverInfo: { name: 'local-http', version: '1' } }
      : { tools: [{ name: 'ping', description: 'local HTTP fixture',
          inputSchema: { type: 'object', properties: {} } }] };
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ jsonrpc: '2.0', id: call.id, result }));
  });
  await new Promise(resolve => http.listen(0, '127.0.0.1', resolve));
  client.config.url = `http://127.0.0.1:${http.address().port}/mcp`;
}
writeFileSync(new URL('./native.json', import.meta.url),
  JSON.stringify(fixture.entries));
let ctx;
try {
  ctx = await boot('fake-mcp-proof', new URL('./native.json', import.meta.url).pathname,
    undefined, undefined, import.meta.url);
  const events = [];
  const report = await auditBeforeReady(ctx, { selection: fixture.selection,
    commit: () => events.push('ready') });
  assert.equal(report.ready, true);
  const tool = ctx.tools.get('mcp__server__ping');
  assert.ok(tool);
  if (client.config.transport === 'stdio') {
    const evidence = JSON.parse(tool.description);
    assert.equal(evidence.cwd, client.config.cwd);
    assert.deepEqual(evidence.args, ['./literal arg']);
    assert.equal(evidence.env, 'explicit-local');
  } else assert.equal(headers['x-local-sentinel'], './literal-header');
  assert.deepEqual(events, ['ready']);
  process.stdout.write(JSON.stringify({
    transport: client.config.transport, ready: report.ready }));
} finally {
  await ctx?.fiber.dispose();
  if (http) await new Promise(resolve => http.close(resolve));
}
""".replace(
            "HELPER_URL", HELPER.as_uri()
        )
    )
    before = snapshot(directory)
    process = subprocess.run(
        [str(runtime.node), str(script)],
        cwd=host,
        env=_env(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout)["ready"] is True
    assert snapshot(directory) == before


@pytest.mark.parametrize(
    "case", ["safe", "collision", "expression", "cycle", "initial"]
)
def test_native_include_namespaces_are_read_without_activation(
    tmp_path: Path, runtime: DshNativeRuntime, case: str
) -> None:
    include = {
        "id": "include",
        "name": "cordis:include",
        "config": {"path": "./child.yml"},
    }
    directory, home = profile(tmp_path, [include])
    child = directory / "child.yml"
    if case == "safe":
        child.write_text(
            "- id: foreign\n  name: fixture-never-imported\n  config:\n"
            "    persona: './literal {{ x }}'\n"
        )
    elif case == "collision":
        child.write_text("- id: ai-dotfiles-bridge\n  name: fixture-never-imported\n")
    elif case == "expression":
        child.write_text(
            "- id: foreign\n  name: fixture-never-imported\n  config:\n"
            "    toolName: !!js 'process.exit(91)'\n"
        )
    elif case == "cycle":
        child.write_text(json.dumps([include]))
    else:
        include["config"]["initial"] = []
        (directory / "cordis.patch.yml").write_text(json.dumps([{"insert": [include]}]))
    plan = compose_dsh_configuration(
        collect_dsh_configuration([], project_layout(tmp_path))
    )
    before = snapshot(tmp_path)
    package_before = runtime.install_anchor.read_bytes()
    if case == "safe":
        result = inspect_dsh_configuration(
            plan,
            runtime,
            profile_dir=directory,
            home=home,
            cwd=tmp_path,
            process_env=_env(tmp_path),
        )
        assert result["selection"] == {"kind": "global"}
    else:
        reason = {
            "collision": "collides",
            "expression": "without evaluating",
            "cycle": "cycle",
            "initial": "would be written",
        }[case]
        with pytest.raises(ConfigError, match=reason):
            inspect_dsh_configuration(
                plan,
                runtime,
                profile_dir=directory,
                home=home,
                cwd=tmp_path,
                process_env=_env(tmp_path),
            )
    assert snapshot(tmp_path) == before
    assert runtime.install_anchor.read_bytes() == package_before


def test_cli_inserted_foreign_tool_collision_refuses(
    tmp_path: Path, runtime: DshNativeRuntime
) -> None:
    directory, home = profile(tmp_path)
    mcp = source(tmp_path, {"mcpServers": {"server": {"command": "/literal"}}}, "mcp")
    plan = compose_dsh_configuration(
        collect_dsh_configuration([mcp], project_layout(tmp_path))
    )
    cli = tmp_path / "collision.json"
    cli.write_text(
        json.dumps(
            [
                {
                    "insert": [
                        {
                            "id": "foreign",
                            "name": "fixture-never-imported",
                            "config": {"serverName": "server"},
                        }
                    ]
                }
            ]
        )
    )
    with pytest.raises(ConfigError, match="foreign CLI serverName collides"):
        inspect_dsh_configuration(
            plan,
            runtime,
            profile_dir=directory,
            home=home,
            cwd=tmp_path,
            process_env=_env(tmp_path),
            cli_patch_files=[cli],
        )


@pytest.mark.parametrize(
    "identity,overlay,nested",
    [
        ("serverName", "domain", False),
        ("toolName", "domain", False),
        ("serverName", "cli", False),
        ("toolName", "cli", False),
        ("id", "cli", False),
        ("serverName", "domain", True),
        ("toolName", "cli", True),
        ("id", "cli", True),
    ],
)
def test_effective_foreign_collision_with_native_domain_has_original_provenance(
    tmp_path: Path,
    runtime: DshNativeRuntime,
    identity: str,
    overlay: str,
    nested: bool,
) -> None:
    plugin = (
        "@deepseek-ai/dsh-mcp-client"
        if identity == "serverName"
        else "fixture-never-imported"
    )
    native_config = (
        {"transport": "stdio", "command": "/literal"}
        if identity == "serverName"
        else {}
    )
    managed_config = {
        **native_config,
        **({identity: "same"} if identity != "id" else {}),
    }
    foreign_config = {
        **native_config,
        **({identity: "old"} if identity != "id" else {}),
    }
    managed = {"id": "domain-client", "name": plugin, "config": managed_config}
    foreign = {"id": "user-client", "name": plugin, "config": foreign_config}
    conflicting = (
        {"insert": [{"id": "domain-client", "name": plugin, "config": foreign_config}]}
        if identity == "id"
        else {"id": "user-client", "config": managed_config}
    )
    if nested:
        bound = tmp_path / "bound"
        bound.mkdir()
        for label, row in (("managed", managed), ("user", foreign)):
            (bound / (label + "-leaf.json")).write_text(json.dumps([row]))
            (bound / (label + "-outer.json")).write_text(
                json.dumps(
                    [
                        {
                            "id": label + "-inner",
                            "name": "cordis:include",
                            "config": {"path": "./" + label + "-leaf.json"},
                        }
                    ]
                )
            )
        managed = {
            "id": "managed-include",
            "name": "cordis:include",
            "config": {"path": "./managed-outer.json"},
        }
        foreign = {
            "id": "user-include",
            "name": "cordis:include",
            "config": {"path": (bound / "user-outer.json").as_uri()},
        }
        conflicting = {
            "id": "user-include",
            "config": {
                **foreign["config"],
                "patches": [
                    {
                        "id": "user-inner",
                        "config": {
                            "path": "./user-leaf.json",
                            "patches": [conflicting],
                        },
                    }
                ],
            },
        }
    values = [{"insert": [managed]}]
    cli_files = []
    if overlay == "domain":
        values.append(conflicting)
        override_origin = "@managed"
        override_field = "patches[1]"
    else:
        cli = tmp_path / "explicit-override.json"
        cli.write_text(json.dumps([conflicting]))
        cli_files = [cli]
        override_origin = str(cli)
        override_field = "patches[0]"
    fragment = source(tmp_path, values, "native", "managed")
    directory, home = profile(tmp_path, [foreign])
    config = compose_dsh_configuration(
        collect_dsh_configuration([fragment], project_layout(tmp_path))
    )
    before = snapshot(tmp_path)
    package_before = runtime.install_anchor.read_bytes()
    with pytest.raises(ConfigError) as captured:
        inspect_dsh_configuration(
            config,
            runtime,
            profile_dir=directory,
            home=home,
            cwd=tmp_path,
            process_env=_env(tmp_path),
            cli_patch_files=cli_files,
        )
    message = str(captured.value)
    assert "collides" in message and identity in message
    assert "@managed" in message
    assert "entries[0]" in message if nested else "patches[0].insert[0]" in message
    if nested:
        assert str(tmp_path / "bound/managed-leaf.json") in message
        assert str(tmp_path / "bound/user-leaf.json") in message
    else:
        assert "user-client" in message or identity == "id"
    assert override_origin in message and override_field in message
    assert snapshot(tmp_path) == before
    assert runtime.install_anchor.read_bytes() == package_before


@pytest.mark.parametrize("new_identity", [False, True])
def test_cli_replaced_managed_include_retains_domain_namespace_ownership(
    tmp_path: Path, runtime: DshNativeRuntime, new_identity: bool
) -> None:
    bound = tmp_path / "bound"
    bound.mkdir()
    original = bound / "original.json"
    replacement = bound / "replacement.json"
    original.write_text(
        json.dumps(
            [
                {
                    "id": "managed-child",
                    "name": "fixture-never-imported",
                    "config": {"toolName": "old"},
                }
            ]
        )
    )
    replacement.write_text(
        json.dumps(
            [
                {
                    "id": "new-child" if new_identity else "managed-child",
                    "name": "fixture-never-imported",
                    "config": {"toolName": "same"},
                }
            ]
        )
    )
    fragment = source(
        tmp_path,
        [
            {
                "insert": [
                    {
                        "id": "managed-include",
                        "name": "cordis:include",
                        "config": {"path": "./original.json"},
                    }
                ]
            }
        ],
        "native",
        "managed",
    )
    cli = tmp_path / "replace-include.json"
    cli.write_text(
        json.dumps(
            [{"id": "managed-include", "config": {"path": replacement.as_uri()}}]
        )
    )
    directory, home = profile(
        tmp_path,
        [
            {
                "id": "user-client",
                "name": "fixture-never-imported",
                "config": {"toolName": "same"},
            }
        ],
    )
    config = compose_dsh_configuration(
        collect_dsh_configuration([fragment], project_layout(tmp_path))
    )
    before = snapshot(tmp_path)
    with pytest.raises(ConfigError) as captured:
        inspect_dsh_configuration(
            config,
            runtime,
            profile_dir=directory,
            home=home,
            cwd=tmp_path,
            process_env=_env(tmp_path),
            cli_patch_files=[cli],
        )
    message = str(captured.value)
    assert "collides" in message and "toolName" in message
    assert "@managed" in message and "user-client" in message
    assert str(replacement) in message and str(cli) in message
    assert "patches[0].config" in message
    if new_identity:
        assert "patches[0].insert[0].config.path" in message
    else:
        assert str(original) in message and "entries[0].config.toolName" in message
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("selection", ["A", "B", "B-unavailable-A"])
def test_native_domain_preset_descendants_follow_selected_namespace_and_audit(
    tmp_path: Path, runtime: DshNativeRuntime, selection: str
) -> None:
    native = {"transport": "stdio", "command": "/literal"}
    plugin = "@deepseek-ai/dsh-mcp-client"
    selected = selection.split("-")[0]
    a_plugins = [
        {
            "id": "scoped-a",
            "name": plugin,
            "config": {**native, "serverName": "same"},
        }
    ]
    if selection == "B-unavailable-A":
        a_plugins = [
            {
                "id": "unselected-include",
                "name": "cordis:include",
                "config": {"path": "./never-read.json"},
            }
        ]
    b_plugins = [
        {
            "id": "scoped-b",
            "name": plugin,
            "config": {**native, "serverName": "other"},
        }
    ]
    fragment = source(
        tmp_path,
        [
            {
                "insert": [
                    {
                        "id": "registry",
                        "name": "@deepseek-ai/dsh-agent-preset-registry",
                        "config": {"default": selected},
                    },
                    {
                        "id": "preset-a",
                        "name": "@deepseek-ai/dsh-agent-preset",
                        "config": {"id": "A", "plugins": a_plugins},
                    },
                    {
                        "id": "preset-b",
                        "name": "@deepseek-ai/dsh-agent-preset",
                        "config": {"id": "B", "plugins": b_plugins},
                    },
                ]
            },
            {"id": "user-client", "config": {**native, "serverName": "same"}},
        ],
        "native",
        "native-preset",
    )
    directory, home = profile(
        tmp_path,
        [
            {
                "id": "user-client",
                "name": plugin,
                "config": {**native, "serverName": "old"},
            }
        ],
    )
    config = compose_dsh_configuration(
        collect_dsh_configuration([fragment], project_layout(tmp_path))
    )
    before = snapshot(tmp_path)
    package_before = runtime.install_anchor.read_bytes()
    if selected == "A":
        with pytest.raises(ConfigError) as captured:
            inspect_dsh_configuration(
                config,
                runtime,
                profile_dir=directory,
                home=home,
                cwd=tmp_path,
                process_env=_env(tmp_path),
            )
        message = str(captured.value)
        assert "@native-preset" in message and "collides" in message
        assert "patches[0].insert[1].config.plugins[0].config.serverName" in message
        assert "user-client" in message and "patches[1].config.serverName" in message
    else:
        result = inspect_dsh_configuration(
            config,
            runtime,
            profile_dir=directory,
            home=home,
            cwd=tmp_path,
            process_env=_env(tmp_path),
        )
        preset = next(row for row in result["entries"] if row["id"] == "preset-b")
        group = next(
            row
            for row in preset["config"]["plugins"]
            if row["id"] == "ai-dotfiles-managed"
        )
        audit = next(row for row in group["config"] if row["id"] == "ai-dotfiles-audit")
        assert "scoped-b" in audit["config"]["requiredIds"]
        assert "scoped-a" not in audit["config"]["requiredIds"]
        assert "unselected-include" not in audit["config"]["requiredIds"]
        assert result["valid"] is True
    assert snapshot(tmp_path) == before
    assert runtime.install_anchor.read_bytes() == package_before


def test_final_native_domain_names_use_explicit_cli_full_replacement(
    tmp_path: Path, runtime: DshNativeRuntime
) -> None:
    client = "@deepseek-ai/dsh-mcp-client"
    native = {"transport": "stdio", "command": "/literal"}
    fragment = source(
        tmp_path,
        [
            {
                "insert": [
                    {
                        "id": "domain-client",
                        "name": client,
                        "config": {
                            **native,
                            "serverName": "same",
                            "args": ["obsolete"],
                        },
                    }
                ]
            },
            {"id": "user-client", "config": {**native, "serverName": "same"}},
        ],
        "native",
    )
    cli = tmp_path / "explicit-route.json"
    replacement = {**native, "serverName": "explicit"}
    cli.write_text(json.dumps([{"id": "domain-client", "config": replacement}]))
    result = compose(
        tmp_path,
        runtime,
        rows=[
            {
                "id": "user-client",
                "name": client,
                "config": {**native, "serverName": "old"},
            }
        ],
        sources=[fragment],
        extra={"cli_patch_files": [cli]},
    )
    assert (
        next(row for row in result["entries"] if row["id"] == "domain-client")["config"]
        == replacement
    )
    assert next(row for row in result["entries"] if row["id"] == "user-client")[
        "config"
    ] == {**native, "serverName": "same"}


def config_source(
    tmp_path: Path,
    value: object,
    *,
    kind: str = "settings",
    scope: str = "project",
    name: str = "source",
) -> DshConfigSource:
    path = tmp_path / (name + ".json")
    path.write_text(json.dumps(value))
    return DshConfigSource(path, kind, scope, "@" + name, "@" + name, tmp_path / name)  # type: ignore[arg-type]


def test_global_project_environment_explicit_process_and_empty_win(
    tmp_path: Path,
) -> None:
    global_source = config_source(
        tmp_path, {"env": {"A": "global", "B": "g"}}, scope="global", name="g"
    )
    project_source = config_source(
        tmp_path, {"env": {"A": "project", "C": "p"}}, name="p"
    )
    plan = collect_dsh_configuration(
        [project_source, global_source], project_layout(tmp_path)
    )
    assert plan.environment == {"A": "project", "B": "g", "C": "p"}
    assert plan.child_environment(
        {"A": "", "HOME": "/explicit", "DSH_HOME": "/explicit-dsh"}
    ) == {"A": "", "B": "g", "C": "p", "HOME": "/explicit", "DSH_HOME": "/explicit-dsh"}
    assert "HOME" not in plan.snapshot()["environment"]
    assert [item["scope"] for item in plan.sources] == ["global", "project"]


@pytest.mark.parametrize(
    "name",
    [
        "PATH",
        "home",
        "NODE_OPTIONS",
        "PYTHONPATH",
        "DSH_HOME",
        "dsh_permission_mode",
        "XDG_CONFIG_HOME",
        "DYLD_LIBRARY_PATH",
        "HTTP_PROXY",
        "DEEPSEEK_BASE_URL",
        "BASH_FUNC_bad",
        "GIT_CONFIG_COUNT",
        "NODE_TLS_REJECT_UNAUTHORIZED",
    ],
)
def test_reserved_environment_refuses_even_when_explicit_process_wins(
    tmp_path: Path, name: str
) -> None:
    plan = collect_dsh_configuration(
        [config_source(tmp_path, {"env": {name: "bad"}})], project_layout(tmp_path)
    )
    assert plan.blocked
    assert plan.diagnostics[0].field == "env." + name
    with pytest.raises(ConfigError, match="bootstrap"):
        plan.child_environment({name: "explicit"})


@pytest.mark.parametrize(
    "environment", [None, [], {"A": None}, {"A": 1}, {"bad=name": "x"}, {"A": "\0"}]
)
def test_invalid_environment_is_diagnosed(tmp_path: Path, environment: object) -> None:
    plan = collect_dsh_configuration(
        [config_source(tmp_path, {"env": environment})], project_layout(tmp_path)
    )
    assert plan.blocked


def test_original_permission_sources_preserve_repeats_and_bad_values(
    tmp_path: Path,
) -> None:
    first = config_source(
        tmp_path,
        {"permissions": {"deny": ["Bash", "Bash"]}},
        name="first",
        scope="global",
    )
    second = config_source(
        tmp_path, {"permissions": {"ask": ["Read"], "deny": "malformed"}}, name="second"
    )
    plan = collect_dsh_configuration([second, first], project_layout(tmp_path))
    assert len(plan.permissions.contributions) == 3
    assert [item.provenance.origin for item in plan.permissions.contributions] == [
        "@first",
        "@first",
        "@second",
    ]
    assert plan.permissions.gaps[0].value == "malformed"
    assert plan.blocked
    with pytest.raises(ConfigError):
        compose_dsh_configuration(plan)


def test_mcp_preserves_stdio_and_http_fields_and_literal_args(tmp_path: Path) -> None:
    stdio = {
        "command": "./bin/server",
        "args": ["./literal", "a b", "$(never)", "{{ literal }}"],
        "cwd": "./work",
        "env": {"TOKEN": "explicit", "constructor": "literal"},
    }
    http = {
        "type": "http",
        "url": "http://127.0.0.1:1234/mcp",
        "headers": {"Authorization": "Bearer local", "constructor": "./literal"},
    }
    plan = collect_dsh_configuration(
        [
            config_source(
                tmp_path, {"mcpServers": {"stdio": stdio, "http": http}}, kind="mcp"
            )
        ],
        project_layout(tmp_path),
    )
    assert not plan.blocked
    native_stdio, native_http = [item.rows[0]["config"] for item in plan.contributions]
    assert native_stdio == {
        "serverName": "stdio",
        "transport": "stdio",
        "command": str(tmp_path / "source/bin/server"),
        "args": stdio["args"],
        "cwd": str(tmp_path / "source/work"),
        "env": stdio["env"],
        "failOnStartupError": True,
    }
    assert native_http["headers"] == http["headers"]
    assert native_http["transport"] == "streamable-http"
    assert plan.contributions[0].requirements.required_ids == ("ai-dotfiles-mcp-stdio",)


@pytest.mark.parametrize(
    "server,field",
    [
        ({"type": "sse", "url": "https://example.test"}, "type"),
        ({"type": "unknown"}, "type"),
        ({"command": "node", "prompts": True}, "prompts"),
        ({"type": "http", "url": "http://127.0.0.1", "oauth": {}}, "oauth"),
        ({"command": "node", "headersHelper": "helper"}, "headersHelper"),
        ({"command": "node", "env": {"TOKEN": "${TOKEN:-fallback}"}}, "env.TOKEN"),
        ({"command": "node", "args": ["${VAR}"]}, "args[0]"),
        ({"command": "node", "serverName": "another"}, "serverName"),
        ({"command": "node", "args": "string"}, "args"),
        ({"type": "http", "url": "file:///tmp/x"}, "url"),
        ({"type": "http", "url": "http://127.0.0.1", "headers": {"A": 1}}, "headers"),
    ],
)
def test_mcp_gaps_retain_exact_field_and_never_emit_partial_client(
    tmp_path: Path, server: object, field: str
) -> None:
    plan = collect_dsh_configuration(
        [config_source(tmp_path, {"mcpServers": {"test": server}}, kind="mcp")],
        project_layout(tmp_path),
    )
    assert plan.blocked
    assert any(item.field == "mcpServers.test." + field for item in plan.diagnostics)
    assert not plan.contributions
    assert plan.sources[0]["value"] == {"mcpServers": {"test": server}}


@pytest.mark.parametrize("name", ["", "has.dot", "x" * 33, "space name"])
def test_mcp_native_namespace_validation(tmp_path: Path, name: str) -> None:
    plan = collect_dsh_configuration(
        [
            config_source(
                tmp_path, {"mcpServers": {name: {"command": "node"}}}, kind="mcp"
            )
        ],
        project_layout(tmp_path),
    )
    assert plan.blocked


def test_scope_merge_one_agent_and_one_mcp_project_wins_removal_retains_other(
    tmp_path: Path,
) -> None:
    global_source = config_source(
        tmp_path,
        {"mcpServers": {"same": {"command": "global"}, "other": {"command": "other"}}},
        kind="mcp",
        scope="global",
        name="g",
    )
    project_source = config_source(
        tmp_path, {"mcpServers": {"same": {"command": "project"}}}, kind="mcp", name="p"
    )
    global_agent = tmp_path / "global-agent.md"
    project_agent = tmp_path / "project-agent.md"
    for path, body in (
        (global_agent, "Global literal"),
        (project_agent, "Project {{ literal }}"),
    ):
        path.write_text(f"---\nname: same\ndescription: Same\n---\n{body}\n")
    plans = [
        plan_dsh_install(
            project_layout(tmp_path), agents=[render_agent(project_agent)]
        ),
        plan_dsh_install(
            global_layout(tmp_path / "dsh-home"), agents=[render_agent(global_agent)]
        ),
    ]
    collected = collect_dsh_configuration(
        [project_source, global_source], project_layout(tmp_path)
    )
    merged = compose_dsh_configuration(collected, plans)
    assert len(merged.contributions) == 3
    assert [row["id"] for row in merged.rows].count("ai-dotfiles-agent-same") == 1
    assert (
        next(
            row["config"]["persona"]
            for row in merged.rows
            if row["id"] == "ai-dotfiles-agent-same"
        )
        == "Project {{ literal }}\n"
    )
    assert (
        next(
            row["config"]["command"]
            for row in merged.rows
            if row["id"] == "ai-dotfiles-mcp-same"
        )
        == "project"
    )
    removed = compose_dsh_configuration(
        collect_dsh_configuration([global_source], project_layout(tmp_path)), plans
    )
    assert (
        next(
            row["config"]["command"]
            for row in removed.rows
            if row["id"] == "ai-dotfiles-mcp-same"
        )
        == "global"
    )
    assert any(row["id"] == "ai-dotfiles-mcp-other" for row in removed.rows)


def test_domain_collector_reuses_topology_and_scope_binding(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    for name, depends in (("base", []), ("dependent", ["@base"])):
        directory = catalog / name
        directory.mkdir(parents=True)
        (directory / "domain.json").write_text(json.dumps({"depends": depends}))
        (directory / "dsh.fragment.json").write_text("[]")
    sources = collect_dsh_config_sources(
        [parse_element("@dependent"), parse_element("@base")],
        catalog,
        project_layout(tmp_path),
    )
    assert [item.origin for item in sources] == ["@base", "@dependent"]
    assert (
        sources[0].binding_root == tmp_path / ".dsh/ai-dotfiles/resources/domains/base"
    )


@pytest.mark.parametrize("raw", ["{bad", "[", "null", "[]", '{"env":{"A":NaN}}'])
def test_malformed_original_source_never_becomes_empty(
    tmp_path: Path, raw: str
) -> None:
    item = config_source(tmp_path, {})
    item.path.write_text(raw)
    with pytest.raises(ConfigError):
        collect_dsh_configuration([item], project_layout(tmp_path))


@pytest.mark.parametrize(
    "name,version,binary",
    [
        ("other", "0.2.0-rc.2", "lib/bin.js"),
        ("@deepseek-ai/dsh", "latest", "lib/bin.js"),
        ("@deepseek-ai/dsh", "0.2.0-rc.2", "shell.sh"),
    ],
)
def test_runtime_requires_official_pinned_executable(
    tmp_path: Path, name: str, version: str, binary: str
) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"name": name, "version": version, "bin": {"dsh": binary}})
    )
    with pytest.raises(ConfigError):
        resolve_dsh_runtime(tmp_path)


@pytest.mark.parametrize("outcome", ["ready", "failed", "missing", "disabled"])
def test_domain_include_descendant_is_required_before_native_ready(
    tmp_path: Path, runtime: DshNativeRuntime, outcome: str
) -> None:
    layout = project_layout(tmp_path)
    catalog = tmp_path / "catalog"
    domain = catalog / "bundle"
    plugins = domain / "plugins"
    plugins.mkdir(parents=True)
    (plugins / "child.mjs").write_text(
        "export function apply(_ctx, config) {\n"
        "  if (config.fail) throw new Error('managed descendant failed');\n"
        "}\n"
    )
    (plugins / "nested.json").write_text(
        json.dumps(
            [
                {
                    "id": "managed-child",
                    "name": "./child.mjs",
                    "config": {
                        "fail": outcome == "failed",
                        "persona": "./literal {{ x }}",
                    },
                },
            ]
        )
    )
    (plugins / "entries.yml").write_text(
        "- id: managed-group\n  name: cordis:group\n  group: true\n"
        "  config:\n    - id: nested-include\n      name: cordis:include\n"
        "      config:\n        path: ./nested.json\n"
    )
    (plugins / "empty.json").write_text("[]")
    (domain / "dsh.fragment.json").write_text(
        json.dumps(
            [
                {
                    "insert": [
                        {
                            "id": "managed-include",
                            "name": "cordis:include",
                            "config": {"path": "./plugins/entries.yml"},
                        }
                    ]
                },
            ]
        )
    )
    elements = [parse_element("@bundle")]
    config = compose_dsh_configuration(
        collect_dsh_configuration(
            collect_dsh_config_sources(elements, catalog, layout), layout
        )
    )
    apply_dsh_install(
        attach_dsh_config_outputs(
            collect_dsh_elements(elements, layout, catalog), config
        )
    )
    directory, home = profile(
        tmp_path,
        [
            {"id": "tools", "name": "@deepseek-ai/dsh-tools"},
            {"id": "prompt", "name": "@deepseek-ai/dsh-system-prompt"},
        ],
    )
    copied = layout.resources_dir / "domains/bundle/plugins"
    cli_files = []
    if outcome in {"missing", "disabled"}:
        replacement = {"path": (copied / "empty.json").as_uri()}
        if outcome == "disabled":
            replacement = {
                "path": (copied / "entries.yml").as_uri(),
                "patches": [
                    {
                        "id": "nested-include",
                        "config": {
                            "path": "./nested.json",
                            "patches": [{"id": "managed-child", "disabled": True}],
                        },
                    },
                ],
            }
        cli = tmp_path / "override.json"
        cli.write_text(json.dumps([{"id": "managed-include", "config": replacement}]))
        cli_files = [cli]
    before = snapshot(tmp_path)
    package_before = runtime.install_anchor.read_bytes()
    result = inspect_dsh_configuration(
        config,
        runtime,
        profile_dir=directory,
        home=home,
        cwd=tmp_path,
        process_env=_env(tmp_path),
        cli_patch_files=cli_files,
    )
    assert snapshot(tmp_path) == before
    required = next(
        row for row in result["entries"] if row["id"] == "ai-dotfiles-audit"
    )["config"]["requiredIds"]
    assert set(required) >= {
        "managed-include",
        "managed-group",
        "nested-include",
        "managed-child",
    }
    host = tmp_path / "include-host"
    host.mkdir()
    (host / "node_modules").symlink_to(runtime.package_dir.parents[1])
    (host / "fixture.json").write_text(json.dumps({**result, "outcome": outcome}))
    (host / "native.json").write_text(json.dumps(result["entries"]))
    script = host / "host.mjs"
    script.write_text(
        r"""
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { boot } from '@deepseek-ai/dsh-app-boot';
import { auditBeforeReady } from 'HELPER_URL';
const fixture = JSON.parse(
  readFileSync(new URL('./fixture.json', import.meta.url)));
const ctx = await boot('domain-include-proof',
  new URL('./native.json', import.meta.url).pathname,
  undefined, undefined, import.meta.url);
const events = [];
try {
  let report;
  try {
    report = await auditBeforeReady(ctx, { selection: fixture.selection,
      commit: () => events.push('ready') });
  } catch (error) {
    assert.ok(error.report, String(error));
    report = error.report;
  }
  if (fixture.outcome === 'ready') {
    assert.equal(report.ready, true);
    assert.deepEqual(events, ['ready']);
  } else {
    assert.equal(report.ready, false);
    assert.deepEqual(events, []);
    const expected = { failed: 'APPLY_FAILED', missing: 'MISSING_ROW',
      disabled: 'DISABLED_ROW' }[fixture.outcome];
    assert.ok(report.failures.some(item => item.code === expected
      && (item.id === 'managed-child' || item.id.endsWith(':managed-child'))),
      JSON.stringify(report));
  }
  process.stdout.write(JSON.stringify({ report, events }));
} finally { await ctx.fiber.dispose(); }
""".replace(
            "HELPER_URL", HELPER.as_uri()
        )
    )
    source_before = snapshot(catalog)
    home_before = snapshot(home)
    resources_before = snapshot(layout.resources_dir)
    process = subprocess.run(
        [str(runtime.node), str(script)],
        cwd=host,
        env=_env(tmp_path),
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )
    assert process.returncode == 0, process.stderr
    evidence = json.loads(process.stdout)
    assert evidence["report"]["ready"] is (outcome == "ready")
    assert snapshot(catalog) == source_before
    assert snapshot(home) == home_before
    assert snapshot(layout.resources_dir) == resources_before
    assert runtime.install_anchor.read_bytes() == package_before


@pytest.mark.parametrize("identity", [None, "", {"__jsExpr": "process.exit(91)"}])
def test_domain_include_unknown_identity_refuses_with_exact_source_field(
    tmp_path: Path, runtime: DshNativeRuntime, identity: object
) -> None:
    bound = tmp_path / "bound"
    bound.mkdir()
    child = bound / "child.json"
    child.write_text(json.dumps([{"id": identity, "name": "fixture-not-imported"}]))
    fragment = source(
        tmp_path,
        [
            {
                "insert": [
                    {
                        "id": "managed-include",
                        "name": "cordis:include",
                        "config": {"path": "./child.json"},
                    }
                ]
            }
        ],
        "native",
    )
    directory, home = profile(tmp_path)
    plan = compose_dsh_configuration(
        collect_dsh_configuration([fragment], project_layout(tmp_path))
    )
    before = snapshot(tmp_path)
    with pytest.raises(ConfigError) as captured:
        inspect_dsh_configuration(
            plan,
            runtime,
            profile_dir=directory,
            home=home,
            cwd=tmp_path,
            process_env=_env(tmp_path),
        )
    assert str(child) in str(captured.value)
    assert "entries[0].id" in str(captured.value)
    assert "literal" in str(captured.value) or "forbidden" in str(captured.value)
    assert snapshot(tmp_path) == before
