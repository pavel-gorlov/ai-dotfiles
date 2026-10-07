"""Required real published-RC2 tests, with isolated homes and local providers.

The optional test-only runtime path reuses a disposable npm installation; its
package version is checked, never used to skip native acceptance. Without it,
the session fixture installs EXACT RC2 into pytest's temporary root. Production
code never installs DSH. Missing Node/npm/network/runtime is a FAILED gate.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ai_dotfiles.core.dsh_audit import (
    DSH_AUDIT_GENERATOR_VERSION,
    DshAuditRequirements,
    audit_module_text,
    bridge_audit_requirements,
    bridge_module_text,
    build_bridge_config,
)
from ai_dotfiles.core.dsh_permissions import translate_permissions
from ai_dotfiles.core.dsh_render import render_agent, render_rule
from ai_dotfiles.core.errors import ConfigError

pytestmark = pytest.mark.integration
PINNED_DSH = "0.2.0-rc.2"


def _env(root: Path) -> dict[str, str]:
    """Pass no production credentials, home, DSH profile or provider settings."""
    home = root / "home"
    home.mkdir(exist_ok=True)
    return {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "DSH_HOME": str(root / "dsh-home"),
        "DSH_AGENTS_HOME": str(root / "agents-home"),
        "XDG_CONFIG_HOME": str(root / "xdg"),
        "npm_config_cache": str(root / "npm-cache"),
    }


@pytest.fixture(scope="session")
def bridge_native_runtime(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("dsh-bridge-rc2")
    configured = os.environ.get("_AI_DOTFILES_TEST_DSH_RUNTIME")
    runtime = Path(configured) if configured else root / "runtime"
    if configured:
        assert runtime.resolve().is_relative_to(
            Path("/private/tmp")
        ), "Native acceptance may reuse only a disposable /private/tmp installation"
    else:
        setup = subprocess.run(
            [
                "npm",
                "install",
                "--prefix",
                str(runtime),
                "--no-audit",
                "--no-fund",
                "--save-exact",
                f"@deepseek-ai/dsh@{PINNED_DSH}",
            ],
            env=_env(root),
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
        assert setup.returncode == 0, f"Required native setup FAILED:\n{setup.stderr}"
    package = runtime / "node_modules/@deepseek-ai/dsh/package.json"
    metadata = json.loads(package.read_text())
    assert metadata["name"] == "@deepseek-ai/dsh"
    assert metadata["version"] == PINNED_DSH
    for name in (
        "dsh-system-prompt",
        "dsh-tools",
        "dsh-agent-loop",
        "dsh-subagent",
        "dsh-tool-subagent",
        "dsh-subagent-spawn-in-process",
        "dsh-user-approval",
        "dsh-app-boot",
        "dsh-ptc-runtime-node",
    ):
        actual = json.loads((package.parent.parent / name / "package.json").read_text())
        assert actual["version"] == PINNED_DSH, f"Unexpected native {name} version"
    cli = subprocess.run(
        ["node", str(package.parent / metadata["bin"]["dsh"]), "--version"],
        env=_env(root),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert cli.returncode == 0, cli.stderr
    assert cli.stdout.strip() == PINNED_DSH
    return runtime


LOCAL_PROVIDER = r"""
import { LlmAdapter } from '@deepseek-ai/dsh-llm';
import { defineTool } from '@deepseek-ai/dsh-tools';
export const name = 'local-native-fixture';
export const inject = ['llm', 'tools'];
export function apply(ctx, config) {
  const evidence = { requests: [], executions: [], children: [], script: [] };
  ctx.provide('localEvidence', evidence);
  class LocalAdapter extends LlmAdapter {
    resolveModel(provider, model) { return Promise.resolve({ provider,
      id: model, name: model }); }
    async *stream(options) {
      evidence.requests.push(options);
      const chunks = evidence.script.shift();
      if (chunks === undefined) throw new Error('local provider script exhausted');
      for (const chunk of chunks) yield chunk;
    }
  }
  ctx.llm.registerAdapter(['local'], new LocalAdapter());
  for (const name of config.tools ?? ['read', 'read_image', 'write', 'bash',
    'edit', 'glob', 'grep']) {
    ctx.tools.register(defineTool({
      name, description: `Local fixture ${name}`, parameters: {},
      output: { schema: { type: 'string' }, render: (_args, value) => [{
        type: 'text', text: value }] },
      async execute() { evidence.executions.push(name); return `executed:${name}`; },
    }));
  }
  ctx.on('agent/created', ({ agent }) => {
    if (agent.session.header.origin === 'subagent') evidence.children.push(agent);
  });
}
"""

NATIVE_HELPERS = r"""
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { boot, auditStartupEntries } from '@deepseek-ai/dsh-app-boot';
import { createUserMessage, ToolCallId } from '@deepseek-ai/dsh-llm';
import { SessionId } from '@deepseek-ai/dsh-session';
import { renderPrompt } from '@deepseek-ai/dsh-system-prompt';
import * as bridge from './bridge.mjs';
import * as audit from './audit.mjs';
const fixture = JSON.parse(readFileSync(new URL('./fixture.json', import.meta.url)));
const configPath = new URL('./native.json', import.meta.url).pathname;
const ctx = await boot('dsh-native-test', configPath, undefined, undefined,
  import.meta.url);
const signal = new AbortController().signal;
let call = 0;
const execute = (name, agent, args = {}) => ctx.tools.execute({
  name, agent, arguments: args, signal, callId: ToolCallId(`test-${++call}`),
});
function text(text) {
  return [
    { type: 'block-start', index: 0, blockType: 'text' },
    { type: 'text-delta', index: 0, text },
    { type: 'block-end', index: 0, block: { type: 'text', text } },
    { type: 'finish', reason: { kind: 'stop' } },
  ];
}
function tool(name, args = {}) {
  const id = ToolCallId(`model-${++call}`);
  const argumentsJson = JSON.stringify(args);
  return [
    { type: 'block-start', index: 0, blockType: 'tool-call' },
    { type: 'tool-call-delta', index: 0, id, name, argumentsDelta: argumentsJson },
    { type: 'block-end', index: 0, block: { type: 'tool-call', id, name,
      arguments: argumentsJson } },
    { type: 'finish', reason: { kind: 'tool-calls' } },
  ];
}
async function createParent(extra = {}) {
  const handle = await ctx.agents.create({
    sessionId: SessionId(`parent-${++call}`),
    agentOptions: { provider: 'local', model: 'current-route', maxTokens: 321 },
    meta: { cwd: process.cwd() }, ...extra,
  });
  return handle;
}
function systemText(request) {
  return request.messages.filter(message => message.role === 'system')
    .flatMap(message => message.content).map(content => content.text ?? '').join('');
}
try {
"""


def _payload(
    tmp_path: Path, permissions: dict[str, object] | None = None
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    agent_path = tmp_path / "reviewer.md"
    agent_path.write_bytes(
        b'---\nname: reviewer\ndescription: "  Exact {{description}}  "\n'
        b"model: haiku\ntools: Read, Bash\ndisallowedTools: Write\n---\n"
        b"\r\n  Literal {{unknown}} and {{ bad reference }}  \r\n\r\n"
    )
    agent = render_agent(agent_path)
    rule_path = tmp_path / "literal.md"
    rule_path.write_bytes(
        b"---\ndescription: unconditional rule\n---\n\r\n  Rule {{unknown}} \r\n"
    )
    rule = render_rule(rule_path)
    policy = translate_permissions(permissions or {}, provenance=agent.provenance)
    config = build_bridge_config([agent], [rule], permissions=policy)
    assert agent.payload is not None
    requirements = bridge_audit_requirements(config).as_dict()
    return dict(config), [dict(agent.payload.row)], dict(requirements)


@pytest.fixture
def run_native(
    tmp_path: Path, bridge_native_runtime: Path
) -> Callable[..., dict[str, Any]]:
    def run(
        body: str,
        *,
        permissions: dict[str, object] | None = None,
        mode: str = "native",
        extra_rows: list[dict[str, Any]] | None = None,
        mutate: (
            Callable[[dict[str, Any], list[dict[str, Any]], dict[str, Any]], None]
            | None
        ) = None,
        native_tools: list[str] | None = None,
        preset: bool = False,
    ) -> dict[str, Any]:
        root = tmp_path / f"case-{len(list(tmp_path.glob('case-*')))}"
        root.mkdir()
        (root / "node_modules").symlink_to(
            bridge_native_runtime / "node_modules", target_is_directory=True
        )
        config, agents, requirements = _payload(root, permissions)
        if mutate is not None:
            mutate(config, agents, requirements)
        (root / "bridge.mjs").write_text(bridge_module_text())
        (root / "audit.mjs").write_text(audit_module_text())
        (root / "provider.mjs").write_text(LOCAL_PROVIDER)
        modules = (
            "llm",
            "session",
            "session-projection",
            "system-prompt",
            "tools",
            "agent",
            "agent-loop",
            "user-approval",
            "subagent",
            "subagent-spawn-in-process",
        )
        rows: list[dict[str, Any]] = [
            {"id": name, "name": f"@deepseek-ai/dsh-{name}"} for name in modules
        ]
        next(row for row in rows if row["id"] == "tools")["config"] = {"mode": mode}
        rows.append(
            {
                "id": "fixture-provider",
                "name": (root / "provider.mjs").as_uri(),
                "config": {} if native_tools is None else {"tools": native_tools},
            }
        )
        if mode != "native":
            rows.extend(
                {
                    "id": name,
                    "name": f"@deepseek-ai/dsh-{name}",
                    **(
                        {
                            "config": {
                                "mode": "danger-full-access",
                                "workspaceRoot": str(root),
                            }
                        }
                        if name == "sandbox-policy"
                        else {}
                    ),
                }
                for name in (
                    "fs-local",
                    "subprocess-local",
                    "sandbox-local",
                    "sandbox-policy",
                    "ptc-runtime-node",
                )
            )
        managed = list(agents)
        managed.append(
            {
                "id": "ai-dotfiles-bridge",
                "name": (root / "bridge.mjs").as_uri(),
                "config": config,
            }
        )
        managed.append(
            {
                "id": "ai-dotfiles-audit",
                "name": (root / "audit.mjs").as_uri(),
                "config": requirements,
            }
        )
        managed.extend(extra_rows or [])
        if preset:
            rows.extend(
                [
                    {
                        "id": "presets",
                        "name": "@deepseek-ai/dsh-agent-preset-registry",
                        "config": {"default": "parent"},
                    },
                    {
                        "id": "parent-preset",
                        "name": "@deepseek-ai/dsh-agent-preset",
                        "config": {
                            "id": "parent",
                            "plugins": [
                                {
                                    "id": "managed",
                                    "name": "cordis:group",
                                    "isolate": {
                                        "aiDotfilesAudit": True,
                                        "aiDotfilesBridge": True,
                                    },
                                    "config": managed,
                                }
                            ],
                        },
                    },
                ]
            )
        else:
            rows.extend(managed)
        (root / "native.json").write_text(json.dumps(rows))
        (root / "fixture.json").write_text(
            json.dumps({"config": config, "requirements": requirements})
        )
        script = NATIVE_HELPERS + body + "\n} finally { await ctx.fiber.dispose(); }\n"
        (root / "run.mjs").write_text(script)
        result = subprocess.run(
            ["node", str(root / "run.mjs")],
            cwd=root,
            env=_env(root),
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        assert (
            result.returncode == 0
        ), f"Native RC2 scenario FAILED:\n{result.stdout}\n{result.stderr}"
        return json.loads(result.stdout.splitlines()[-1])

    return run


def test_native_literal_schema_loader_and_real_named_child(
    run_native: Callable[..., Any],
) -> None:
    result = run_native(
        r"""
const report = await ctx.aiDotfilesAudit.run();
assert.equal(report.ready, true);
assert.equal(ctx.loader.getTasks().length, 0);
assert.equal(bridge.name, 'ai-dotfiles-bridge');
assert.equal(audit.name, 'ai-dotfiles-audit');
const assembly = await ctx.systemPrompt.assemble();
assert.equal(assembly.tools.find(
  tool => tool.name === 'ai_dotfiles_agent_reviewer').description,
    fixture.config.agents[0].description);
assert.ok(renderPrompt(assembly).includes(fixture.config.rules[0].body));
const handle = await createParent();
const parent = handle.agent;
ctx.localEvidence.script.push(text('real native child result'));
const delegated = await execute('ai_dotfiles_agent_reviewer', parent, {
  description: 'Check literal source', prompt: 'Perform check',
    run_in_background: false });
assert.equal(delegated.isError, false);
assert.ok(JSON.stringify(delegated).includes('real native child result'));
const child = ctx.localEvidence.children[0];
assert.equal(child.options.provider, 'local');
assert.equal(child.options.model, 'current-route');
assert.equal(child.options.maxTokens, 321);
assert.equal(ctx.approval.overrideOf(child.session), 'never');
const request = ctx.localEvidence.requests[0];
assert.ok(systemText(request).includes(fixture.config.agents[0].persona));
assert.deepEqual(request.tools.map(tool => tool.name).sort(), ['bash', 'read',
  'read_image']);
assert.equal(ctx.tools.get('write', parent).name, 'write');
assert.equal(ctx.tools.get('ai_dotfiles_agent_reviewer', parent).name,
  'ai_dotfiles_agent_reviewer');
await handle.dispose();
console.log(JSON.stringify({ ready: report.ready,
  childRequests: ctx.localEvidence.requests.length, route: child.options.model,
    persona: fixture.config.agents[0].persona }));
"""
    )
    assert result["ready"] is True
    assert result["childRequests"] == 1
    assert "\r\n" in result["persona"]


@pytest.mark.parametrize("mode", ["native", "ptc", "both"])
def test_native_descriptions_and_exact_persona_whitelist(
    run_native: Callable[..., Any], mode: str
) -> None:
    result = run_native(
        r"""
await ctx.aiDotfilesAudit.run();
const actual = fixture.config.agents[0];
const handle = await createParent({ setup: inner => {
  inner.systemPrompt.section({ name: 'deployment:persona-prefix', order: 0,
    text: actual.persona });
  inner.systemPrompt.section({ name: 'user:matching-text', order: 1,
    text: actual.persona });
} });
const assembly = await ctx.systemPrompt.assemble({ scope: handle.agent });
assert.equal(assembly.sections.find(
  section => section.name === 'deployment:persona-prefix').interpolate, false);
assert.equal(assembly.sections.find(
  section => section.name === 'user:matching-text').interpolate, undefined);
assert.throws(() => renderPrompt(assembly), /prompt variable/);
const different = await createParent({ setup: inner => {
  inner.systemPrompt.section({ name: 'deployment:persona-prefix', order: 0,
    text: actual.persona + ' user suffix' }); } });
const user = await ctx.systemPrompt.assemble({ scope: different.agent });
assert.equal(user.sections.find(
  section => section.name === 'deployment:persona-prefix').interpolate, undefined);
assert.throws(() => renderPrompt(user), /prompt variable/);
const host = await ctx.systemPrompt.assemble();
const roster = host.sections.find(
  section => section.name === 'ai-dotfiles:agent-descriptions');
assert.equal(roster.interpolate, false);
if (ctx.tools.get('run_code') !== undefined) assert.ok(roster.text.includes(
  actual.description));
else assert.equal(roster.text, '');
for (const schema of host.tools.filter(
  tool => tool.name === actual.toolName)) assert.equal(schema.description,
    actual.description);
await handle.dispose(); await different.dispose();
console.log(JSON.stringify({ roster: roster.text, schema: host.tools.map(
  tool => tool.name) }));
""",
        mode=mode,
    )
    assert ("  Exact {{description}}  " in result["roster"]) == (mode != "native")


def test_native_deny_is_monotonic_and_ptc_inner_calls_are_gated(
    run_native: Callable[..., Any],
) -> None:
    for mode in ("native", "ptc", "both"):
        result = run_native(
            r"""
await ctx.aiDotfilesAudit.run();
ctx.on('tools/pre-execute', async (_exec, _next) => ({ kind: 'allow' }), {
  prepend: true });
const handle = await createParent();
const blocked = ctx.tools.get('run_code') === undefined
  ? await execute('bash', handle.agent)
  : await execute('run_code', handle.agent, { description: 'Local denied call',
    code: 'return await tools.bash({});' });
assert.ok(JSON.stringify(blocked).includes('ai-dotfiles permissions deny tool'));
assert.deepEqual(ctx.localEvidence.executions, []);
await handle.dispose();
console.log(JSON.stringify({ denied: true }));
""",
            mode=mode,
            permissions={"deny": ["Bash"]},
        )
        assert result["denied"] is True


@pytest.mark.parametrize("decision", ["deny", "cancel", "ask", "allow"])
def test_native_ask_preserves_downstream_and_approval_never(
    run_native: Callable[..., Any], decision: str
) -> None:
    result = run_native(
        r"""
await ctx.aiDotfilesAudit.run();
const handle = await createParent();
const parent = handle.agent;
let approvalCalls = 0;
ctx.on('approval/request', async () => { approvalCalls++; return 'allowed-once'; });
ctx.on('tools/pre-execute', async (exec, next) => exec.name === 'bash' ? ({
  kind: DECISION, reason: 'downstream reason' }) : next());
ctx.localEvidence.script.push(tool('bash'), text('parent done'));
parent.followup(createUserMessage({ content: [{ type: 'text',
  text: 'Try action' }], source: { kind: 'user' } }));
await parent.whenIdle();
const events = parent.session.snapshotEvents();
const asked = events.filter(event => event.type === 'approval/asked');
assert.equal(asked.length, ['ask', 'allow'].includes(DECISION) ? 1 : 0);
assert.equal(approvalCalls, asked.length);
if (DECISION === 'ask') assert.equal(asked[0].data.reason, 'downstream reason');
if (DECISION === 'allow') assert.ok(asked[0].data.reason.includes('ai-dotfiles'));
if (DECISION === 'deny') assert.ok(JSON.stringify(events).includes(
  'downstream reason'));
if (DECISION === 'cancel') assert.equal(ctx.localEvidence.executions.length, 0);
ctx.localEvidence.script.push(tool('bash'), text('child refusal retained'));
const before = approvalCalls;
const delegated = await execute('ai_dotfiles_agent_reviewer', parent, {
  description: 'Ask inside child', prompt: 'Try action', run_in_background: false });
assert.equal(delegated.isError, false);
const child = ctx.localEvidence.children[0];
assert.equal(ctx.approval.overrideOf(child.session), 'never');
assert.equal(approvalCalls, before);
assert.equal(ctx.localEvidence.executions.length, ['ask', 'allow'].includes(
  DECISION) ? 1 : 0);
await handle.dispose();
console.log(JSON.stringify({ approvalCalls, decision: DECISION, never: true }));
""".replace(
            "DECISION", json.dumps(decision)
        ),
        permissions={"ask": ["Bash"]},
    )
    assert result["never"] is True


def test_bridge_builder_rejects_blocked_deferred_and_duplicate_sources(
    tmp_path: Path,
) -> None:
    config, _rows, _requirements = _payload(tmp_path)
    assert sorted(config["agents"][0]["requiredTools"]) == [
        "bash",
        "read",
        "read_image",
        "write",
    ]
    rendered = render_agent(tmp_path / "reviewer.md")
    blocked = translate_permissions(
        {"deny": ["Bash(cat *)"]}, provenance=rendered.provenance
    )
    with pytest.raises(ConfigError, match="blocked DSH permissions"):
        build_bridge_config([rendered], permissions=blocked)
    with pytest.raises(ConfigError, match="Duplicate"):
        build_bridge_config([rendered, rendered])
    with pytest.raises(ConfigError, match="non-empty native names"):
        DshAuditRequirements(required_tools=("",)).as_dict()
    source = tmp_path / "deferred.md"
    source.write_text("---\nname: deferred\ndescription: |\n  multiline\n---\nbody\n")
    with pytest.raises(ConfigError, match="DEFERRED"):
        build_bridge_config([render_agent(source)])


def test_audit_generator_config_module_and_ownership_drift(tmp_path: Path) -> None:
    from ai_dotfiles.core.dsh_install import (
        apply_dsh_install,
        output_drift,
        plan_dsh_install,
    )
    from ai_dotfiles.core.dsh_layout import project_layout

    assert DshAuditRequirements().as_dict()["generator"] == DSH_AUDIT_GENERATOR_VERSION
    assert f"// generator: {DSH_AUDIT_GENERATOR_VERSION}\n" in audit_module_text()
    assert (
        f"export const generator = {DSH_AUDIT_GENERATOR_VERSION};"
        in audit_module_text()
    )
    plan = plan_dsh_install(project_layout(tmp_path))
    result = apply_dsh_install(plan)
    output = next(
        item
        for item in plan.outputs
        if item.generators == {"audit": DSH_AUDIT_GENERATOR_VERSION}
    )
    record = result.inventory.records["ai-dotfiles/audit.mjs"]
    assert output_drift(output, record) == ()
    record["generators"] = {"audit": 1}
    assert output_drift(output, record) == ("generator changed",)


SELECTED_PRESET = r"""
const { createScope } = await import('@deepseek-ai/dsh-scope');
const scope = {};
Object.assign(scope, createScope(ctx, scope));
assert.equal(ctx.get('aiDotfilesAudit'), undefined);
assert.equal(ctx.get('aiDotfilesBridge'), undefined);
assert.equal((await ctx.agentPresets.resolve('parent')).id, 'parent');
const lease = await ctx.agentPresets.acquireScope('parent');
await lease[Symbol.asyncDispose]();
await ctx.agentPresets.mount(scope.ctx, 'parent');
const nativeAudit = ctx.agentPresets.serviceFor(scope, 'aiDotfilesAudit');
const impl = Object.getOwnPropertySymbols(ctx.reflect.store)
  .map(key => ctx.reflect.store[key]).find(impl => impl.value === nativeAudit);
assert.equal(impl.name, 'aiDotfilesAudit');
const tree = impl.fiber.entry.parent.tree;
assert.ok([...tree.entries()].includes(impl.fiber.entry));
assert.ok(![...ctx.loader.entries()].includes(impl.fiber.entry));
assert.equal(ctx.sessions.list().length, 0);
"""


def test_native_selected_preset_tree_settles_before_ready_and_real_child(
    run_native: Callable[..., Any],
) -> None:
    result = run_native(
        SELECTED_PRESET
        + r"""
assert.equal(audit.generator, fixture.requirements.generator);
assert.throws(() => audit.validateAuditConfig({ ...fixture.requirements,
  generator: 1 }), /schema or generator/);
writeFileSync(new URL('./late.mjs', import.meta.url), `
export const name = 'scoped-late';
export async function apply(ctx) {
  await new Promise(resolve => setTimeout(resolve, 25));
  ctx.provide('fixtureScopedLate', { settled: true });
}`);
const adding = tree.create({ id: 'scoped-late',
  name: new URL('./late.mjs', import.meta.url).href,
  isolate: { fixtureScopedLate: true } }, 'managed');
assert.ok(tree.getTasks().length > 0);
const req = { ...fixture.requirements,
  requiredIds: [...fixture.requirements.requiredIds, 'scoped-late'],
  requiredServices: [...fixture.requirements.requiredServices, 'fixtureScopedLate'] };
const report = await audit.auditReady(ctx, req, { scope });
await adding;
assert.equal(report.ready, true);
assert.equal(report.composition, 'selected');
assert.equal(ctx.agentPresets.serviceFor(scope, 'fixtureScopedLate').settled, true);
assert.equal(tree.getTasks().length, 0);
assert.deepEqual(await nativeAudit.run({ scope }), report);
assert.equal(ctx.sessions.list().length, 0);
// Another standing preset tree cannot create leaf-id collisions in this scope.
await ctx.loader.create({ id: 'unselected', name: '@deepseek-ai/dsh-agent-preset',
  config: { id: 'other', plugins: [{ id: 'managed', name: 'cordis:group',
    isolate: { aiDotfilesAudit: true, aiDotfilesBridge: true },
    config: tree.resolve('managed').options.config }] } });
await ctx.loader.await();
assert.equal((await ctx.agentPresets.resolve('other')).broken, undefined);
assert.equal((await audit.auditReady(ctx, req, { scope })).ready, true);
const handle = await createParent({ setup: async inner => {
  await ctx.agentPresets.mount(inner, 'parent');
} });
ctx.localEvidence.script.push(tool('read'), text('scoped native child result'));
const delegated = await execute('ai_dotfiles_agent_reviewer', handle.agent, {
  description: 'Use selected composition', prompt: 'Read', run_in_background: false,
});
assert.equal(delegated.isError, false);
const child = ctx.localEvidence.children[0];
assert.equal(ctx.agentPresets.composedPreset(child.ctx), 'parent');
assert.equal(child.options.model, 'current-route');
assert.equal(child.options.maxTokens, 321);
assert.ok(systemText(ctx.localEvidence.requests[0])
  .includes(fixture.config.agents[0].persona));
assert.deepEqual(ctx.localEvidence.requests[0].tools.map(item => item.name).sort(),
  ['bash', 'read', 'read_image']);
await handle.dispose(); await scope.dispose();
console.log(JSON.stringify({ ready: report.ready, inherited: 'parent' }));
""",
        preset=True,
    )
    assert result == {"ready": True, "inherited": "parent"}


@pytest.mark.parametrize(
    "kind",
    [
        "missing",
        "disabled",
        "import",
        "pending",
        "apply",
        "ambiguous",
        "filter",
        "options",
        "persona",
    ],
)
def test_native_selected_preset_required_rows_remain_strict(
    run_native: Callable[..., Any], kind: str
) -> None:
    result = run_native(
        SELECTED_PRESET
        + r"""
const kind = KIND;
const id = 'scoped-required';
const file = new URL('./scoped-required.mjs', import.meta.url);
let req = fixture.requirements;
if (['filter', 'options', 'persona'].includes(kind)) {
  const row = [...tree.entries()].find(entry =>
    entry.options.id === fixture.config.agents[0].rowId);
  const config = structuredClone(row.options.config);
  if (kind === 'filter') delete config.toolFilter;
  if (kind === 'options') config.agentOptions = { maxTokens: 1 };
  if (kind === 'persona') config.persona = 'changed literal body';
  await tree.update(row.options.id, { config });
} else {
  req = { ...fixture.requirements,
    requiredIds: [...fixture.requirements.requiredIds, id] };
  if (!['missing', 'import'].includes(kind)) writeFileSync(file,
    "export const name = 'scoped-required'; "
    + (kind === 'pending' ? "export const inject = ['missingScopedService']; " : '')
    + "export function apply() { "
    + (kind === 'apply' ? "throw new Error('scoped apply failed');" : '') + " }");
  if (kind !== 'missing') await tree.create({ id, name: file.href,
    disabled: kind === 'disabled' }, 'managed');
  if (kind === 'ambiguous') await ctx.loader.create({ id, name: file.href });
}
let report;
await assert.rejects(audit.auditReady(ctx, req, { scope }), error => {
  report = error.report;
  return error.name === 'DshReadinessError';
});
const expected = { missing: 'MISSING_ROW', disabled: 'DISABLED_ROW',
  import: 'IMPORT_FAILED', pending: 'PENDING_SERVICE', apply: 'APPLY_FAILED',
  ambiguous: 'AMBIGUOUS_ROW', filter: 'MANAGED_AGENT_FILTER',
  options: 'MANAGED_AGENT_OPTIONS', persona: 'MANAGED_AGENT_CONFIG' }[kind];
assert.ok(report.failures.some(item => item.code === expected));
if (['filter', 'options', 'persona'].includes(kind)) {
  await assert.rejects(nativeAudit.run({ scope }), error =>
    error.report.failures.some(item => item.code === expected));
} else {
  // The same foreign optional row remains a diagnostic rather than a fatal row.
  const foreign = await nativeAudit.run({ scope });
  assert.equal(foreign.ready, true);
  if (['import', 'pending', 'apply'].includes(kind)) {
    assert.ok(foreign.diagnostics.some(item => item.code === expected));
  }
}
assert.equal(ctx.sessions.list().length, 0);
await scope.dispose();
console.log(JSON.stringify({ refused: expected }));
""".replace(
            "KIND", json.dumps(kind)
        ),
        preset=True,
    )
    assert result["refused"] != ""


def test_native_selected_tree_without_provider_proof_refuses_ready(
    run_native: Callable[..., Any],
) -> None:
    result = run_native(
        SELECTED_PRESET
        + r"""
for (const id of ['ai-dotfiles-audit', 'ai-dotfiles-bridge']) {
  await tree.update(id, { disabled: true });
}
assert.equal(ctx.agentPresets.serviceFor(scope, 'aiDotfilesAudit'), undefined);
assert.equal(ctx.agentPresets.serviceFor(scope, 'aiDotfilesBridge'), undefined);
await assert.rejects(audit.auditReady(ctx, fixture.requirements, { scope }), error =>
  error.report.ready === false && error.report.failures.some(item =>
    item.code === 'SCOPED_TREE_UNAVAILABLE'));
assert.equal(ctx.sessions.list().length, 0);
await scope.dispose();
console.log(JSON.stringify({ unprovedRefused: true }));
""",
        preset=True,
    )
    assert result["unprovedRefused"] is True


def test_real_native_parent_preset_services_tools_and_child_inheritance(
    run_native: Callable[..., Any],
) -> None:
    result = run_native(
        r"""
writeFileSync(new URL('./parent-preset.mjs', import.meta.url), `
import { defineTool } from '@deepseek-ai/dsh-tools';
export const name = 'parent-composition';
export const inject = ['tools', 'systemPrompt'];
export function apply(ctx) {
  ctx.provide('fixtureParentService', { label: 'retained parent service' });
  ctx.systemPrompt.section({ name: 'parent:composition', order: 50,
    text: 'Retained parent composition', interpolate: false });
  for (const name of ['read', 'read_image', 'bash', 'write']) {
    ctx.tools.register(defineTool({ name, description: 'Preset-owned capability',
      parameters: {}, output: { schema: { type: 'string' },
        render: (_args, value) => [{ type: 'text', text: value }] },
      async execute() { return 'preset:' + name; } }));
  }
}
`);
await ctx.loader.create({ id: 'presets',
  name: '@deepseek-ai/dsh-agent-preset-registry', config: { default: 'parent' } });
await ctx.loader.create({ id: 'parent-preset', name: '@deepseek-ai/dsh-agent-preset',
  config: { id: 'parent', plugins: [{ id: 'parent-realm', name: 'cordis:group',
    isolate: { fixtureParentService: true }, config: [{ id: 'parent-composition',
      name: new URL('./parent-preset.mjs', import.meta.url).href }] }] } });
await ctx.loader.await();
await assert.rejects(ctx.aiDotfilesAudit.run(), error =>
  error.report.composition === 'pending'
  && error.report.failures.some(item => item.code === 'COMPOSITION_NOT_SELECTED'));
const handle = await createParent({ setup: async inner => {
  await inner.get('agentPresets').mount(inner);
} });
const parent = handle.agent;
const req = { ...fixture.requirements,
  requiredServices: [...fixture.requirements.requiredServices,
    'fixtureParentService'] };
const report = await audit.auditReady(ctx, req, { scope: parent });
assert.equal(report.composition, 'selected');
assert.equal(ctx.tools.get('read'), undefined);
assert.equal(ctx.tools.get('read', parent).description, 'Preset-owned capability');
let inherited;
ctx.on('agent/created', ({ agent }) => {
  if (agent.session.header.origin === 'subagent') inherited = {
    service: ctx.agentPresets.serviceFor(agent, 'fixtureParentService').label,
    preset: ctx.agentPresets.composedPreset(agent.ctx),
  };
});
ctx.localEvidence.script.push(tool('read'), text('preset child result'));
const result = await execute('ai_dotfiles_agent_reviewer', parent, {
  description: 'Use scoped parent service', prompt: 'Read', run_in_background: false,
});
assert.equal(result.isError, false);
assert.ok(JSON.stringify(result).includes('preset child result'));
assert.deepEqual(inherited, { service: 'retained parent service', preset: 'parent' });
const request = ctx.localEvidence.requests[0];
assert.ok(systemText(request).includes('Retained parent composition'));
assert.ok(systemText(request).includes(fixture.config.agents[0].persona));
assert.deepEqual(request.tools.map(item => item.name).sort(), ['bash', 'read',
  'read_image']);
assert.ok(JSON.stringify([...ctx.localEvidence.children[0].session.snapshotEvents()])
  .includes('preset:read'));
await handle.dispose();
console.log(JSON.stringify({ ready: report.ready, inherited }));
""",
        native_tools=[],
    )
    assert result["ready"] is True
    assert result["inherited"]["preset"] == "parent"


@pytest.mark.parametrize("kind", ["missing", "disabled", "import", "pending", "apply"])
def test_native_optional_startup_is_not_managed_readiness(
    run_native: Callable[..., Any],
    kind: str,
) -> None:
    result = run_native(
        r"""
await ctx.aiDotfilesAudit.run();
const id = 'ai-dotfiles-managed-test';
const kind = KIND;
if (kind !== 'missing') {
  const file = new URL('./managed-test.mjs', import.meta.url);
  if (kind !== 'import') writeFileSync(file,
    "export const name = 'managed-test'; "
    + (kind === 'pending' ? "export const inject = ['missingNativeService']; " : '')
    + "export function apply() { "
    + (kind === 'apply' ? "throw new Error('managed provider failed');" : '') + " }");
  await ctx.loader.create({ id, name: file.href, disabled: kind === 'disabled' });
}
await ctx.loader.await();
const warnings = [];
await auditStartupEntries(ctx, 'native', warning => warnings.push(warning));
const req = { ...fixture.requirements,
  requiredIds: [...fixture.requirements.requiredIds, id] };
let failure;
try { await audit.auditReady(ctx, req); }
catch (error) { failure = error.report.failures.find(item => item.id.endsWith(id)); }
assert.ok(failure);
const expected = { missing: 'MISSING_ROW', disabled: 'DISABLED_ROW',
  import: 'IMPORT_FAILED', pending: 'PENDING_SERVICE', apply: 'APPLY_FAILED' };
assert.equal(failure.code, expected[kind]);
if (kind === 'pending') assert.ok(failure.reason.includes('missingNativeService'));
if (kind === 'apply') assert.ok(failure.reason.includes('managed provider failed'));
assert.equal(warnings.length, ['missing', 'disabled'].includes(kind) ? 0 : 1);
// Foreign optional failures remain native warnings and report-only diagnostics.
const foreign = await audit.auditReady(ctx, fixture.requirements);
assert.equal(foreign.ready, true);
assert.equal(foreign.diagnostics.length, ['missing', 'disabled'].includes(
  kind) ? 0 : 1);
console.log(JSON.stringify({ code: failure.code, nativeWarnings: warnings.length }));
""".replace(
            "KIND", json.dumps(kind)
        )
    )
    assert result["code"] != ""


@pytest.mark.parametrize("mutation", ["drop", "widen", "swap", "empty-allow"])
def test_native_audit_rejects_changed_exact_agent_filters(
    run_native: Callable[..., Any],
    mutation: str,
) -> None:
    def mutate(
        _config: dict[str, Any], rows: list[dict[str, Any]], _req: dict[str, Any]
    ) -> None:
        native = rows[0]["config"]
        if mutation == "drop":
            native.pop("toolFilter")
        elif mutation == "widen":
            native["toolFilter"]["allow"].append("edit")
        elif mutation == "swap":
            native["toolFilter"] = {"deny": ["read", "read_image", "bash"]}
        else:
            native["toolFilter"] = {"allow": []}

    result = run_native(
        r"""
await assert.rejects(ctx.aiDotfilesAudit.run(), error =>
  error.report.failures.some(item => item.code === 'MANAGED_AGENT_FILTER'));
console.log(JSON.stringify({ refused: true }));
""",
        mutate=mutate,
    )
    assert result["refused"] is True


def test_native_complete_persona_and_missing_custom_profile_providers_fail(
    run_native: Callable[..., Any],
) -> None:
    result = run_native(
        r"""
await ctx.aiDotfilesAudit.run();
await assert.rejects(createParent({ setup: async inner => {
  const Persona = await import('@deepseek-ai/dsh-persona');
  await inner.plugin(Persona, { prefix: 'Complete native persona', complete: true });
} }), /complete persona mode is unsupported/);
assert.equal(ctx.localEvidence.requests.length, 0);
await ctx.loader.create({ id: 'disabled-spawn',
  name: '@deepseek-ai/dsh-subagent-spawn-in-process', disabled: true });
await ctx.loader.resolve('include:subagent-spawn-in-process').fiber.dispose();
ctx.loader.remove('include:subagent-spawn-in-process');
await ctx.loader.await();
await assert.rejects(ctx.aiDotfilesAudit.run(), error =>
  error.report.failures.some(
    item => item.code === 'MISSING_PROVIDER' && item.id === 'spawn'));
console.log(JSON.stringify({ completeRefused: true, providerRefused: true }));
"""
    )
    assert result["completeRefused"] is True


def test_native_missing_read_image_and_service_are_not_dropped(
    run_native: Callable[..., Any],
) -> None:
    result = run_native(
        r"""
await assert.rejects(ctx.aiDotfilesAudit.run(), error =>
  error.report.failures.some(
    item => item.code === 'MISSING_TOOL' && item.id === 'read_image'));
const req = { ...fixture.requirements,
  requiredServices: [...fixture.requirements.requiredServices,
    'requiredMissingService'] };
await assert.rejects(audit.auditReady(ctx, req), error =>
  error.report.failures.some(
    item => item.code === 'MISSING_SERVICE' && item.id === 'requiredMissingService'));
console.log(JSON.stringify({ missingImageRefused: true }));
""",
        native_tools=["read", "bash", "write"],
    )
    assert result["missingImageRefused"] is True


@pytest.mark.parametrize(
    "broken",
    [
        "schema",
        "generator",
        "blocked",
        "null-deny",
        "required",
        "contributions",
        "diagnostic",
    ],
)
def test_native_malformed_permission_policy_cannot_activate(
    run_native: Callable[..., Any],
    broken: str,
) -> None:
    def mutate(
        config: dict[str, Any], _rows: list[dict[str, Any]], _req: dict[str, Any]
    ) -> None:
        policy = config["permissions"]
        if broken == "schema":
            policy["schemaVersion"] = 42
        elif broken == "generator":
            policy["generator"] = 42
        elif broken == "blocked":
            policy["blocked"] = True
        elif broken == "null-deny":
            policy["deny"] = None
        elif broken == "required":
            policy["requiredTools"] = []
        elif broken == "contributions":
            policy["contributions"] = []
        else:
            policy["diagnostics"] = [{"blocking": True}]

    result = run_native(
        r"""
assert.equal(ctx.get('aiDotfilesBridge'), undefined);
await assert.rejects(ctx.aiDotfilesAudit.run(), error =>
  error.report.failures.some(item => item.code === 'APPLY_FAILED'
    && item.id.endsWith('ai-dotfiles-bridge')));
console.log(JSON.stringify({ malformedRefused: true }));
""",
        permissions={"deny": ["Bash"]},
        mutate=mutate,
    )
    assert result["malformedRefused"] is True


@pytest.mark.parametrize(
    "outcome", ["allowed-once", "rejected", "cancelled", "unavailable"]
)
def test_real_ptc_inner_ask_preserves_native_approval_outcomes(
    run_native: Callable[..., Any],
    outcome: str,
) -> None:
    result = run_native(
        r"""
await ctx.aiDotfilesAudit.run();
const handle = await createParent();
const parent = handle.agent;
let calls = 0;
ctx.on('approval/request', async () => { calls++; return OUTCOME; });
ctx.localEvidence.script.push(tool('run_code', {
  description: 'Run local approval action', code: 'return await tools.bash({});',
}), text('approval outcome retained'));
parent.followup(createUserMessage({ content: [{ type: 'text', text: 'Try action' }],
  source: { kind: 'user' } }));
await parent.whenIdle();
assert.equal(calls, 1);
assert.equal(ctx.localEvidence.executions.length, OUTCOME === 'allowed-once' ? 1 : 0);
assert.equal(ctx.sandboxPolicy.resolve({ session: parent.session }).mode,
  'danger-full-access');
const decisions = parent.session.snapshotEvents()
  .filter(event => event.type === 'approval/decided');
assert.equal(decisions[0].data.outcome, OUTCOME);
assert.equal(ctx.localEvidence.requests.length, 2);
await handle.dispose();
console.log(JSON.stringify({ outcome: decisions[0].data.outcome, calls }));
""".replace(
            "OUTCOME", json.dumps(outcome)
        ),
        mode="ptc",
        permissions={"ask": ["Bash"]},
    )
    assert result["outcome"] == outcome


def test_ask_preserves_real_sandbox_policy_and_native_denial(
    run_native: Callable[..., Any],
) -> None:
    result = run_native(
        r"""
await ctx.loader.create({ id: 'sandbox-policy', name: '@deepseek-ai/dsh-sandbox-policy',
  config: { mode: 'read-only', workspaceRoot: process.cwd() } });
await ctx.loader.await();
await ctx.aiDotfilesAudit.run();
const handle = await createParent();
const parent = handle.agent;
const policy = ctx.sandboxPolicy.resolve({ session: parent.session });
let approvalCalls = 0;
ctx.on('approval/request', async () => { approvalCalls++; return 'allowed-once'; });
ctx.on('tools/pre-execute', async (exec, next) => {
  const downstream = await next();
  const actual = ctx.sandboxPolicy.resolve({ session: exec.agent.session });
  return exec.name === 'bash' && actual.mode === 'read-only'
    ? { kind: 'deny', reason: 'retained sandbox policy denial' } : downstream;
});
ctx.localEvidence.script.push(tool('bash'), text('sandbox denial retained'));
parent.followup(createUserMessage({ content: [{ type: 'text', text: 'Try action' }],
  source: { kind: 'user' } }));
await parent.whenIdle();
assert.equal(approvalCalls, 0);
assert.deepEqual(ctx.localEvidence.executions, []);
assert.deepEqual(ctx.sandboxPolicy.resolve({ session: parent.session }), policy);
assert.ok(JSON.stringify([...parent.session.snapshotEvents()])
  .includes('retained sandbox policy denial'));
ctx.localEvidence.script.push(tool('bash'), text('child keeps sandbox denial'));
await execute('ai_dotfiles_agent_reviewer', parent, {
  description: 'Retain sandbox', prompt: 'Try action', run_in_background: false,
});
const child = ctx.localEvidence.children[0];
const childPolicy = ctx.sandboxPolicy.resolve({ session: child.session });
assert.equal(childPolicy.mode, policy.mode);
assert.equal(childPolicy.workspaceRoot, policy.workspaceRoot);
assert.equal(childPolicy.sessionId, child.id);
assert.equal(approvalCalls, 0);
assert.deepEqual(ctx.localEvidence.executions, []);
await handle.dispose();
console.log(JSON.stringify({ mode: policy.mode, neverBypassed: true }));
""",
        permissions={"ask": ["Bash"]},
    )
    assert result["mode"] == "read-only"


def test_native_unique_leaf_and_qualified_ids_reject_ambiguity(
    run_native: Callable[..., Any],
) -> None:
    result = run_native(
        r"""
await ctx.aiDotfilesAudit.run();
for (const id of ['tree-a', 'tree-b']) {
  const file = new URL(`./${id}.json`, import.meta.url);
  writeFileSync(file, JSON.stringify([{ id: 'shared-leaf',
    name: new URL('./empty.mjs', import.meta.url).href }]));
  writeFileSync(new URL('./empty.mjs', import.meta.url),
    "export const name = 'empty'; export function apply() {};");
  await ctx.loader.create({ id, name: 'cordis:include', config: { path: file.href } });
}
await ctx.loader.await();
const ambiguous = { ...fixture.requirements,
  requiredIds: [...fixture.requirements.requiredIds, 'shared-leaf'] };
await assert.rejects(audit.auditReady(ctx, ambiguous), error =>
  error.report.failures.some(item => item.code === 'AMBIGUOUS_ROW'));
const qualified = { ...fixture.requirements,
  requiredIds: ['include:ai-dotfiles-bridge', 'include:ai-dotfiles-audit',
    'include:ai-dotfiles-agent-reviewer', 'tree-a:shared-leaf'] };
const report = await audit.auditReady(ctx, qualified);
assert.equal(report.ready, true);
console.log(JSON.stringify({ qualifiedReady: true, ambiguousRefused: true }));
"""
    )
    assert result["ambiguousRefused"] is True


def test_native_exact_empty_allow_and_legitimate_partial_options(
    run_native: Callable[..., Any],
) -> None:
    def mutate(
        config: dict[str, Any], rows: list[dict[str, Any]], req: dict[str, Any]
    ) -> None:
        source = Path(config["agents"][0]["provenance"]["source"])
        source.write_bytes(
            source.read_bytes().replace(b"tools: Read, Bash", b"tools: []")
        )
        rendered = render_agent(source, native_agent_options={"maxTokens": 17})
        assert rendered.payload is not None
        literal = render_rule(source.parent / "literal.md")
        new = build_bridge_config([rendered], [literal])
        config.clear()
        config.update(new)
        rows[:] = [dict(rendered.payload.row)]
        req.clear()
        req.update(bridge_audit_requirements(new).as_dict())

    result = run_native(
        r"""
const report = await ctx.aiDotfilesAudit.run();
assert.equal(report.ready, true);
const handle = await createParent();
ctx.localEvidence.script.push(text('no tool child result'));
const result = await execute('ai_dotfiles_agent_reviewer', handle.agent, {
  description: 'Empty capability filter', prompt: 'Answer', run_in_background: false,
});
assert.equal(result.isError, false);
const child = ctx.localEvidence.children[0];
assert.equal(child.options.model, 'current-route');
assert.equal(child.options.provider, 'local');
assert.equal(child.options.maxTokens, 17);
assert.equal(ctx.localEvidence.requests[0].tools, undefined);
await handle.dispose();
console.log(JSON.stringify({ exactEmpty: true, partialOptions: true }));
""",
        mutate=mutate,
    )
    assert result["partialOptions"] is True


def test_native_allow_diagnostics_grant_nothing_and_approval_is_optional(
    run_native: Callable[..., Any],
) -> None:
    result = run_native(
        r"""
const report = await ctx.aiDotfilesAudit.run();
assert.equal(report.ready, true);
await ctx.loader.resolve('include:user-approval').fiber.dispose();
ctx.loader.remove('include:user-approval');
await ctx.loader.await();
assert.equal(ctx.get('approval'), undefined);
const noApproval = await ctx.aiDotfilesAudit.run();
assert.equal(noApproval.ready, true);
assert.equal(fixture.config.permissions.diagnostics[0].code, 'ALLOW_UNMAPPED');
assert.deepEqual(fixture.config.permissions.deny, []);
assert.deepEqual(fixture.config.permissions.ask, []);
const handle = await createParent();
const blocked = await execute('bash', handle.agent);
assert.equal(blocked.isError, true);
assert.ok(JSON.stringify(blocked).includes('requires approval'));
assert.deepEqual(ctx.localEvidence.executions, []);
await handle.dispose();
console.log(JSON.stringify({ noGrants: true, optionalApproval: true }));
""",
        permissions={"allow": ["Bash"]},
        extra_rows=[
            {
                "id": "native-existing-policy",
                "name": "data:text/javascript,"
                + "export const name='existing-native-policy';"
                "export function apply(ctx){"
                "ctx.on('tools/pre-execute',async()=>({kind:'ask'}));}",
            }
        ],
    )
    assert result["noGrants"] is True
