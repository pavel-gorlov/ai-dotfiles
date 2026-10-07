"""Native managed Web settings, with isolated profiles and real HTTP RPC."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ai_dotfiles.core.dsh_launch import prepare_dsh_launch
from ai_dotfiles.core.dsh_native import DshNativeRuntime
from tests.e2e.test_dsh_launch import _run, managed_fixture

__all__ = ["managed_fixture"]
pytestmark = pytest.mark.integration

SETTINGS_PROOF = r"""
import assert from 'node:assert/strict';
import { appendFileSync, readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
export const inject = ['settingsController', 'webServer', 'connection',
  'directoryPicker'];
export function apply(ctx) {
  ctx.appReady.onReady(() => setTimeout(async () => {
    try {
      await ctx.loader.await();
      const base = `http://127.0.0.1:${ctx.webServer.port}/`;
      const exchange = await fetch(ctx.connection.authenticatedUrl(base), {
        redirect: 'manual', signal: AbortSignal.timeout(10000) });
      const cookie = exchange.headers.get('set-cookie')?.split(';')[0];
      assert.ok(cookie);
      let counter = 0;
      const rpc = async (method, args) => {
        const rpcId = `native-settings-${++counter}`;
        const response = await fetch(`${base}api/settings/${method}`, {
          method: 'POST', headers: { cookie, 'content-type': 'application/json' },
          body: JSON.stringify({ type: 'client-request', rpcId,
            method: `settings/${method}`, payload: { args } }),
          signal: AbortSignal.timeout(10000) });
        assert.equal(response.status, 200);
        const envelope = await response.json();
        assert.equal(envelope.rpcId, rpcId);
        return envelope.result;
      };
      const bytes = () => readFileSync(ctx.profileContext.patchPath, 'utf8');
      const managed = () => createHash('sha256').update(JSON.stringify(
        [...ctx.loader.entries()].filter(row => row.options.id === 'preset-standard'
          || row.options.id.startsWith('ai-dotfiles')).map(row => row.options)))
          .digest('hex');
      const digest = managed();
      const describe = await rpc('describe', {});
      assert.equal(describe.ok, true);
      const find = (view, ns) => view.value.namespaces.find(row => row.ns === ns);
      const welcome = find(describe, 'ui-settings-general');
      assert.ok(welcome);
      const entries = [...ctx.loader.entries()];
      // The isolated fixture has no display or SSH markers. RC2 therefore
      // chooses native on darwin/win32 and browse on headless Linux.
      assert.equal(ctx.webServer.host, '127.0.0.1');
      for (const key of ['DISPLAY', 'WAYLAND_DISPLAY', 'SSH_CONNECTION', 'SSH_TTY'])
        assert.equal(process.env[key], undefined, `isolated fixture ${key}`);
      const pickerBackend = ['darwin', 'win32'].includes(process.platform)
        ? 'native' : 'browse';
      const opposite = pickerBackend === 'native' ? 'browse' : 'native';
      for (const suffix of [`dsh-host-directory-picker-${pickerBackend}`,
        `dsh-client-ui-directory-picker-${pickerBackend}`]) {
        const matches = entries.filter(row =>
          row.options.name === `@deepseek-ai/${suffix}`);
        assert.equal(matches.length, 1, `one directory picker ${suffix}`);
        assert.equal(matches[0].fiber?.state, 2,
          `directory picker ${suffix} mounted`);
      }
      for (const suffix of [`dsh-host-directory-picker-${opposite}`,
        `dsh-client-ui-directory-picker-${opposite}`])
        assert.ok(!entries.some(row => row.options.name === `@deepseek-ai/${suffix}`));
      const capability = ctx.directoryPicker.capability();
      assert.equal(capability.kind, pickerBackend);
      assert.equal(capability, ctx.directoryPicker.capability());
      if (pickerBackend === 'browse') {
        const listing = await capability.list(process.cwd());
        assert.equal(listing.path, process.cwd());
        assert.ok(listing.entries.some(row => row.name === 'picker-child'
          && row.path === `${process.cwd()}/picker-child`));
      } else assert.equal(typeof capability.pick, 'function');
      if (process.env.SETTINGS_PHASE === 'restart') {
        assert.equal(welcome.value.welcomeNoticeVersion, '2026-09-28.1');
        assert.equal(find(describe, 'fixture-preferences').secrets[0].set, true);
      } else if (process.env.SETTINGS_PHASE === 'duplicate') {
        assert.equal(find(describe, 'fixture-preferences'), undefined);
        const before = bytes();
        const refused = await rpc('mutate', { ns: 'fixture-preferences',
          ops: [{ op: 'set', path: ['live'], value: 'refused' }] });
        assert.equal(refused.ok, false);
        assert.equal(bytes(), before);
      } else if (process.env.SETTINGS_PHASE === 'external') {
        appendFileSync(ctx.profileContext.patchPath,
          '\n- id: fixture-preferences\n  config: { ordinary: externally-changed }\n');
        const before = bytes();
        const refused = await rpc('mutate', { ns: 'fixture-preferences',
          ops: [{ op: 'set', path: ['live'], value: 'refused' }] });
        assert.equal(refused.ok, false);
        assert.equal(refused.error.code, 'settings/rejected');
        assert.ok(refused.error.message.includes('composition changed'));
        assert.equal(bytes(), before);
      } else if (process.env.SETTINGS_PHASE === 'override') {
        const before = bytes();
        const refused = await rpc('mutate', { ns: 'fixture-preferences',
          ops: [{ op: 'set', path: ['live'], value: 'refused' }] });
        assert.equal(refused.ok, false);
        assert.equal(refused.error.code, 'settings/rejected');
        assert.equal(bytes(), before);
      } else {
        const changed = await rpc('mutate', { ns: welcome.ns,
          expectedRevision: welcome.revision,
          ops: [{ op: 'set', path: ['welcomeNoticeVersion'],
            value: '2026-09-28.1' }] });
        assert.equal(changed.ok, true, JSON.stringify(changed.error));
        assert.equal(changed.value.value.welcomeNoticeVersion, '2026-09-28.1');
        const refreshed = await rpc('describe', {});
        assert.equal(find(refreshed, welcome.ns).value.welcomeNoticeVersion,
          '2026-09-28.1');
        const before = bytes();
        for (const [path, value, revision, code] of [
          [['welcomeNoticeVersion'], 'stale', welcome.revision, 'settings/conflict'],
          [['welcomeNoticeVersion'], 42, changed.value.revision, 'settings/rejected'],
          [['ordinary'], 'forbidden', changed.value.revision, 'settings/rejected'],
        ]) {
          const refused = await rpc('mutate', { ns: welcome.ns,
            expectedRevision: revision, ops: [{ op: 'set', path, value }] });
          assert.equal(refused.ok, false);
          assert.equal(refused.error.code, code);
          assert.equal(bytes(), before);
        }
        const preference = find(refreshed, 'fixture-preferences');
        const secret = await rpc('mutate', { ns: preference.ns,
          expectedRevision: preference.revision,
          ops: [{ op: 'set', path: ['secret'], value: 'isolated-secret' },
            { op: 'set', path: ['live'], value: 'changed' }] });
        assert.equal(secret.ok, true, JSON.stringify(secret.error));
        assert.equal(secret.value.value.secret, undefined);
        assert.equal(secret.value.secrets[0].set, true);
        assert.ok(!JSON.stringify(secret).includes('isolated-secret'));
        const replace = await rpc('mutate', { ns: preference.ns,
          expectedRevision: secret.value.revision,
          ops: [{ op: 'set', path: ['live'], value: 'second' }] });
        assert.equal(replace.ok, true, JSON.stringify(replace.error));
        assert.ok(bytes().includes('ordinary: keep # ordinary comment'));
        assert.ok(bytes().includes('!!js'));
        assert.ok(bytes().includes('# expression comment'));
        const entry = entries.find(row => row.options.id === preference.ns);
        assert.equal(entry.fiber.config.ordinary, 'keep');
        assert.equal(entry.fiber.config.secret.get(), 'isolated-secret');
        // A failing public Entry.update seam must roll disk bytes back. This
        // failure injection belongs to the test plugin, never production code.
        const saved = bytes();
        const fiber = entry.fiber;
        const update = entry.update;
        let first = true;
        entry.update = async function(...args) {
          if (first) { first = false; throw new Error('injected apply failure'); }
          return update.apply(this, args);
        };
        const rollback = await rpc('mutate', { ns: preference.ns,
          ops: [{ op: 'set', path: ['live'], value: 'rolled-back' }] });
        entry.update = update;
        assert.equal(rollback.ok, false);
        assert.ok(rollback.error.message.includes('injected apply failure'));
        assert.equal(bytes(), saved);
        assert.equal(entry.fiber, fiber);
        assert.equal(entry.fiber.config.live.get(), 'second');
        const denied = await rpc('mutate', { ns: 'ai-dotfiles-audit',
          ops: [{ op: 'set', path: ['requiredIds'], value: [] }] });
        assert.equal(denied.ok, false);
      }
      assert.equal(managed(), digest);
      writeFileSync(process.env.SETTINGS_PROOF, JSON.stringify({
        phase: process.env.SETTINGS_PHASE, namespaces: describe.value.namespaces.length,
        pickerBackend, pickerMounted: true, managedUnchanged: true }), { mode: 0o600 });
      ctx.appExit(23);
    } catch (error) {
      process.stderr.write(`Settings HTTP proof failed: ${error.stack}\n`);
      ctx.appExit(1);
    }
  }, 0));
}
"""


@pytest.fixture
def managed_web(
    managed_fixture: tuple[Path, Path, DshNativeRuntime, dict[str, str]], tmp_path: Path
) -> tuple[Path, Path, DshNativeRuntime, dict[str, str]]:
    project, directory, runtime, env = managed_fixture
    (project / "picker-child").mkdir()
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
    (directory / "settings-proof.mjs").write_text(SETTINGS_PROOF)
    (directory / "preferences.mjs").write_text(
        "import z from '@deepseek-ai/schemastery';\n"
        "export const Config = z.object({ ordinary: z.string(), "
        "live: z.string().volatile(), "
        "secret: z.string().role('secret').volatile() });\n"
        "export function apply() {}\n"
    )
    patches = [
        {
            "id": "agent-default-model",
            "config": {"provider": "local", "model": "parent-current"},
        },
        {"id": "storage-json", "config": {"root": str(tmp_path / "state/storages")}},
        {
            "id": "session-persistence-jsonl",
            "config": {"root": str(tmp_path / "state/sessions")},
        },
        {
            "id": "credentials",
            "config": {"path": str(tmp_path / "state/credentials.yml")},
        },
        {
            "insert": [
                {"id": "local-provider", "name": "./provider.mjs"},
                {"id": "settings-proof", "name": "./settings-proof.mjs"},
                {
                    "id": "fixture-preferences",
                    "name": "./preferences.mjs",
                    "config": {"ordinary": "keep"},
                },
            ]
        },
    ]
    prefix = "".join(f"- {json.dumps(patch)}\n" for patch in patches)
    patch = directory / "cordis.patch.yml"
    patch.write_text(
        "# native profile sentinel\n"
        + prefix
        + "- id: session-title-llm\n  disabled: !!js 'true' # expression comment\n"
        "- id: fixture-preferences\n  config:\n    ordinary: keep # ordinary comment\n"
    )
    env["SETTINGS_PROOF"] = str(tmp_path / "settings-proof.json")
    env.pop("PYTHONPATH", None)
    return project, directory, runtime, env


def test_native_http_ack_refresh_restart_refusals_secrets_and_picker(
    managed_web: tuple[Path, Path, DshNativeRuntime, dict[str, str]], tmp_path: Path
) -> None:
    project, directory, runtime, env = managed_web
    immutable = {
        path: path.read_bytes()
        for path in (directory / "package.json", directory / "cordis.yml")
    }
    for phase in ("write", "restart"):
        env["SETTINGS_PHASE"] = phase
        plan = prepare_dsh_launch(
            ["proof"], cwd=project, process_env=env, runtime=runtime
        )
        result = _run(plan, env, tmp_path, ["--no-open", "--port", "0"])
        assert result.returncode == 23, result.stderr
        assert (
            "failed to load @deepseek-ai/dsh-host-directory-picker" not in result.stderr
        )
        proof = json.loads(Path(env["SETTINGS_PROOF"]).read_text())
        assert proof["pickerMounted"] and proof["managedUnchanged"]
        assert proof["pickerBackend"] == (
            "native" if sys.platform in ("darwin", "win32") else "browse"
        )
        assert proof["namespaces"] > 0
    assert all(path.read_bytes() == before for path, before in immutable.items())
    assert not list(directory.glob("*.lock"))
    assert (project / ".dsh/ai-dotfiles/launch-root.json").read_bytes() == b"[]\n"
    stored = (directory / "cordis.patch.yml").read_text()
    assert "ai-dotfiles-host" not in stored and "ai-dotfiles-audit" not in stored
    assert "directory-picker-native" not in stored
    assert "directory-picker-browse" not in stored


@pytest.mark.parametrize("layer", ["home", "domain", "cli"])
def test_native_higher_override_cannot_be_overwritten(
    managed_web: tuple[Path, Path, DshNativeRuntime, dict[str, str]],
    tmp_path: Path,
    layer: str,
) -> None:
    project, directory, _runtime, env = managed_web
    override = [
        {"id": "fixture-preferences", "config": {"ordinary": "keep", "live": "locked"}}
    ]
    args = ["proof"]
    if layer == "home":
        path = directory.parent.parent / "cordis.patch.yml"
    elif layer == "domain":
        path = Path(env["AI_DOTFILES_HOME"]) / "catalog/preferences/dsh.fragment.json"
        path.parent.mkdir()
        (project / "ai-dotfiles.json").write_text(
            '{"targets":["dsh"],"packages":["@preferences"]}'
        )
    else:
        path = tmp_path / "cli-patch.json"
        args = ["--profile", "proof", "--patch", str(path)]
    path.write_text(json.dumps(override))
    before = {
        current: current.read_bytes()
        for current in (path, directory / "cordis.patch.yml")
    }
    env["SETTINGS_PHASE"] = "override"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai_dotfiles",
            "dsh",
            "launch",
            *args,
            "--no-open",
            "--port",
            "0",
        ],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 23, result.stderr
    assert all(current.read_bytes() == raw for current, raw in before.items())


@pytest.mark.parametrize("phase", ["external", "duplicate"])
def test_stale_composition_or_duplicate_namespace_preserves_profile(
    managed_web: tuple[Path, Path, DshNativeRuntime, dict[str, str]],
    tmp_path: Path,
    phase: str,
) -> None:
    project, directory, runtime, env = managed_web
    if phase == "duplicate":
        (directory / "duplicate.json").write_text(
            json.dumps(
                [
                    {
                        "id": "fixture-preferences",
                        "name": "./preferences.mjs",
                        "config": {"ordinary": "keep"},
                    }
                ]
            )
        )
        with (directory / "cordis.patch.yml").open("a") as stream:
            stream.write(
                "- insert:\n  - id: duplicate-settings\n    name: cordis:include\n"
                "    config: {path: ./duplicate.json}\n"
            )
    env["SETTINGS_PHASE"] = phase
    plan = prepare_dsh_launch(["proof"], cwd=project, process_env=env, runtime=runtime)
    result = _run(plan, env, tmp_path, ["--no-open", "--port", "0"])
    assert result.returncode == 23, result.stderr
