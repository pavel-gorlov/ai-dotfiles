"""Required same-host RC2 and installed-wheel acceptance, without live services.

Missing runtime/providers are failures, never skips. Fixtures use only disposable
homes, finite child environments, a local scripted LLM, and local MCP/hooks. The
actual production launcher owns boot/audit/readiness and stock child composition.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tarfile
import zipfile
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import metadata
from pathlib import Path
from threading import Thread

import pytest

from ai_dotfiles.core.dsh_launch import prepare_dsh_launch
from ai_dotfiles.core.dsh_native import DshNativeRuntime
from tests.e2e.test_dsh_launch import (
    WEB_PROOF,
    _bytes,
)
from tests.e2e.test_dsh_launch import (
    managed_fixture as _managed_fixture,
)

managed_fixture = _managed_fixture
pytestmark = [pytest.mark.integration, pytest.mark.dsh_runtime]

PERSONA = "\r\n  CHILD BODY {{unknown}} and {{ bad reference }}  \r\n\r\n"
DESCRIPTION = "  Exact child {{description}}. Keep whitespace.  "


def _run_command(
    command: list[str], *, cwd: Path, env: dict[str, str], logs: Path, timeout: int = 60
) -> subprocess.CompletedProcess[str]:
    logs.mkdir(parents=True, exist_ok=True)
    stem = logs / str(len(list(logs.glob("*.json"))))
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    stem.with_suffix(".stdout").write_text(result.stdout)
    stem.with_suffix(".stderr").write_text(result.stderr)
    stem.with_suffix(".json").write_text(
        json.dumps(
            {
                "argv": command,
                "cwd": str(cwd),
                "exit": result.returncode,
                "isolatedEnvironment": {
                    key: env[key]
                    for key in (
                        "HOME",
                        "DSH_HOME",
                        "DSH_AGENTS_HOME",
                        "AI_DOTFILES_HOME",
                        "XDG_CONFIG_HOME",
                    )
                    if key in env
                },
                "stdout": str(stem.with_suffix(".stdout")),
                "stderr": str(stem.with_suffix(".stderr")),
            }
        )
    )
    return result


SCRIPTED_PROVIDER = r"""
import assert from 'node:assert/strict';
import { LlmAdapter } from '@deepseek-ai/dsh-llm';
import { defineTool } from '@deepseek-ai/dsh-tools';
import { livePresetMounts, standingMountFor }
  from '@deepseek-ai/dsh-agent-preset-registry';
import { appendFileSync, readFileSync } from 'node:fs';
export const inject = ['llm', 'tools', 'systemPrompt', 'approval'];
const record = value => appendFileSync(process.env.PROOF,
  JSON.stringify(value) + '\n');
const counters = { parent: 0, child: 0 };
let nextId = 0;
let nextTree = 0;
const treeIds = new WeakMap();
function treeEvidence(mount) {
  if (mount === undefined) return undefined;
  if (!treeIds.has(mount.tree)) treeIds.set(mount.tree, ++nextTree);
  const entries = [...mount.tree.entries()];
  const audit = entries.find(entry => entry.options.id === 'ai-dotfiles-audit');
  return {preset:mount.presetId,tree:treeIds.get(mount.tree),
    required:audit?.fiber?.ctx.get('aiDotfilesAudit')?.config.requiredIds,
    entries:entries.map(entry=>({id:entry.id,leaf:entry.options.id,
      state:entry.fiber?.state,disabled:entry.disabled}))};
}
function text(value) { return [
  {type:'block-start',index:0,blockType:'text'},
  {type:'text-delta',index:0,text:value},
  {type:'block-end',index:0,block:{type:'text',text:value}},
  {type:'finish',reason:{kind:'stop'}}]; }
function call(name, args = {}) {
  const id = `acceptance-${++nextId}`;
  const argumentsJson = JSON.stringify(args);
  return [{type:'block-start',index:0,blockType:'tool-call'},
    {type:'tool-call-delta',index:0,id,name,argumentsDelta:argumentsJson},
    {type:'block-end',index:0,block:{type:'tool-call',id,name,
      arguments:argumentsJson}}, {type:'finish',reason:{kind:'tool-calls'}}];
}
export function apply(ctx) {
  class Local extends LlmAdapter {
    resolveModel(provider, model) {
      return Promise.resolve({provider,id:model,name:model});
    }
    async *stream(options) {
      const system = options.messages.filter(message => message.role === 'system')
        .flatMap(message => message.content).map(block => block.text ?? '').join('');
      const kind = system.includes(process.env.EXPECT_PERSONA) ? 'child' : 'parent';
      const step = counters[kind]++;
      record({event:'turn',kind,step,model:options.model,system,
        tools:options.tools,messages:options.messages,env:process.env.FIXTURE_ENV,
        resource:readFileSync(new URL('./profile-resource.txt',import.meta.url),
          'utf8')});
      const actions = kind === 'child'
        ? [call('read'),call('write'),call('bash'),call('mcp__stdio__ping'),
           ...(process.env.HTTP_MCP ? [call('mcp__http__ping')] : []),
           text('actual child completed')]
        : [call('ai_dotfiles_agent_reviewer', {description:'Native acceptance',
           prompt:'Run the literal child',run_in_background:false}),
           call('run_code',{description:'Parent ask',
             code:'return await tools.bash({});'}),
           call('run_code',{description:'Parent deny',
             code:'return await tools.write({});'}),
           text('actual parent completed')];
      assert.ok(actions[step], `Unexpected ${kind} step ${step}`);
      for (const chunk of actions[step]) yield chunk;
    }
  }
  ctx.llm.registerAdapter(['local'],new Local());
  for (const name of ['read','read_image','write','bash']) ctx.tools.register(
    defineTool({name,description:`local ${name}`,parameters:{},
      output:{schema:{type:'string'},render:(_args,value)=>[{type:'text',text:value}]},
      async execute() { record({event:'executed',name});
        return `executed:${name}`; }}));
  ctx.on('approval/request', async () => {
    record({event:'approval-request'}); return 'allowed-once';
  });
  ctx.on('tools/result', (exec,result) => record({event:'tool-result',name:exec.name,
    origin:exec.agent?.session.header.origin,result}));
  ctx.on('agent/created', async ({agent}) => {
    const presets = ctx.get('agentPresets');
    const preset = presets?.composedPreset(agent.ctx);
    const serviceFor = name => presets?.serviceFor(agent,name)
      ?? agent.ctx.get(name);
    record({event:'agent',id:agent.id,origin:agent.session.header.origin,
      options:agent.options,preset,approval:ctx.approval.overrideOf(agent.session),
      required:serviceFor('aiDotfilesAudit')?.config.requiredIds,
      selectedTree:treeEvidence(standingMountFor(agent.ctx)),
      services:['llm','tools','systemPrompt','subagents','aiDotfilesAudit',
        'aiDotfilesBridge'].map(name =>
        [name,serviceFor(name) !== undefined])});
  });
  ctx.on('session/event', (session,event) => {
    if (event.type === 'hook/result') record({event:'hook-result',
      origin:session.header.origin,sessionId:session.id,data:event.data});
  });
  ctx.appReady.onReady(() => {
    let root=ctx.fiber;
    while (root.parent.fiber !== root) root=root.parent.fiber;
    record({event:'ready',selectedTrees:livePresetMounts(root)
      .filter(mount=>mount.presetId === 'standard').map(treeEvidence),
    tasks:ctx.loader.getTasks().length,sessions:ctx.get('sessions').list().length,
    entries:[...ctx.loader.entries()].map(entry=>entry.id),
    required:ctx.get('aiDotfilesAudit')?.config.requiredIds,
    nativeConfig:ctx.get('nativeConfigEvidence')});
  });
}
"""

STDIO_MCP = r"""
import {createInterface} from 'node:readline';
import {appendFileSync} from 'node:fs';
createInterface({input:process.stdin}).on('line',line=> {
  const request=JSON.parse(line);
  appendFileSync(process.env.MCP_PROOF,JSON.stringify(request)+'\n');
  if (request.id === undefined) return;
  const result=request.method === 'initialize'
    ? {protocolVersion:request.params.protocolVersion,capabilities:{tools:{}},
       serverInfo:{name:'isolated',version:'1'}}
    : request.method === 'tools/list'
      ? {tools:[{name:'ping',description:'real local stdio',
          inputSchema:{type:'object',properties:{}}}]}
      : {content:[{type:'text',text:'local MCP actually called'}]};
  process.stdout.write(JSON.stringify({jsonrpc:'2.0',id:request.id,result})+'\n');
});
"""


@pytest.fixture
def runtime_case(
    managed_fixture: tuple[Path, Path, DshNativeRuntime, dict[str, str]],
    dsh_native_runtime: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, DshNativeRuntime, dict[str, str]]:
    project, profile, runtime, env = managed_fixture
    assert runtime.package_dir == dsh_native_runtime / "node_modules/@deepseek-ai/dsh"
    env["EXPECT_PERSONA"] = PERSONA
    env["DSH_AGENTS_HOME"] = str(tmp_path / "agents-home")
    env["MCP_PROOF"] = str(tmp_path / "mcp.jsonl")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    (profile / "provider.mjs").write_text(SCRIPTED_PROVIDER)
    patches = json.loads((profile / "cordis.patch.yml").read_text())
    rows = patches[0]["insert"]
    next(row for row in rows if row["id"] == "tools")["config"] = {"mode": "both"}
    for name in (
        "user-approval",
        "subagent",
        "subagent-spawn-in-process",
        "fs-local",
        "subprocess-local",
        "sandbox-local",
        "sandbox-policy",
        "bash-sandbox",
        "ptc-runtime-node",
    ):
        rows.append({"id": name, "name": f"@deepseek-ai/dsh-{name}"})
    (profile / "cordis.patch.yml").write_text(json.dumps(patches))
    catalog = Path(env["AI_DOTFILES_HOME"]) / "catalog"
    domain = catalog / "acceptance"
    (domain / "agents").mkdir(parents=True)
    (domain / "agents/reviewer.md").write_bytes(
        (
            "---\nname: reviewer\ndescription: "
            + json.dumps(DESCRIPTION)
            + "\nmodel: haiku\n---\n"
            + PERSONA
        ).encode()
    )
    (domain / "mcp.mjs").write_text(STDIO_MCP)
    (domain / "settings.fragment.json").write_text(
        json.dumps(
            {
                "permissions": {"deny": ["Write"], "ask": ["Bash"]},
            }
        )
    )
    (domain / "mcp.fragment.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "stdio": {
                        "command": str(runtime.node),
                        "args": [str(domain / "mcp.mjs")],
                        "env": {"MCP_PROOF": env["MCP_PROOF"]},
                    }
                },
            }
        )
    )
    (project / "ai-dotfiles.json").write_text(
        '{"targets":["dsh"],"packages":["@acceptance"],"link_mode":"copy"}'
    )
    return project, profile, runtime, env


def test_same_managed_host_actually_invokes_named_stock_child_and_native_gates(
    runtime_case: tuple[Path, Path, DshNativeRuntime, dict[str, str]], tmp_path: Path
) -> None:
    project, profile, runtime, env = runtime_case
    before = _bytes(profile.parent.parent)
    plan = prepare_dsh_launch(
        ["proof", "acceptance", "--json"], cwd=project, process_env=env, runtime=runtime
    )
    assert any(item.code == "MODEL_UNMAPPED" for item in plan.diagnostics)
    result = _run_command(
        [
            os.sys.executable,
            "-m",
            "ai_dotfiles",
            "dsh",
            "launch",
            "proof",
            "acceptance",
            "--json",
        ],
        cwd=project,
        env=env,
        logs=tmp_path / "commands",
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    events = [json.loads(line) for line in Path(env["PROOF"]).read_text().splitlines()]
    assert events[0]["event"] == "ready" and events[0]["tasks"] == 0
    assert events[0]["sessions"] == 0
    assert all(
        any(entry.endswith(":" + required) for entry in events[0]["entries"])
        for required in events[0]["required"]
    )
    assert "Managed DSH audit passed; native surface released" in result.stderr
    child = next(
        item
        for item in events
        if item.get("origin") == "subagent" and item["event"] == "agent"
    )
    assert child["options"]["model"] == "parent-current"
    assert child["options"]["provider"] == "local" and child["approval"] == "never"
    assert all(present for _, present in child["services"])
    child_turns = [item for item in events if item.get("kind") == "child"]
    assert len(child_turns) == 5 and PERSONA in child_turns[0]["system"]
    assert {"read", "read_image", "write", "bash", "mcp__stdio__ping"} <= {
        tool["name"] for tool in child_turns[0]["tools"]
    }
    parent = next(item for item in events if item.get("kind") == "parent")
    assert DESCRIPTION in parent["system"]
    assert (
        next(
            tool
            for tool in parent["tools"]
            if tool["name"] == "ai_dotfiles_agent_reviewer"
        )["description"]
        == DESCRIPTION
    )
    assert [item["name"] for item in events if item["event"] == "executed"] == [
        "read",
        "bash",
    ]
    assert sum(item["event"] == "approval-request" for item in events) == 1
    assert any(
        item["event"] == "tool-result"
        and item["name"] == "bash"
        and item.get("origin") == "subagent"
        and item["result"]["isError"]
        for item in events
    )
    child_results = {
        item["name"]: item["result"]
        for item in events
        if item["event"] == "tool-result" and item.get("origin") == "subagent"
    }
    assert (
        child_results["write"]["error"]["message"]
        == 'ai-dotfiles permissions deny tool "write"'
    )
    assert child_results["bash"]["error"]["message"] == 'the user rejected tool "bash"'
    assert child_results["mcp__stdio__ping"]["isError"] is False
    ptc_success = next(
        item["result"]
        for item in events
        if item["event"] == "tool-result"
        and item["name"] == "run_code"
        and item["result"]["isError"] is False
    )
    assert ptc_success["value"]["sandbox"] == {
        "mode": "read-only",
        "denied": False,
        "enforcement": "full",
    }
    assert "actual child completed" in json.dumps(events)
    assert "actual parent completed" in result.stdout
    assert "tools/call" in Path(env["MCP_PROOF"]).read_text()
    assert _bytes(profile.parent.parent) == before


@pytest.fixture
def http_mcp(tmp_path: Path) -> Iterator[tuple[str, list[dict[str, object]]]]:
    """A loopback-only fake MCP peer; the published native client is exercised."""
    observations: list[dict[str, object]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            self.send_response(405)
            self.end_headers()

        def do_POST(self) -> None:
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            observations.append({"request": request, "headers": dict(self.headers)})
            (tmp_path / "http-mcp.json").write_text(json.dumps(observations))
            if "id" not in request:
                self.send_response(202)
                self.end_headers()
                return
            result = (
                {
                    "protocolVersion": request["params"]["protocolVersion"],
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "local-http", "version": "1"},
                }
                if request["method"] == "initialize"
                else (
                    {
                        "tools": [
                            {
                                "name": "ping",
                                "description": "local HTTP peer",
                                "inputSchema": {"type": "object", "properties": {}},
                            }
                        ]
                    }
                    if request["method"] == "tools/list"
                    else {
                        "content": [
                            {"type": "text", "text": "local HTTP actually called"}
                        ]
                    }
                )
            )
            body = json.dumps(
                {"jsonrpc": "2.0", "id": request["id"], "result": result}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/mcp", observations
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


@pytest.mark.parametrize("surface", ["headless", "web"])
@pytest.mark.parametrize("override", ["project", "cli"])
def test_same_host_native_precedence_global_project_http_hooks_and_scoped_child(
    runtime_case: tuple[Path, Path, DshNativeRuntime, dict[str, str]],
    http_mcp: tuple[str, list[dict[str, object]]],
    tmp_path: Path,
    surface: str,
    override: str,
) -> None:
    project, profile, runtime, env = runtime_case
    url, requests = http_mcp
    env["HTTP_MCP"] = "1"
    catalog = Path(env["AI_DOTFILES_HOME"]) / "catalog"
    global_domain = catalog / "global-acceptance"
    (global_domain / "agents").mkdir(parents=True)
    (global_domain / "agents/reviewer.md").write_text(
        "---\nname: reviewer\ndescription: Global shadowed description\n"
        "---\nGLOBAL SHADOWED BODY"
    )
    (global_domain / "agents/globalonly.md").write_text(
        "---\nname: globalonly\ndescription: Global survives\n---\nGlobal body"
    )
    project_domain = catalog / "acceptance"
    for domain, scope in ((global_domain, "global"), (project_domain, "project")):
        (domain / "hooks").mkdir()
        (domain / "hooks/observe.mjs").write_text(
            "import {readFileSync} from 'node:fs';\n"
            "const payload=JSON.parse(readFileSync(0,'utf8'));\n"
            f"process.stderr.write(JSON.stringify({{scope:'{scope}',payload}})+'\\n');\n"
            "process.stdout.write(JSON.stringify({hookSpecificOutput:{"
            "hookEventName:payload.hook_event_name,"
            f"additionalContext:'actual {scope} hook'}}}}));\n"
        )
        path = domain / "settings.fragment.json"
        settings = json.loads(path.read_text()) if path.exists() else {}
        settings["env"] = {"FIXTURE_ENV": scope}
        settings["hooks"] = {
            event: [
                {"hooks": [{"type": "command", "command": "node hooks/observe.mjs"}]}
            ]
            for event in (
                "UserPromptSubmit",
                "PreToolUse",
                "SubagentStart",
                "SubagentStop",
            )
        }
        path.write_text(json.dumps(settings))
        (domain / "dsh.fragment.json").write_text(
            json.dumps([{"id": "user-config", "config": {scope: True}}])
        )
    mcp = project_domain / "mcp.fragment.json"
    values = json.loads(mcp.read_text())
    values["mcpServers"]["http"] = {
        "type": "http",
        "url": url,
        "headers": {"X-Local-Sentinel": "local-header"},
    }
    mcp.write_text(json.dumps(values))
    (Path(env["AI_DOTFILES_HOME"]) / "global.json").write_text(
        '{"targets":["dsh"],"packages":["@global-acceptance"]}'
    )
    (profile / "config-observer.mjs").write_text(
        "export function apply(ctx,config) { "
        "ctx.provide('nativeConfigEvidence',config); }\n"
    )
    profile_patches = json.loads((profile / "cordis.patch.yml").read_text())
    observer = {
        "id": "user-config",
        "name": "./config-observer.mjs",
        "config": {"profile": True, "discarded": "must disappear"},
    }
    profile_patches[0]["insert"].append(observer)
    (profile / "cordis.patch.yml").write_text(json.dumps(profile_patches))
    (profile.parent.parent / "cordis.patch.yml").write_text(
        json.dumps([{"id": "user-config", "config": {"home": True}}])
    )
    cli_patch = tmp_path / "cli.json"
    cli_patch.write_text(json.dumps([{"id": "user-config", "config": {"cli": True}}]))
    args = ["proof", "--patch", str(cli_patch), "acceptance", "--json"]
    if surface == "web":
        (profile / "package.json").write_text(
            json.dumps(
                {
                    "dsh": {
                        "profile": {
                            "bundles": [
                                "@deepseek-ai/dsh-base",
                                "@deepseek-ai/dsh-web-app",
                            ]
                        }
                    }
                }
            )
        )
        (profile / "web-proof.mjs").write_text(WEB_PROOF)
        patches = [
            {"id": name, "disabled": True}
            for name in ("session-title-llm", "tool-bash", "tool-fs", "tool-fs-search")
        ]
        patches.extend(
            [
                {
                    "id": "agent-default-model",
                    "config": {"provider": "local", "model": "parent-current"},
                },
                {"id": "tools", "config": {"mode": "both"}},
                {
                    "insert": [
                        row
                        for row in profile_patches[0]["insert"]
                        if row["id"]
                        in ("local-provider", "user-relative-include", "user-config")
                    ]
                },
                {"insert": [{"id": "native-web-proof", "name": "./web-proof.mjs"}]},
                {
                    "id": "storage-json",
                    "config": {"root": str(tmp_path / "state/storages")},
                },
                {
                    "id": "session-persistence-jsonl",
                    "config": {"root": str(tmp_path / "state/sessions")},
                },
                {
                    "id": "credentials",
                    "config": {"path": str(tmp_path / "state/credentials.yaml")},
                },
            ]
        )
        (profile / "cordis.patch.yml").write_text(json.dumps(patches))
        args = ["proof", "--patch", str(cli_patch), "--no-open", "--port", "0"]
    if override == "project":
        args = [value for index, value in enumerate(args) if index not in (1, 2)]
    before = _bytes(profile.parent.parent)
    plan = prepare_dsh_launch(args, cwd=project, process_env=env, runtime=runtime)
    assert plan.request["inspected"]["selection"] == (
        {"kind": "global"}
        if surface == "headless"
        else {"kind": "preset", "id": "standard", "entryId": "preset-standard"}
    )
    assert (
        sum(row["id"] == "ai-dotfiles-agent-reviewer" for row in plan.config.rows) == 1
    )
    assert any(item.name == "hooks" for item in plan.config.contributions)
    result = _run_command(
        [os.sys.executable, "-m", "ai_dotfiles", "dsh", "launch", *args],
        cwd=project,
        env=env,
        logs=tmp_path / "commands",
        timeout=45,
    )
    assert result.returncode == (0 if surface == "headless" else 23), (
        result.stdout + result.stderr
    )
    events = [json.loads(line) for line in Path(env["PROOF"]).read_text().splitlines()]
    assert events[0]["event"] == "ready" and events[0]["tasks"] == 0
    assert events[0]["nativeConfig"] == {override: True}
    assert events[0]["sessions"] == 0
    if surface == "headless":
        assert all(
            any(entry.endswith(":" + required) for entry in events[0]["entries"])
            for required in events[0]["required"]
        )
    assert "Managed DSH audit passed; native surface released" in result.stderr
    child = next(
        row
        for row in events
        if row["event"] == "agent" and row.get("origin") == "subagent"
    )
    assert set(child["required"]) == {
        "ai-dotfiles-agent-globalonly",
        "ai-dotfiles-agent-reviewer",
        "ai-dotfiles-audit",
        "ai-dotfiles-bridge",
        "ai-dotfiles-hooks",
        "ai-dotfiles-mcp-stdio",
        "ai-dotfiles-mcp-http",
    }
    if surface == "web":
        (selected,) = events[0]["selectedTrees"]
        assert selected["preset"] == "standard"
        assert set(selected["required"]) == set(child["required"])
        for required in selected["required"]:
            (entry,) = [
                entry for entry in selected["entries"] if entry["leaf"] == required
            ]
            assert entry["state"] == 2 and entry["disabled"] is False
        parent_agent = next(row for row in events if row["event"] == "agent")
        assert parent_agent["selectedTree"]["tree"] == selected["tree"]
        assert child["selectedTree"]["tree"] == selected["tree"]
        assert child["preset"] == "standard"
        assert (
            next(row for row in events if row["event"] == "agent")["preset"]
            == "standard"
        )
        web = next(row for row in events if row["event"] == "web")
        assert web["status"] in (200, 404) and "include:hmr" not in web["entries"]
    assert (
        child["options"]["model"] == "parent-current" and child["approval"] == "never"
    )
    assert all(present for _, present in child["services"])
    child_turns = [row for row in events if row.get("kind") == "child"]
    assert len(child_turns) == 6 and PERSONA in child_turns[0]["system"]
    assert "GLOBAL SHADOWED BODY" not in child_turns[0]["system"]
    parent = next(row for row in events if row.get("kind") == "parent")
    assert DESCRIPTION in parent["system"]
    assert (
        next(
            tool
            for tool in parent["tools"]
            if tool["name"] == "ai_dotfiles_agent_reviewer"
        )["description"]
        == DESCRIPTION
    )
    assert "ai_dotfiles_agent_globalonly" in {tool["name"] for tool in parent["tools"]}
    assert all(row["env"] == "explicit" for row in events if row["event"] == "turn")
    results = {
        row["name"]: row["result"]
        for row in events
        if row["event"] == "tool-result" and row.get("origin") == "subagent"
    }
    assert results["mcp__http__ping"]["isError"] is False
    assert results["mcp__stdio__ping"]["isError"] is False
    assert (
        results["write"]["error"]["message"]
        == 'ai-dotfiles permissions deny tool "write"'
    )
    assert results["bash"]["error"]["message"] == 'the user rejected tool "bash"'
    assert any(item["request"]["method"] == "tools/call" for item in requests)
    assert all(
        item["headers"]["X-Local-Sentinel"] == "local-header" for item in requests
    )
    hook_events = [row for row in events if row["event"] == "hook-result"]
    assert hook_events and all(row["data"].get("exitCode") == 0 for row in hook_events)
    hooks = [json.loads(row["data"]["stderrSummary"]) for row in hook_events]
    assert {item["scope"] for item in hooks} == {"global", "project"}
    assert any(item["payload"].get("tool_name") == "read" for item in hooks)
    assert "actual global hook" in json.dumps(child_turns[0]["messages"])
    assert "actual project hook" in json.dumps(child_turns[0]["messages"])
    after = _bytes(profile.parent.parent)
    assert {key: after[key] for key in before} == before
    assert all(key.startswith("ai-dotfiles/") for key in after.keys() - before.keys())


@pytest.mark.parametrize("layer", ["profile", "home", "global"])
def test_native_full_config_replacement_at_each_lower_layer(
    runtime_case: tuple[Path, Path, DshNativeRuntime, dict[str, str]],
    tmp_path: Path,
    layer: str,
) -> None:
    project, profile, runtime, env = runtime_case
    (profile / "config-observer.mjs").write_text(
        "export function apply(ctx,config) { "
        "ctx.provide('nativeConfigEvidence',config); }\n"
    )
    patch = profile / "cordis.patch.yml"
    rows = json.loads(patch.read_text())
    rows[0]["insert"].append(
        {
            "id": "user-config",
            "name": "./config-observer.mjs",
            "config": {"profile": True, "discarded": "profile-only"},
        }
    )
    patch.write_text(json.dumps(rows))
    if layer in {"home", "global"}:
        (profile.parent.parent / "cordis.patch.yml").write_text(
            '[{"id":"user-config","config":{"home":true}}]'
        )
    if layer == "global":
        storage = Path(env["AI_DOTFILES_HOME"])
        domain = storage / "catalog/global-config"
        domain.mkdir()
        (domain / "dsh.fragment.json").write_text(
            '[{"id":"user-config","config":{"global":true}}]'
        )
        (storage / "global.json").write_text(
            '{"targets":["dsh"],"packages":["@global-config"]}'
        )
    before = _bytes(profile.parent.parent)
    result = _run_command(
        [
            os.sys.executable,
            "-m",
            "ai_dotfiles",
            "dsh",
            "launch",
            "proof",
            "acceptance",
            "--json",
        ],
        cwd=project,
        env=env,
        logs=tmp_path / "commands",
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    events = [json.loads(line) for line in Path(env["PROOF"]).read_text().splitlines()]
    expected = (
        {"profile": True, "discarded": "profile-only"}
        if layer == "profile"
        else {layer: True}
    )
    assert events[0]["nativeConfig"] == expected
    after = _bytes(profile.parent.parent)
    assert {key: after[key] for key in before} == before
    assert all(key.startswith("ai-dotfiles/") for key in after.keys() - before.keys())


def test_archives_ship_all_helpers_and_isolated_installed_wheel_runs_real_child(
    runtime_case: tuple[Path, Path, DshNativeRuntime, dict[str, str]], tmp_path: Path
) -> None:
    project, profile, runtime, env = runtime_case
    checkout = Path(__file__).resolve().parents[2]
    poetry = shutil.which("poetry")
    assert poetry is not None, "Required package acceptance needs Poetry build"
    build_env = dict(env)
    for key in ("POETRY_CACHE_DIR", "POETRY_CONFIG_DIR"):
        if key in os.environ:
            build_env[key] = os.environ[key]
    build_env["POETRY_VIRTUALENVS_IN_PROJECT"] = "true"
    archives = tmp_path / "archives"
    logs = tmp_path / "commands"
    built = _run_command(
        [poetry, "build", "--output", str(archives)],
        cwd=checkout,
        env=build_env,
        logs=logs,
    )
    assert built.returncode == 0, built.stdout + built.stderr
    wheel = next(archives.glob("*.whl"))
    sdist = next(archives.glob("*.tar.gz"))
    required = [
        "ai_dotfiles/scaffold/templates/dsh_bridge.mjs",
        "ai_dotfiles/scaffold/templates/dsh_compose.mjs",
        "ai_dotfiles/scaffold/templates/dsh_audit.mjs",
        "ai_dotfiles/core/dsh_launch.py",
    ]
    with zipfile.ZipFile(wheel) as archive, tarfile.open(sdist) as source_archive:
        names = source_archive.getnames()
        for name in required:
            expected = (checkout / "src" / name).read_bytes()
            assert archive.read(name) == expected
            member = next(item for item in names if item.endswith("/src/" + name))
            extracted = source_archive.extractfile(member)
            assert extracted is not None and extracted.read() == expected
    venv = tmp_path / "installed"
    setup = _run_command(
        [os.sys.executable, "-m", "venv", str(venv)], cwd=tmp_path, env=env, logs=logs
    )
    assert setup.returncode == 0, setup.stderr
    python = str(venv / "bin/python")
    dependencies: list[str] = []
    cache = Path(os.environ.get("POETRY_CACHE_DIR", str(tmp_path / "empty-cache")))
    for name in ("click", "tomli_w"):
        candidates = list(
            cache.glob(f"artifacts/**/{name}-{metadata.version(name)}-*.whl")
        )
        if not candidates:
            downloaded = _run_command(
                [
                    python,
                    "-m",
                    "pip",
                    "--isolated",
                    "--cache-dir",
                    str(tmp_path / "pip-cache"),
                    "download",
                    "--no-deps",
                    "--only-binary=:all:",
                    "--dest",
                    str(archives),
                    f"{name}=={metadata.version(name)}",
                ],
                cwd=tmp_path,
                env=env,
                logs=logs,
            )
            assert downloaded.returncode == 0, downloaded.stderr
            candidates = list(archives.glob(f"{name}-*.whl"))
        assert candidates, f"Required isolated installation lacks {name} wheel"
        dependencies.append(str(candidates[0]))
    installed = _run_command(
        [
            python,
            "-m",
            "pip",
            "--isolated",
            "--cache-dir",
            str(tmp_path / "pip-cache"),
            "install",
            "--no-index",
            "--no-deps",
            str(wheel),
            *dependencies,
        ],
        cwd=tmp_path,
        env=env,
        logs=logs,
    )
    assert installed.returncode == 0, installed.stdout + installed.stderr
    identity = _run_command(
        [
            python,
            "-I",
            "-c",
            "import ai_dotfiles, sys; print(ai_dotfiles.__file__); print(sys.path)",
        ],
        cwd=project,
        env=env,
        logs=logs,
    )
    assert identity.returncode == 0, identity.stderr
    assert str(venv) in identity.stdout and str(checkout) not in identity.stdout
    assert "PYTHONPATH" not in env
    helpers = tmp_path / "installed-helpers"
    generated = _run_command(
        [
            python,
            "-I",
            "-c",
            "import json,sys; from pathlib import Path; "
            "from importlib import resources; "
            "from ai_dotfiles.core.dsh_launch import launch_module_text; "
            "from ai_dotfiles.core.dsh_native import resolve_dsh_runtime; "
            "output=Path(sys.argv[3]); output.mkdir(); "
            "names=['dsh_bridge.mjs','dsh_compose.mjs','dsh_audit.mjs']; "
            "package=resources.files('ai_dotfiles.scaffold.templates'); "
            "[(output/name).write_bytes(package.joinpath(name).read_bytes()) "
            "for name in names]; "
            "runtime=resolve_dsh_runtime(Path(sys.argv[1]),node=sys.argv[2]); "
            "(output/'managed_host.mjs').write_text(launch_module_text(runtime)); "
            "print(json.dumps({'helpers':names+['managed_host.mjs']}))",
            str(runtime.package_dir),
            str(runtime.node),
            str(helpers),
        ],
        cwd=project,
        env=env,
        logs=logs,
    )
    assert generated.returncode == 0, generated.stderr
    for helper in sorted(helpers.glob("*.mjs")):
        checked = _run_command(
            [str(runtime.node), "--check", str(helper)], cwd=project, env=env, logs=logs
        )
        assert checked.returncode == 0, checked.stderr
    for helper in (
        profile / "provider.mjs",
        Path(env["AI_DOTFILES_HOME"]) / "catalog/acceptance/mcp.mjs",
    ):
        checked = _run_command(
            [str(runtime.node), "--check", str(helper)], cwd=project, env=env, logs=logs
        )
        assert checked.returncode == 0, checked.stderr
    before = _bytes(profile.parent.parent)
    launched = _run_command(
        [
            str(venv / "bin/ai-dotfiles"),
            "dsh",
            "launch",
            "proof",
            "acceptance",
            "--json",
        ],
        cwd=project,
        env=env,
        logs=logs,
        timeout=45,
    )
    assert launched.returncode == 0, launched.stdout + launched.stderr
    assert "actual parent completed" in launched.stdout
    events = [json.loads(line) for line in Path(env["PROOF"]).read_text().splitlines()]
    assert any(
        row["event"] == "agent" and row.get("origin") == "subagent" for row in events
    )
    assert _bytes(profile.parent.parent) == before


@pytest.mark.parametrize(
    "failure",
    ["runtime", "read_image", "spawn", "optional-import", "optional-apply", "preset"],
)
def test_required_native_failure_never_releases_ready_or_a_turn(
    runtime_case: tuple[Path, Path, DshNativeRuntime, dict[str, str]],
    tmp_path: Path,
    failure: str,
) -> None:
    project, profile, runtime, env = runtime_case
    catalog = Path(env["AI_DOTFILES_HOME"]) / "catalog/acceptance"
    patch_path = profile / "cordis.patch.yml"
    patches = json.loads(patch_path.read_text())
    expected = ""
    if failure == "runtime":
        empty_bin = tmp_path / "empty-bin"
        empty_bin.mkdir()
        env["PATH"] = str(empty_bin)
        expected = "Official dsh executable is missing from PATH"
    elif failure == "read_image":
        source = (profile / "provider.mjs").read_text()
        (profile / "provider.mjs").write_text(
            source.replace(
                "['read','read_image','write','bash']", "['read','write','bash']"
            )
        )
        (catalog / "settings.fragment.json").write_text(
            '{"permissions":{"deny":["Write"],"ask":["Bash","Read"]}}'
        )
        expected = "read_image: required native capability is unavailable"
    elif failure == "spawn":
        patches[0]["insert"] = [
            row
            for row in patches[0]["insert"]
            if row["id"] != "subagent-spawn-in-process"
        ]
        expected = "spawn: required native subagent provider is missing"
    elif failure == "preset":
        patches[0]["insert"].extend(
            [
                {
                    "id": "presets",
                    "name": "@deepseek-ai/dsh-agent-preset-registry",
                    "config": {"default": "chosen"},
                },
                {
                    "id": "chosen",
                    "name": "@deepseek-ai/dsh-agent-preset",
                    "config": {"id": "chosen", "plugins": []},
                },
            ]
        )
        expected = "COMPOSITION_NOT_SELECTED"
    else:
        plugin = catalog / "broken.mjs"
        if failure == "optional-apply":
            plugin.write_text(
                "export function apply() { "
                "throw new Error('managed optional failed'); }\n"
            )
        else:
            plugin.write_text("export {missing} from './absent-dependency.mjs';\n")
        (catalog / "dsh.fragment.json").write_text(
            json.dumps(
                [{"insert": [{"id": "managed-optional", "name": "./broken.mjs"}]}]
            )
        )
        # Native ordinary optional startup reports a warning. Managed startup
        # must treat the identical row as required, in the actual launch host.
        ordinary = tmp_path / "ordinary"
        ordinary.mkdir()
        (ordinary / "node_modules").symlink_to(runtime.package_dir.parent.parent)
        config = ordinary / "config.json"
        config.write_text(
            json.dumps([{"id": "ordinary-optional", "name": plugin.as_uri()}])
        )
        script = ordinary / "probe.mjs"
        script.write_text(
            "import assert from 'node:assert/strict';\n"
            "import {boot,auditStartupEntries} from '@deepseek-ai/dsh-app-boot';\n"
            "const config=new URL('./config.json',import.meta.url).pathname;\n"
            "const ctx=await boot('ordinary-optional',config,"
            "undefined,undefined,import.meta.url);\n"
            "try { const warnings=[]; "
            "await auditStartupEntries(ctx,'ordinary',v=>warnings.push(v));"
            "assert.equal(warnings.length,1); "
            "console.log(JSON.stringify({nativeWarnings:warnings.length}));"
            "} finally { await ctx.fiber.dispose(); }\n"
        )
        ordinary_result = _run_command(
            [str(runtime.node), str(script)],
            cwd=project,
            env=env,
            logs=tmp_path / "commands",
        )
        assert ordinary_result.returncode == 0, ordinary_result.stderr
        assert json.loads(ordinary_result.stdout) == {"nativeWarnings": 1}
        expected = (
            "failed to import"
            if failure == "optional-import"
            else "managed optional failed"
        )
    patch_path.write_text(json.dumps(patches))
    before = _bytes(profile.parent.parent)
    result = _run_command(
        [
            os.sys.executable,
            "-m",
            "ai_dotfiles",
            "dsh",
            "launch",
            "proof",
            "acceptance",
            "--json",
        ],
        cwd=project,
        env=env,
        logs=tmp_path / "commands",
        timeout=45,
    )
    assert result.returncode != 0, result.stdout + result.stderr
    assert expected in result.stderr, result.stdout + result.stderr
    assert "native surface released" not in result.stderr
    assert not Path(
        env["PROOF"]
    ).exists(), "Failure must precede Ready, session, and LLM turn"
    assert _bytes(profile.parent.parent) == before
