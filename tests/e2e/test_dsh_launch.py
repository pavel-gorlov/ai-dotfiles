"""CLI contract and required real RC2 managed-host readiness proofs."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from ai_dotfiles.cli import cli
from ai_dotfiles.core.dsh_install import apply_dsh_install, collect_dsh_elements
from ai_dotfiles.core.dsh_launch import DshLaunchPlan, prepare_dsh_launch
from ai_dotfiles.core.dsh_layout import project_layout
from ai_dotfiles.core.dsh_native import DshNativeRuntime, resolve_dsh_runtime
from ai_dotfiles.core.elements import parse_element
from ai_dotfiles.core.errors import ConfigError
from tests.integration.test_dsh_bridge import (
    bridge_native_runtime as _bridge_native_runtime,
)

bridge_native_runtime = _bridge_native_runtime


def test_help_and_registered_group() -> None:
    result = CliRunner().invoke(cli, ["dsh", "launch", "--help"])
    assert result.exit_code == 0
    for text in (
        "existing official DSH",
        "--profile",
        "--patch",
        "restart",
        "Web",
        "hard isolation",
    ):
        assert text in result.output
    assert "dsh" in CliRunner().invoke(cli, ["--help"]).output


def test_command_forwards_argv_status_and_restart_notice() -> None:
    with patch("ai_dotfiles.commands.dsh.prepare_dsh_launch") as prepare, patch(
        "ai_dotfiles.commands.dsh.execute_dsh_launch", return_value=19
    ) as execute:
        prepare.return_value.diagnostics = ()
        result = CliRunner().invoke(
            cli, ["dsh", "launch", "--profile", "headless", "task; $(no)", "--json"]
        )
    assert result.exit_code == 19
    assert prepare.call_args.args == (
        ("--profile", "headless", "task; $(no)", "--json"),
    )
    assert "Restart after managed updates" in result.output
    execute.assert_called_once()


def test_app_help_is_forwarded_after_native_profile() -> None:
    with patch("ai_dotfiles.commands.dsh.prepare_dsh_launch") as prepare, patch(
        "ai_dotfiles.commands.dsh.execute_dsh_launch", return_value=0
    ):
        prepare.return_value.diagnostics = ()
        result = CliRunner().invoke(
            cli, ["dsh", "launch", "--profile", "web", "--help"]
        )
    assert result.exit_code == 0
    assert prepare.call_args.args[0] == ("--profile", "web", "--help")


def test_core_error_has_no_success_claim() -> None:
    with patch(
        "ai_dotfiles.commands.dsh.prepare_dsh_launch",
        side_effect=ConfigError("native audit refused"),
    ), patch("ai_dotfiles.commands.dsh.execute_dsh_launch") as execute:
        result = CliRunner().invoke(cli, ["dsh", "launch", "web"])
    assert result.exit_code != 0
    assert "native audit refused" in result.output
    assert "released" not in result.output
    execute.assert_not_called()


PROVIDER = r"""
import { LlmAdapter } from '@deepseek-ai/dsh-llm';
import { appendFileSync, readFileSync } from 'node:fs';
export const inject = ['llm'];
export function apply(ctx) {
  class Local extends LlmAdapter {
    resolveModel(provider, model) {
      return Promise.resolve({ provider, id: model, name: model });
    }
    async *stream(options) {
      appendFileSync(process.env.PROOF, JSON.stringify({ event: 'turn',
        argv: ctx.cmdlineArgs.get(), env: process.env.FIXTURE_ENV,
        profileResource: readFileSync(
          new URL('./profile-resource.txt', import.meta.url), 'utf8'),
        messages: options.messages }) + '\n');
      yield { type: 'block-start', index: 0, blockType: 'text' };
      yield { type: 'text-delta', index: 0, text: 'managed local answer' };
      yield { type: 'block-end', index: 0,
        block: { type: 'text', text: 'managed local answer' } };
      yield { type: 'finish', reason: { kind: 'stop' } };
    }
  }
  ctx.llm.registerAdapter(['local'], new Local());
  ctx.appReady.onReady(() => appendFileSync(process.env.PROOF,
    JSON.stringify({ event: 'ready',
      sessions: ctx.get('sessions').list().length }) + '\n'));
  ctx.on('agent/created', ({agent}) => appendFileSync(process.env.PROOF,
    JSON.stringify({event:'agent',
      preset: ctx.get('agentPresets')?.composedPreset(agent.ctx)})+'\n'));
}
"""

WEB_PROOF = r"""
import {appendFileSync} from 'node:fs';
export const inject = ['webServer', 'webRuntime', 'sessionController'];
export function apply(ctx) {
  setTimeout(async () => {
    try {
      await ctx.get('loader').await();
      const server = ctx.webServer;
      const url = ctx.get('connection').authenticatedUrl(
        `http://127.0.0.1:${server.port}/`);
      const exchange = await fetch(url, {redirect:'manual'});
      const cookie = exchange.headers.get('set-cookie').split(';')[0];
      const response = await fetch(`http://127.0.0.1:${server.port}/`,
        {headers:{cookie}});
      await response.arrayBuffer();
      appendFileSync(process.env.PROOF, JSON.stringify({event: 'web',
        status: response.status,
        entries: [...ctx.get('loader').entries()].map(entry => entry.id)})+'\n');
      const controller = ctx.sessionController;
      const created = await controller.create({cwd:process.cwd()});
      await controller.prompt({sessionId:created.sessionId,
        requestId:'isolated-web-proof',mode:'queue',
        content:[{type:'text',text:'Managed native Web task'}]},
        new AbortController().signal);
      const resolved = await controller.resolveAgent(created.sessionId);
      if (resolved.error) throw new Error(resolved.error.message);
      await resolved.agent.whenIdle();
      await ctx.get('sessions').flush(resolved.agent.session);
      ctx.get('appExit')(23);
    } catch (error) {
      process.stderr.write(`Native Web proof failed: ${error.message}\n`);
      ctx.get('appExit')(1);
    }
  }, 0);
}
"""


@pytest.fixture
def managed_fixture(
    tmp_path: Path, bridge_native_runtime: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, DshNativeRuntime, dict[str, str]]:
    project = tmp_path / "project"
    project.mkdir()
    (project / ".git").mkdir()
    (project / "ai-dotfiles.json").write_text('{"targets":["dsh"],"packages":[]}')
    storage = tmp_path / "storage"
    storage.mkdir()
    (storage / "catalog").mkdir()
    home = tmp_path / "home"
    home.mkdir()
    native_home = tmp_path / "native-home"
    directory = native_home / "profiles/proof"
    directory.mkdir(parents=True)
    (directory / "node_modules").symlink_to(bridge_native_runtime / "node_modules")
    (directory / "package.json").write_text('{"dsh":{"profile":{"bundles":[]}}}')
    (directory / "cordis.yml").write_text(
        "User root sentinel. Must never be parsed or rewritten.\n"
    )
    (directory / "provider.mjs").write_text(PROVIDER)
    (directory / "profile-resource.txt").write_text("profile relative resource")
    rows = [
        {"id": name, "name": f"@deepseek-ai/dsh-{name}"}
        for name in (
            "llm",
            "session",
            "session-projection",
            "system-prompt",
            "tools",
            "agent",
            "agent-loop",
        )
    ]
    rows.extend(
        [
            {"id": "local-provider", "name": "./provider.mjs"},
            {
                "id": "default-model",
                "name": "@deepseek-ai/dsh-agent-default-model",
                "config": {"provider": "local", "model": "parent-current"},
            },
            {"id": "headless-startup", "name": "@deepseek-ai/dsh-headless/startup"},
            {
                "id": "headless-runner",
                "name": "@deepseek-ai/dsh-headless",
                "inject": ["headlessStartup"],
                "config": {
                    "task": {"__jsExpr": "ctx.headlessStartup.task"},
                    "json": {"__jsExpr": "ctx.headlessStartup.json"},
                },
            },
        ]
    )
    sub = directory / "included"
    sub.mkdir()
    (sub / "resource.txt").write_text("nested relative include resource")
    (sub / "relative.mjs").write_text(
        "import { readFileSync, appendFileSync } from 'node:fs';\n"
        "export function apply(ctx) {\n"
        "  ctx.appReady.onReady(() => appendFileSync(process.env.PROOF,\n"
        "    JSON.stringify({event:'include', value:readFileSync(\n"
        "      new URL('./resource.txt',import.meta.url),'utf8')})+'\\n'));\n"
        "}\n"
    )
    (sub / "rows.json").write_text(
        json.dumps([{"id": "nested-relative", "name": "./relative.mjs"}])
    )
    rows.append(
        {
            "id": "user-relative-include",
            "name": "cordis:include",
            "config": {"path": "./included/rows.json"},
        }
    )
    (directory / "cordis.patch.yml").write_text(json.dumps([{"insert": rows}]))
    (native_home / "cordis.patch.yml").write_text("[]\n")
    (native_home / "sentinel").write_text("user home sentinel")
    env = {
        "PATH": str(bridge_native_runtime / "node_modules/.bin")
        + os.pathsep
        + os.environ["PATH"],
        "HOME": str(home),
        "DSH_HOME": str(native_home),
        "AI_DOTFILES_HOME": str(storage),
        "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
        "PROOF": str(tmp_path / "proof.jsonl"),
        "DSH_TELEMETRY_DISABLED": "1",
        "FIXTURE_ENV": "explicit",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    runtime = resolve_dsh_runtime(
        bridge_native_runtime / "node_modules/@deepseek-ai/dsh"
    )
    return project, directory, runtime, env


def _bytes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink() and "node_modules" not in path.parts
    }


def _run(
    plan: DshLaunchPlan,
    env: dict[str, str],
    tmp_path: Path,
    app_args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    # Execute the actual production boundary in an isolated child so inherited
    # native stdout/stderr are captured without changing production stdio.
    return subprocess.run(
        [
            os.sys.executable,
            "-m",
            "ai_dotfiles",
            "dsh",
            "launch",
            *(["--strict"] if plan.strict else []),
            "proof",
            *(app_args if app_args is not None else ["task; $(touch no)", "--json"]),
        ],
        cwd=plan.cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


@pytest.mark.integration
def test_actual_same_host_readiness_native_headless_relative_bases_and_exit(
    managed_fixture: tuple[Path, Path, DshNativeRuntime, dict[str, str]], tmp_path: Path
) -> None:
    project, directory, runtime, env = managed_fixture
    before = _bytes(directory.parent.parent)
    plan = prepare_dsh_launch(
        ["proof", "task; $(touch no)", "--json"],
        cwd=project,
        process_env=env,
        runtime=runtime,
    )
    assert _bytes(directory.parent.parent) == before
    result = _run(plan, env, tmp_path)
    assert result.returncode == 0, result.stderr
    evidence = [
        json.loads(line) for line in Path(env["PROOF"]).read_text().splitlines()
    ]
    assert [item["event"] for item in evidence] == ["ready", "include", "agent", "turn"]
    assert evidence[1]["value"] == "nested relative include resource"
    assert evidence[-1]["profileResource"] == "profile relative resource"
    assert evidence[-1]["argv"] == ["task; $(touch no)", "--json"]
    assert evidence[-1]["env"] == "explicit"
    assert "managed local answer" in result.stdout
    assert _bytes(directory.parent.parent) == before
    assert not (project / "no").exists()


@pytest.mark.integration
def test_failed_same_host_required_audit_releases_no_ready_or_provider_turn(
    managed_fixture: tuple[Path, Path, DshNativeRuntime, dict[str, str]], tmp_path: Path
) -> None:
    project, directory, runtime, env = managed_fixture
    # A native managed domain row loads but cannot provide its required runtime.
    domain = Path(env["AI_DOTFILES_HOME"]) / "catalog/failure"
    domain.mkdir(parents=True)
    (domain / "dsh.fragment.json").write_text(
        json.dumps(
            [{"insert": [{"id": "required-broken", "name": "./missing-plugin.mjs"}]}]
        )
    )
    (project / "ai-dotfiles.json").write_text(
        '{"targets":["dsh"],"packages":["@failure"]}'
    )
    before = _bytes(directory.parent.parent)
    plan = prepare_dsh_launch(
        ["proof", "task"], cwd=project, process_env=env, runtime=runtime
    )
    result = _run(plan, env, tmp_path)
    assert result.returncode != 0
    assert "required-broken" in result.stderr
    assert "native surface released" not in result.stderr
    assert not Path(env["PROOF"]).exists()
    assert _bytes(directory.parent.parent) == before


@pytest.mark.integration
def test_local_registry_is_refused_before_activation(
    managed_fixture: tuple[Path, Path, DshNativeRuntime, dict[str, str]],
) -> None:
    project, _directory, runtime, env = managed_fixture
    layout = project_layout(project)
    layout.owned_dir.mkdir(parents=True)
    layout.local_registry_path.write_text('{"rule_blocks":{}}')
    with pytest.raises(ConfigError, match="Local DSH registry.*integration"):
        prepare_dsh_launch(
            ["proof", "task"], cwd=project, process_env=env, runtime=runtime
        )


@pytest.mark.integration
def test_retired_native_linked_skill_cannot_survive_omission(
    managed_fixture: tuple[Path, Path, DshNativeRuntime, dict[str, str]],
) -> None:
    project, _directory, runtime, env = managed_fixture
    catalog = Path(env["AI_DOTFILES_HOME"]) / "catalog"
    skill = catalog / "skills/retired"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: retired\ndescription: Retired native skill\n---\nbody\n"
    )
    apply_dsh_install(
        collect_dsh_elements(
            [parse_element("skill:retired")], project_layout(project), catalog
        )
    )
    with pytest.raises(ConfigError, match="Stale native-discovered.*skills/retired"):
        prepare_dsh_launch(
            ["proof", "task"], cwd=project, process_env=env, runtime=runtime
        )


@pytest.mark.integration
def test_native_leading_app_flag_and_help_have_exact_process_argv_and_exit(
    managed_fixture: tuple[Path, Path, DshNativeRuntime, dict[str, str]], tmp_path: Path
) -> None:
    project, _directory, runtime, env = managed_fixture
    plan = prepare_dsh_launch(
        ["proof", "--json", "task"], cwd=project, process_env=env, runtime=runtime
    )
    result = _run(plan, env, tmp_path, ["--json", "task"])
    assert result.returncode == 0, result.stderr
    evidence = [
        json.loads(line) for line in Path(env["PROOF"]).read_text().splitlines()
    ]
    assert evidence[-1]["argv"] == ["--json", "task"]
    Path(env["PROOF"]).unlink()
    help_result = _run(plan, env, tmp_path, ["--help"])
    assert help_result.returncode == 0, help_result.stderr
    assert "Answer one task" in help_result.stdout
    assert not Path(env["PROOF"]).exists()


@pytest.mark.integration
def test_disabled_global_target_still_refuses_retired_ambient_native_skill(
    managed_fixture: tuple[Path, Path, DshNativeRuntime, dict[str, str]],
) -> None:
    from ai_dotfiles.core.dsh_layout import global_layout

    project, _directory, runtime, env = managed_fixture
    catalog = Path(env["AI_DOTFILES_HOME"]) / "catalog"
    skill = catalog / "skills/old-global"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: old-global\ndescription: Old global native skill\n---\nbody\n"
    )
    layout = global_layout()
    apply_dsh_install(
        collect_dsh_elements([parse_element("skill:old-global")], layout, catalog)
    )
    before = _bytes(layout.dsh_dir)
    with pytest.raises(ConfigError, match="Stale native-discovered.*skills/old-global"):
        prepare_dsh_launch(
            ["proof", "task"], cwd=project, process_env=env, runtime=runtime
        )
    assert _bytes(layout.dsh_dir) == before


@pytest.mark.integration
@pytest.mark.parametrize(
    "provider_mode", ["active", "disabled", "custom-candidates", "nested"]
)
def test_actual_shared_codex_scoped_instruction_gap_preserves_bytes_and_checks_provider(
    managed_fixture: tuple[Path, Path, DshNativeRuntime, dict[str, str]],
    tmp_path: Path,
    provider_mode: str,
) -> None:
    from ai_dotfiles.core.agents_md import upsert_rule_block

    project, directory, runtime, env = managed_fixture
    catalog = Path(env["AI_DOTFILES_HOME"]) / "catalog"
    (catalog / "rules").mkdir()
    rule = catalog / "rules/scoped.md"
    paths = '["nested"]' if provider_mode == "nested" else '["**/*.py"]'
    always_on = "" if provider_mode == "nested" else "always_on: true\n"
    rule.write_text(f"---\npaths: {paths}\n{always_on}---\nCODEX_SCOPED_SENTINEL\n")
    (project / "ai-dotfiles.json").write_text(
        '{"targets":["codex","dsh"],"packages":["rule:scoped"]}'
    )
    block = (
        project / "nested/AGENTS.md"
        if provider_mode == "nested"
        else project / "AGENTS.md"
    )
    upsert_rule_block(block, "scoped", "CODEX_SCOPED_SENTINEL\n")
    body_before = block.read_bytes()
    patch_file = directory / "cordis.patch.yml"
    patches = json.loads(patch_file.read_text())
    provider = {
        "id": "agent-instructions",
        "name": "@deepseek-ai/dsh-agent-instructions",
        "config": {"maxBytes": 65536},
    }
    if provider_mode == "disabled":
        provider["disabled"] = True
    elif provider_mode == "custom-candidates":
        provider["config"]["instructionFileCandidates"] = ["SAFE.md"]
    patches[0]["insert"].append(provider)
    patch_file.write_text(json.dumps(patches))
    # The public native loader demonstrates why the unchanged root block is unsafe.
    if provider_mode == "active":
        probe = subprocess.run(
            [
                str(runtime.node),
                "--input-type=module",
                "-e",
                "const m=await import("
                + json.dumps(
                    (
                        runtime.package_dir.parent
                        / "dsh-agent-instructions/lib/index.js"
                    ).as_uri()
                )
                + "); const r=await m.loadBaselineInstructions({"
                "cwd:process.argv[1],dshHome:process.argv[2],maxBytes:65536}); "
                "process.stdout.write(r.text);",
                "--",
                str(project),
                env["DSH_HOME"],
            ],
            cwd=project,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert probe.returncode == 0, probe.stderr
        assert "CODEX_SCOPED_SENTINEL" in probe.stdout
    plan = prepare_dsh_launch(
        ["proof", "task"], cwd=project, process_env=env, runtime=runtime
    )
    result = _run(plan, env, tmp_path)
    if provider_mode in ("active", "nested"):
        assert result.returncode != 0
        assert str(rule) in result.stderr
        assert "paths: native instruction provider" in result.stderr
        assert "unconditionally" in result.stderr
        assert not Path(env["PROOF"]).exists()
    else:
        assert result.returncode == 0, result.stderr
    assert block.read_bytes() == body_before


@pytest.mark.integration
@pytest.mark.parametrize("failure", ["none", "required-row", "selected-provider"])
def test_actual_stock_standard_preset_has_scoped_audit_and_native_web_release(
    managed_fixture: tuple[Path, Path, DshNativeRuntime, dict[str, str]],
    tmp_path: Path,
    failure: str,
) -> None:
    project, directory, runtime, env = managed_fixture
    (directory / "package.json").write_text(
        json.dumps(
            {
                "dsh": {
                    "profile": {
                        "bundles": ["@deepseek-ai/dsh-base", "@deepseek-ai/dsh-web-app"]
                    }
                }
            }
        )
    )
    original = json.loads((directory / "cordis.patch.yml").read_text())[0]["insert"]
    retained = [
        row
        for row in original
        if row["id"]
        in (
            "local-provider",
            "user-relative-include",
        )
    ]
    patches = [{"id": name, "disabled": True} for name in ("session-title-llm",)]
    patches.append(
        {
            "id": "agent-default-model",
            "config": {"provider": "local", "model": "parent-current"},
        }
    )
    patches.append({"insert": retained})
    (directory / "web-proof.mjs").write_text(WEB_PROOF)
    patches.append({"insert": [{"id": "native-web-proof", "name": "./web-proof.mjs"}]})
    patches.extend(
        [
            {
                "id": "storage-json",
                "config": {"root": str(tmp_path / "runtime-state/storages")},
            },
            {
                "id": "session-persistence-jsonl",
                "config": {"root": str(tmp_path / "runtime-state/sessions")},
            },
            {
                "id": "credentials",
                "config": {"path": str(tmp_path / "runtime-state/credentials.yaml")},
            },
        ]
    )
    (directory / "cordis.patch.yml").write_text(json.dumps(patches))
    if failure == "required-row":
        domain = Path(env["AI_DOTFILES_HOME"]) / "catalog/failure"
        domain.mkdir()
        (domain / "dsh.fragment.json").write_text(
            json.dumps([{"insert": [{"id": "broken-scoped", "name": "./absent.mjs"}]}])
        )
        (project / "ai-dotfiles.json").write_text(
            '{"targets":["dsh"],"packages":["@failure"]}'
        )
    if failure == "selected-provider":
        original_plan = prepare_dsh_launch(
            ["proof", "--no-open", "--port", "0"],
            cwd=project,
            process_env=env,
            runtime=runtime,
        )
        stock = next(
            row
            for row in original_plan.request["inspected"]["entries"]
            if row.get("id") == "preset-standard"
        )
        patches.append(
            {
                "id": "preset-standard",
                "config": {
                    **stock["config"],
                    "plugins": [
                        *(
                            row
                            for row in stock["config"]["plugins"]
                            if not row["id"].startswith("ai-dotfiles")
                        ),
                        {
                            "id": "selected-model",
                            "name": "@deepseek-ai/dsh-agent-default-model",
                            "isolate": {"agentDefaultModel": True},
                            "config": {
                                "provider": "missing-selected",
                                "model": "selected-route",
                            },
                        },
                    ],
                },
            }
        )
        (directory / "cordis.patch.yml").write_text(json.dumps(patches))
    before = _bytes(directory.parent.parent)
    plan = prepare_dsh_launch(
        ["proof", "task"], cwd=project, process_env=env, runtime=runtime
    )
    assert plan.request["inspected"]["selection"]["id"] == "standard"
    result = _run(plan, env, tmp_path, ["--no-open", "--port", "0"])
    if failure != "none":
        assert result.returncode != 0
        assert (
            "broken-scoped" if failure == "required-row" else "missing-selected"
        ) in result.stderr
        assert "native surface released" not in result.stderr
        assert "dsh web:" not in result.stdout
        assert not Path(env["PROOF"]).exists()
    else:
        assert result.returncode == 23, result.stderr
        evidence = [
            json.loads(line) for line in Path(env["PROOF"]).read_text().splitlines()
        ]
        assert evidence[0] == {"event": "ready", "sessions": 0}
        web = next(item for item in evidence if item["event"] == "web")
        assert web["status"] in (200, 404)
        assert "include:ai-dotfiles-host" in web["entries"]
        assert "include:hmr" not in web["entries"]
        assert (
            next(item for item in evidence if item["event"] == "agent")["preset"]
            == "standard"
        )
        assert evidence[-1]["event"] == "turn"
        assert "Managed DSH audit passed; native surface released" in result.stderr
    assert _bytes(directory.parent.parent) == before


@pytest.mark.integration
def test_native_headless_preset_mismatch_refuses_before_readiness_or_turn(
    managed_fixture: tuple[Path, Path, DshNativeRuntime, dict[str, str]], tmp_path: Path
) -> None:
    project, directory, runtime, env = managed_fixture
    patch_path = directory / "cordis.patch.yml"
    patches = json.loads(patch_path.read_text())
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
    patch_path.write_text(json.dumps(patches))
    before = _bytes(directory.parent.parent)
    plan = prepare_dsh_launch(
        ["proof", "task"], cwd=project, process_env=env, runtime=runtime
    )
    result = _run(plan, env, tmp_path)
    assert result.returncode != 0
    assert "COMPOSITION_NOT_SELECTED" in result.stderr
    assert "headless runs global Agents" in result.stderr
    assert not Path(env["PROOF"]).exists()
    assert _bytes(directory.parent.parent) == before


@pytest.mark.integration
@pytest.mark.parametrize("filesystem", [True, False])
def test_native_deferred_skill_retry_and_required_filesystem_provider(
    managed_fixture: tuple[Path, Path, DshNativeRuntime, dict[str, str]],
    tmp_path: Path,
    filesystem: bool,
) -> None:
    project, directory, runtime, env = managed_fixture
    skill = Path(env["AI_DOTFILES_HOME"]) / "catalog/skills/deferred"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: deferred\ndescription: |-\n  Valid native YAML\n"
        "  with multiline routing\n---\nSkill body\n"
    )
    (project / "ai-dotfiles.json").write_text(
        '{"targets":["dsh"],"packages":["skill:deferred"]}'
    )
    patch_path = directory / "cordis.patch.yml"
    patches = json.loads(patch_path.read_text())
    patches[0]["insert"].append({"id": "skills", "name": "@deepseek-ai/dsh-skill"})
    if filesystem:
        patches[0]["insert"].append(
            {
                "id": "skill-filesystem",
                "name": "@deepseek-ai/dsh-skill-filesystem",
                "config": {"watch": False},
            }
        )
    patch_path.write_text(json.dumps(patches))
    plan = prepare_dsh_launch(
        ["proof", "task"], cwd=project, process_env=env, runtime=runtime
    )
    assert plan.installs[-1].skills[0].status == "READY"
    assert not any(item.field == "frontmatter" for item in plan.diagnostics)
    result = _run(plan, env, tmp_path)
    if filesystem:
        assert result.returncode == 0, result.stderr
        assert Path(env["PROOF"]).exists()
    else:
        assert result.returncode != 0
        assert "Missing active native filesystem skill provider" in result.stderr
        assert not Path(env["PROOF"]).exists()


@pytest.mark.integration
def test_global_project_original_environment_precedence_reaches_native_process(
    managed_fixture: tuple[Path, Path, DshNativeRuntime, dict[str, str]], tmp_path: Path
) -> None:
    project, _directory, runtime, env = managed_fixture
    original_global = Path(env["AI_DOTFILES_HOME"]) / "global/settings.json"
    original_global.parent.mkdir()
    original_global.write_text(
        '{"env":{"FIXTURE_ENV":"global","GLOBAL_ONLY":"global"}}'
    )
    local = project / ".claude/settings.local.json"
    local.parent.mkdir()
    local.write_text('{"env":{"FIXTURE_ENV":"project","PROJECT_ONLY":"project"}}')
    # A merged destination is excluded when its existing ownership ledger exists.
    merged = local.parent / "settings.json"
    merged.write_text('{"env":{"MERGED_DESTINATION":"must-not-activate"}}')
    (local.parent / ".ai-dotfiles-settings-ownership.json").write_text("{}")
    plan = prepare_dsh_launch(
        ["proof", "task"], cwd=project, process_env=env, runtime=runtime
    )
    assert plan.config.environment == {
        "FIXTURE_ENV": "project",
        "GLOBAL_ONLY": "global",
        "PROJECT_ONLY": "project",
    }
    before = [original_global.read_bytes(), local.read_bytes(), merged.read_bytes()]
    result = _run(plan, env, tmp_path)
    assert result.returncode == 0, result.stderr
    evidence = [
        json.loads(line) for line in Path(env["PROOF"]).read_text().splitlines()
    ]
    assert evidence[-1]["env"] == "explicit"
    assert [
        original_global.read_bytes(),
        local.read_bytes(),
        merged.read_bytes(),
    ] == before


@pytest.mark.integration
def test_global_project_hooks_have_one_current_layout_contribution_and_raw_resources(
    managed_fixture: tuple[Path, Path, DshNativeRuntime, dict[str, str]],
) -> None:
    project, _directory, runtime, env = managed_fixture
    storage = Path(env["AI_DOTFILES_HOME"])
    for scope in ("global", "project"):
        domain = storage / "catalog" / scope
        (domain / "hooks").mkdir(parents=True)
        (domain / "hooks/raw.sh").write_text(f"# raw {scope}\nexit 0\n")
        (domain / "settings.fragment.json").write_text(
            json.dumps(
                {
                    "hooks": {
                        "UserPromptSubmit": [
                            {
                                "hooks": [
                                    {"type": "command", "command": "bash hooks/raw.sh"}
                                ]
                            }
                        ]
                    }
                }
            )
        )
    (storage / "global.json").write_text('{"targets":["dsh"],"packages":["@global"]}')
    (project / "ai-dotfiles.json").write_text(
        '{"targets":["dsh"],"packages":["@project"]}'
    )
    plan = prepare_dsh_launch(
        ["proof", "task"], cwd=project, process_env=env, runtime=runtime
    )
    hooks = [item for item in plan.config.contributions if item.name == "hooks"]
    assert len(hooks) == 1
    assert [item.source.parent.name for item in hooks[0].provenance] == [
        "global",
        "project",
    ]
    assert len(hooks[0].rows) == 1
    current = plan.installs[-1]
    assert current.layout == project_layout(project)
    raw = [
        output
        for output in current.outputs
        if output.source is not None
        and output.source.name in ("global", "project")
        and output.path.is_relative_to(current.layout.resources_dir)
    ]
    assert len(raw) == 2
    assert all(
        output.path.is_relative_to(current.layout.resources_dir) for output in raw
    )
    for install in plan.installs:
        apply_dsh_install(install)
    assert {(output.path / "hooks/raw.sh").read_bytes() for output in raw} == {
        b"# raw global\nexit 0\n",
        b"# raw project\nexit 0\n",
    }


@pytest.mark.integration
def test_required_managed_official_hmr_has_precise_restart_incompatibility(
    managed_fixture: tuple[Path, Path, DshNativeRuntime, dict[str, str]], tmp_path: Path
) -> None:
    project, directory, runtime, env = managed_fixture
    domain = Path(env["AI_DOTFILES_HOME"]) / "catalog/live-reload"
    domain.mkdir()
    (domain / "dsh.fragment.json").write_text(
        json.dumps(
            [
                {
                    "insert": [
                        {
                            "id": "managed-hmr",
                            "name": "@deepseek-ai/dsh-hmr",
                            "config": {"root": []},
                        }
                    ]
                }
            ]
        )
    )
    (project / "ai-dotfiles.json").write_text(
        '{"targets":["dsh"],"packages":["@live-reload"]}'
    )
    before = _bytes(directory.parent.parent)
    plan = prepare_dsh_launch(
        ["proof", "task"], cwd=project, process_env=env, runtime=runtime
    )
    result = _run(plan, env, tmp_path)
    assert result.returncode != 0
    assert "Required managed HMR row" in result.stderr
    assert "immutable composition" in result.stderr
    assert "DISABLED_ROW" not in result.stderr
    assert not Path(env["PROOF"]).exists()
    assert _bytes(directory.parent.parent) == before
