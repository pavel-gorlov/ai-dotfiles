"""Managed, immutable RC2 host with a same-process audit before surface release.

No profile preparation, package installation, shell, or durable audit session is
used. Native profile patches are composed through the shipped helper. The small
host uses the published Cordis EntryTree extension, preserving the profile base
for relative imports while keeping its root and include snapshots in memory.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from importlib import resources
from pathlib import Path
from typing import Literal

from ai_dotfiles.core import manifest, paths
from ai_dotfiles.core.agents_md import block_markers
from ai_dotfiles.core.dependencies import topological_sort
from ai_dotfiles.core.dsh_audit import DshAuditRequirements
from ai_dotfiles.core.dsh_config import (
    DshConfigPlan,
    DshConfigSource,
    DshNativeContribution,
    attach_dsh_config_outputs,
    collect_dsh_config_sources,
    collect_dsh_configuration,
    compose_dsh_configuration,
    inspect_dsh_configuration,
    validate_native_fragment,
)
from ai_dotfiles.core.dsh_hooks import (
    DshHookSource,
    attach_dsh_hook_outputs,
    collect_dsh_hooks,
)
from ai_dotfiles.core.dsh_install import (
    DshInstallPlan,
    DshOutput,
    InstallMode,
    apply_dsh_install,
    collect_dsh_elements,
    plan_dsh_install,
    preflight_dsh_install,
)
from ai_dotfiles.core.dsh_layout import DshLayout, global_layout, project_layout
from ai_dotfiles.core.dsh_local_registry import load_dsh_local_registry
from ai_dotfiles.core.dsh_migrate import (
    DshLocalInputs,
    collect_dsh_local_inputs,
    verify_dsh_local_inputs,
)
from ai_dotfiles.core.dsh_native import (
    DshNativeRuntime,
    compose_module_text,
    native_frontmatter,
    resolve_dsh_runtime,
)
from ai_dotfiles.core.dsh_render import DshDiagnostic, DshProvenance, render_rule
from ai_dotfiles.core.dsh_targets import project_target_plan
from ai_dotfiles.core.elements import Element, parse_elements
from ai_dotfiles.core.errors import AiDotfilesError, ConfigError, ExternalError
from ai_dotfiles.core.shared_instructions import project_instruction_plan
from ai_dotfiles.core.targets import Target

DSH_LAUNCH_GENERATOR_VERSION = 2
RESTART_NOTICE = (
    "Managed DSH stays bound to this project's MCP, hooks and agents. "
    "Restart after managed updates or when changing projects. "
    "Web workspace switching does not provide hard isolation. "
    "Native hot reload is disabled."
)

# These are the public RC2 application entry points, not arbitrary user plugins.
# Their rows are restored verbatim only after the managed audit succeeds.
_HOST_MODULE = r"""
import { createRequire } from 'node:module';
import { readFileSync, lstatSync, realpathSync } from 'node:fs';
import { isAbsolute, resolve, relative, dirname, sep } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import { isDeepStrictEqual } from 'node:util';
const state = { trees: [], released: false, requiredIds: new Set() };
const helper = await import('./compose.mjs');
const runtimeAnchor = __RUNTIME_ANCHOR__;
const native = await helper.loadNative(runtimeAnchor);
const require = createRequire(runtimeAnchor);
const load = async name => import(pathToFileURL(require.resolve(name)).href);
const { EntryTree, EntryGroup, isJsExpr } = await load(
  '@deepseek-ai/cordis-plugin-loader');
const { Service } = await load('@deepseek-ai/cordis');
const surfaces = new Set([
  '@deepseek-ai/dsh-headless', '@deepseek-ai/dsh-host-webserver',
  '@deepseek-ai/dsh-web-app', '@deepseek-ai/dsh-acp',
  '@deepseek-ai/dsh-sdk-jsonrpc-server',
  '@deepseek-ai/dsh-client-modules', '@deepseek-ai/dsh-client-connection',
]);
const includes = new Set(['cordis:include', '@deepseek-ai/cordis-plugin-include']);

function freezeRows(rows, baseUrl, ancestors = new Set()) {
  return rows.map(original => {
    const row = structuredClone(original);
    if (row.name === '@deepseek-ai/dsh-config-editor')
      row.name = new URL('./managed-settings.mjs', import.meta.url).href;
    // Official HMR replaces the host root from mutable user profile patches.
    // Managed composition is immutable and requires an explicit restart.
    if (row.name === '@deepseek-ai/dsh-hmr') {
      if (state.requiredIds.has(row.id))
        throw new Error(`Required managed HMR row ${row.id} conflicts with `
          + 'immutable composition; managed launch requires restart');
      row.disabled = true;
    }
    if (includes.has(row.name) && row.disabled !== true) {
      if (typeof row.config?.path !== 'string')
        throw new Error('Unsupported native include path');
      const filename = isAbsolute(row.config.path) ? row.config.path
        : fileURLToPath(new URL(row.config.path, baseUrl));
      if (ancestors.has(filename))
        throw new Error(`Recursive native include: ${filename}`);
      const next = new Set([...ancestors, filename]);
      const url = pathToFileURL(filename).href;
      let parsed;
      try {
        const text = readFileSync(filename, 'utf8');
        parsed = filename.endsWith('.json') ? JSON.parse(text)
          : native.includeYaml.load(text, { schema: native.include.entryListSchema });
      } catch (error) {
        throw new Error(`Read-only native include ${filename}: ${error.message}`);
      }
      if (!Array.isArray(parsed))
        throw new Error(`Native include must contain an entry list: ${filename}`);
      const effective = native.include.applyEntryPatches(
        parsed, row.config.patches, message => {
          throw new Error(`Unprovable include patch: ${filename}: ${message}`);
        });
      row.name = import.meta.url;
      row.config = { baseUrl: new URL('.', url).href,
        entries: freezeRows(effective, new URL('.', url).href, next) };
    } else if ((row.group === true || row.name === 'cordis:group')
      && Array.isArray(row.config)) {
      row.config = freezeRows(row.config, baseUrl, ancestors);
    } else if (row.name === '@deepseek-ai/dsh-agent-preset'
      && Array.isArray(row.config?.plugins)) {
      if (row.config.plugins.some(child => surfaces.has(child.name)
        && child.disabled !== true))
        throw new Error('Unsupported native surface inside a preset; '
          + 'custom profiles are not repaired');
      row.config.plugins = freezeRows(row.config.plugins, baseUrl, ancestors);
    }
    return row;
  });
}

function stage(rows) {
  return rows.map(original => {
    const row = structuredClone(original);
    if (surfaces.has(row.name)) row.disabled = true;
    // agent-loop is the lazy core factory, not an app. Keep it available for
    // scoped prompt/agent services, deferring only declarative eager Agents.
    if (row.name === '@deepseek-ai/dsh-agent-loop' && row.config?.agents) {
      if (!Array.isArray(row.config.agents))
        throw new Error('Unprovable dynamic eager agent-loop configuration');
      row.config.agents = [];
    }
    if ((row.group === true || row.name === 'cordis:group')
      && Array.isArray(row.config)) row.config = stage(row.config);
    return row;
  });
}

// Public native EntryTree/root.update/Service.init, also used by PresetTree.
export default class ImmutableProfileTree extends EntryTree {
    static inject = ['loader'];
    static [EntryGroup.key] = true;
    constructor(context, config) {
      super(context);
      this.ctx.baseUrl = config.baseUrl;
      this.complete = config.entries;
      state.trees.push(this);
    }
    async *[Service.init]() {
      yield () => this.root.stop();
      await this.root.update(state.released ? this.complete : stage(this.complete));
    }
    write() {}
}

async function releaseRows(tree, rows) {
    for (const row of rows) {
    if (surfaces.has(row.name)
      || (row.name === '@deepseek-ai/dsh-agent-loop' && row.config?.agents)) {
      await tree.resolve(row.id).update({ ...row, disabled: row.disabled ?? null });
    }
    if ((row.group === true || row.name === 'cordis:group')
      && Array.isArray(row.config)) await releaseRows(tree, row.config);
  }
}

function readySignal() {
  let ready = false;
  const listeners = new Set();
  return {
    service: { onReady(listener) {
      if (ready) { listener(); return () => {}; }
      listeners.add(listener); return () => listeners.delete(listener);
    } },
    commit() {
      ready = true;
      for (const listener of [...listeners]) listener();
      listeners.clear();
    },
  };
}

function selectedEntries(ctx, scope) {
  const entries = [...ctx.loader.entries()];
  if (scope?.ctx === undefined) return entries;
  const service = ctx.agentPresets.serviceFor(scope, 'aiDotfilesAudit');
  // Published Cordis Impl -> Fiber -> Entry identifies the selected tree.
  for (const key of Object.getOwnPropertySymbols(ctx.reflect.store)) {
    const impl = ctx.reflect.store[key];
    if (impl?.name === 'aiDotfilesAudit' && impl.value === service) {
      const tree = impl.fiber.entry?.parent.tree;
      if (tree !== undefined) return [...new Set([...entries, ...tree.entries()])];
    }
  }
  throw new Error('Cannot prove actual selected instruction-provider tree');
}

async function validateBeforeRelease(ctx, scope, request) {
  const entries = selectedEntries(ctx, scope);
  const serviceFor = name => (scope?.ctx === undefined ? undefined
    : ctx.agentPresets?.serviceFor(scope, name)) ?? scope?.ctx?.get(name)
    ?? ctx.get(name);
  const llm = serviceFor('llm');
  const selection = serviceFor('agentDefaultModel')?.currentSelection();
  const providers = new Set(selection === undefined ? [] : [selection.provider]);
  for (const entry of entries) {
    if (entry.options.name === '@deepseek-ai/dsh-tool-subagent') {
      const provider = entry.fiber?.config?.agentOptions?.provider;
      if (provider !== undefined) providers.add(provider);
    }
  }
  for (const provider of providers) {
    if (llm === undefined)
      throw new Error(`Missing native llm provider service: ${provider}`);
    try { llm.providerRetryPolicy(provider); }
    catch {
      throw new Error(`Native model provider ${provider} is not mounted; `
        + 'activate its provider in the existing profile');
    }
  }
  if (request.requiredSkills.length) {
    if (!entries.some(entry =>
      entry.options.name === '@deepseek-ai/dsh-skill-filesystem'
      && !entry.disabled && entry.fiber?.state === 2))
      throw new Error('Missing active native filesystem skill provider; '
        + 'custom profiles are not repaired');
    const skills = (scope?.ctx === undefined ? undefined
      : ctx.agentPresets?.serviceFor(scope, 'skills')) ?? ctx.get('skills');
    if (skills === undefined) throw new Error('Missing native skills service');
    const listed = await skills.list({ cwd: process.cwd(), scope });
    for (const expected of request.requiredSkills) {
      const actual = listed.find(skill => skill.name === expected.name);
      if (actual === undefined || actual.description !== expected.description)
        throw new Error(`Managed native skill ${expected.name} is not `
          + 'discoverable with its original description');
    }
  }
  if (!(request.instructionGuards?.length)) return;
  const instructions = await load('@deepseek-ai/dsh-agent-instructions');
  for (const entry of entries) {
    if (entry.options.name !== '@deepseek-ai/dsh-agent-instructions'
      || entry.disabled || entry.fiber?.state !== 2) continue;
    const config = entry.fiber.config;
    if (!(config.maxBytes > 0 && config.maxSourceBytes > 0)) continue;
    for (const guard of request.instructionGuards) {
      const files = await instructions.discoverBaselineInstructionFiles({
        ...config,
        cwd: fileURLToPath(new URL('.', pathToFileURL(guard.path))) });
      if (!files.some(file =>
        resolve(file.absolutePath) === resolve(guard.path))) continue;
      let text;
      try { text = readFileSync(guard.path, 'utf8'); }
      catch (error) { if (error.code === 'ENOENT') continue; throw error; }
      if (text.includes(guard.start) && text.includes(guard.end))
        throw new Error(`${guard.source} ${guard.field}: native instruction `
          + `provider ${entry.id} would load ${guard.path}:${guard.name} `
          + `unconditionally; ${guard.reason}`);
    }
  }
}

function verifySourceGuards(request) {
  for (const [filename, digest] of Object.entries(request.sourceHashes)) {
    if (createHash('sha256').update(readFileSync(filename)).digest('hex') !== digest)
      throw new Error(`Managed DSH source changed before readiness: ${filename}`);
  }
  for (const guard of request.localSourceGuards ?? []) {
    let present = true, existing = guard.path;
    try { lstatSync(existing); }
    catch (error) { if (error.code !== 'ENOENT') throw error; present = false; }
    while (true) {
      try { lstatSync(existing); break; }
      catch (error) {
        if (error.code !== 'ENOENT') throw error;
        existing = dirname(existing);
      }
    }
    const bounded = relative(realpathSync(request.localSourceRoot),
      realpathSync(existing));
    if (bounded === '..' || bounded.startsWith(`..${sep}`) || isAbsolute(bounded))
      throw new Error('Local DSH original/ownership resolves outside project: '
        + guard.path);
    const digest = present
      ? createHash('sha256').update(readFileSync(guard.path)).digest('hex') : null;
    if (digest !== guard.source_sha256)
      throw new Error('Local DSH original/ownership changed before readiness: '
        + guard.path);
  }
}

function settingsSnapshot(rows, id, config) {
  const result = structuredClone(rows);
  let count = 0;
  const walk = rows => {
    for (const row of rows) {
      if (row.id === id) {
        if (config === undefined) delete row.config;
        else row.config = structuredClone(config);
        count++;
      }
      else {
        if (Array.isArray(row.config)) walk(row.config);
        if (Array.isArray(row.config?.plugins)) walk(row.config.plugins);
        if (Array.isArray(row.config?.entries)) walk(row.config.entries);
      }
    }
  };
  walk(result);
  if (count !== 1) throw new Error('Settings entry id is not unique in composition');
  return result;
}

export async function runManaged(request, args) {
  if (request.runtimeAnchor !== runtimeAnchor)
    throw new Error('Managed host runtime anchor changed');
  const cmdline = await load('@deepseek-ai/dsh-cmdline');
  const environment = await load('@deepseek-ai/dsh-launch-environment');
  const proxy = await load('@deepseek-ai/dsh-http-proxy');
  verifySourceGuards(request);
  for (const name of ['boot', 'PluginPackages', 'createRuntimeResolution',
    'prepareProfilePatches', 'auditStartupEntries'])
    if (typeof native.boot[name] !== 'function')
      throw new Error(`Unsupported RC2 host API: ${name}`);
  if (typeof cmdline.provideCmdline !== 'function')
    throw new Error('Unsupported RC2 cmdline API');
  const inspected = await helper.inspectComposition(native, request.composition);
  if (!inspected.valid) throw new Error('Managed DSH composition is invalid');
  const collectRequired = rows => {
    for (const row of rows) {
      for (const id of row.config?.requiredIds ?? []) state.requiredIds.add(id);
      if (Array.isArray(row.config)) collectRequired(row.config);
      if (Array.isArray(row.config?.plugins)) collectRequired(row.config.plugins);
    }
  };
  collectRequired(inspected.entries);
  const profile = native.boot.loadProfileDirectory('ai-dotfiles',
    inspected.profile.dir, request.runtimeAnchor);
  const resolution = await native.boot.createRuntimeResolution({
    installAnchor: request.runtimeAnchor, profile });
  const baseUrl = new URL('.', pathToFileURL(resolve(profile.dir, 'cordis.yml'))).href;
  const profileContext = { ...inspected.profile, installAnchor: request.runtimeAnchor,
    cwd: process.cwd(), home: request.composition.home, overlays: [],
    telemetryDisabledEnv: process.env.DSH_TELEMETRY_DISABLED };
  const ready = readySignal();
  const launchEnvironment = native.boot.loadLayeredEnv('ai-dotfiles dsh');
  let ctx, scope, disposal, requestedExit, timer;
  const disposeProxy = await proxy.installProxyFromEnvironment(launchEnvironment,
    message => process.stderr.write(`dsh: ${message}\n`));
  const dispose = () => disposal ??= (async () => {
    await scope?.dispose(); await ctx?.fiber.dispose(); await disposeProxy();
  })();
  const shutdown = code => {
    requestedExit ??= code;
    timer ??= setTimeout(() => process.exit(requestedExit), 5000);
    void dispose().then(() => {
      clearTimeout(timer); process.exitCode = requestedExit;
    }, error => {
      process.stderr.write(`Managed DSH cleanup failed: ${error.message}\n`);
      process.exit(requestedExit || 1);
    });
  };
  const interrupt = code => requestedExit === undefined
    ? shutdown(code) : process.exit(code);
  process.on('SIGINT', () => interrupt(130));
  process.on('SIGTERM', () => interrupt(143));
  native.boot.installFailLoud('ai-dotfiles dsh', process, dispose);
  try {
    const patches = [];
    ctx = await native.boot.boot('ai-dotfiles dsh', request.rootPath, patches,
      async host => {
      ctx = host;
      // Dynamic native loader.create({ name }) entries use the root Loader,
      // unlike profile rows. Bind its public context to the installed runtime;
      // ImmutableProfileTree keeps each profile/include's own relative base.
      host.loader.root.ctx.baseUrl = pathToFileURL(request.runtimeAnchor).href;
      host.provide('profileContext', profileContext);
      host.provide(environment.DSH_LAUNCH_ENVIRONMENT_KEY, launchEnvironment);
      await host.plugin(native.boot.PluginPackages, { resolution });
      cmdline.provideCmdline(host, { args, ready: ready.service, exit: shutdown });
      const prepared = native.boot.prepareProfilePatches(host,
        inspected.patches, baseUrl, 'ai-dotfiles dsh');
      const entries = native.boot.composeEntries([prepared]);
      let snapshot = freezeRows(entries, baseUrl);
      const initialSettings = helper.inspectSettingsComposition(native,
        request.composition);
      const allowed = new Set(initialSettings.editableIds);
      const frozen = layers => freezeRows(native.boot.composeEntries([
        native.boot.prepareProfilePatches(host, layers.patches, baseUrl,
          'ai-dotfiles dsh')]), baseUrl);
      host.provide('aiDotfilesManagedSettings', {
        owns: entry => allowed.has(entry.options.id)
          && !state.requiredIds.has(entry.options.id)
          && entry.parent.tree === state.trees[0],
        read: patches => helper.inspectSettingsComposition(native,
          request.composition, patches),
        inherited: (profile, id) => helper.inheritedSettingsConfig(native,
          request.composition, profile, id),
        validate(layers, entry, next) {
          verifySourceGuards(request);
          if (!layers.valid || !layers.editableIds.includes(entry.options.id))
            throw new Error('Settings entry is managed or overridden by a '
              + 'domain, home patch or command-line overlay');
          const expected = settingsSnapshot(snapshot, entry.options.id, next);
          if (!isDeepStrictEqual(frozen(layers), expected))
            throw new Error('Settings composition changed; restart managed DSH '
              + 'before editing its native profile');
        },
        committed(entry, next) {
          snapshot = settingsSnapshot(snapshot, entry.options.id, next);
        },
      });
      patches.push({ insert: [{ id: 'ai-dotfiles-host', name: import.meta.url,
        config: { baseUrl, entries: snapshot } }] });
    }, pathToFileURL(request.runtimeAnchor).href);
    if (requestedExit !== undefined) return;
    // The boot root contains only our origin-bound immutable native tree.
    const tree = state.trees[0];
    if (tree === undefined) throw new Error('Managed profile tree failed to load');
    if (inspected.selection.kind === 'preset') {
      const hasGlobalHeadless = (mounted, rows) => rows.some(row => {
        if (row.name === '@deepseek-ai/dsh-headless') {
          const entry = mounted.resolve(row.id);
          const disabled = isJsExpr(row.disabled)
            ? Boolean(entry.evaluate(row.disabled.__jsExpr))
            : Boolean(row.disabled);
          return !disabled && !entry.parent.ctx.fiber.entry?.disabled;
        }
        return Array.isArray(row.config) && hasGlobalHeadless(mounted, row.config);
      });
      if (state.trees.some(mounted =>
        hasGlobalHeadless(mounted, mounted.complete)))
        throw new Error('COMPOSITION_NOT_SELECTED: native RC2 headless runs '
          + 'global Agents while this profile selects a managed preset; '
          + 'use a preset-free existing headless profile or the native '
          + 'preset-aware Web surface');
      scope = {};
      Object.assign(scope, native.scope.createScope(ctx, scope));
      await helper.mountSelectedComposition(scope.ctx, inspected.selection);
    }
    await helper.auditBeforeReady(ctx, { selection: inspected.selection, scope,
      commit: async report => {
        if (report.ready !== true)
          throw new Error('Managed DSH audit did not report readiness');
        await validateBeforeRelease(ctx, scope, request);
        verifySourceGuards(request);
        ready.commit();
      } });
    if (requestedExit !== undefined) return;
    state.released = true;
    // Include trees may be created during release; new trees see released=true.
    for (const mounted of [...state.trees])
      await releaseRows(mounted, mounted.complete);
    await ctx.loader.await();
    if (requestedExit === undefined)
      await native.boot.auditStartupEntries(ctx, 'ai-dotfiles dsh');
    if (requestedExit === undefined)
      process.stderr.write('Managed DSH audit passed; native surface released.\n');
  } catch (error) {
    try { await dispose(); } finally { clearTimeout(timer); }
    process.stderr.write(`Managed DSH startup refused: ${error.message}\n`);
    process.exitCode = 1;
  }
}
"""


@dataclass(frozen=True)
class DshLaunchArguments:
    """Native launcher flags separated from the verbatim application argv."""

    profile: str
    patch_files: tuple[Path, ...]
    app_args: tuple[str, ...]


@dataclass(frozen=True)
class DshLaunchPlan:
    """Prepared raw-source composition; neither inspection nor planning is ready."""

    runtime: DshNativeRuntime
    cwd: Path
    arguments: DshLaunchArguments
    config: DshConfigPlan
    installs: tuple[DshInstallPlan, ...]
    request: Mapping[str, object]
    diagnostics: tuple[DshDiagnostic, ...]
    local_inputs: tuple[DshLocalInputs, ...] = ()


def parse_dsh_launch_arguments(args: Sequence[str], *, cwd: Path) -> DshLaunchArguments:
    """Match native leading --profile/--patch parsing and profile shorthand.

    The first application token ends launcher parsing. Mutating profile/plugin
    and dump commands are explicitly outside managed launch; use official dsh.
    """
    remaining = list(args)
    profile: str | None = None
    patches: list[Path] = []
    if remaining and not remaining[0].startswith("-"):
        profile = remaining.pop(0)
    while remaining:
        token = remaining[0]
        if token in (
            "--from-default-profile",
            "--dump-config",
            "--dump-config-schema",
            "--dump-default-config",
        ) or token.startswith("--from-default-profile="):
            raise ConfigError(
                "Managed launch does not create/repair profiles or dump "
                "configuration; use official dsh for this command"
            )
        name, separator, value = token.partition("=")
        if name not in ("--profile", "--patch"):
            break
        remaining.pop(0)
        if not separator:
            if not remaining or remaining[0].startswith("-"):
                raise ConfigError(f"{name} requires a value")
            value = remaining.pop(0)
        if not value:
            raise ConfigError(f"{name} requires a value")
        if name == "--profile":
            if profile is not None:
                raise ConfigError("Select a native DSH profile only once")
            profile = value
        else:
            patches.append(Path(os.path.abspath(cwd / value)))
    if profile is None:
        raise ConfigError(
            "A native profile is required: ai-dotfiles dsh launch "
            "--profile <name> [--patch <path>] [app-args...]"
        )
    if (
        profile.lower() == "desktop"
        or profile in ("plugin", ".", "..", "node_modules")
        or "/" in profile
        or "\\" in profile
    ):
        raise ConfigError(
            f"Unsupported managed native profile: {profile!r}; "
            "use an existing CLI profile"
        )
    return DshLaunchArguments(profile, tuple(patches), tuple(remaining))


def discover_dsh_runtime(*, process_env: Mapping[str, str]) -> DshNativeRuntime:
    """Resolve a genuine installed official bin, refusing executable wrappers."""
    executable = shutil.which("dsh", path=process_env.get("PATH", os.defpath))
    if executable is None:
        raise ExternalError(
            "Official dsh executable is missing from PATH; "
            "install @deepseek-ai/dsh 0.2.0-rc.2 separately"
        )
    cli = Path(executable).resolve()
    if cli.name != "bin.js" or cli.parent.name != "lib":
        raise ConfigError(
            f"Unsupported dsh wrapper: {executable}; "
            "put the official package's dsh bin on PATH"
        )
    node = shutil.which("node", path=process_env.get("PATH", os.defpath))
    if node is None:
        raise ExternalError(
            "Node executable is missing from the launching process PATH"
        )
    runtime = resolve_dsh_runtime(cli.parent.parent, node=node)
    if runtime.cli.resolve() != cli:
        raise ConfigError(f"Unsupported official dsh executable path: {cli}")
    return runtime


def launch_module_text(runtime: DshNativeRuntime) -> str:
    """Return the versioned finite native host, embedded in this owned module."""
    digest = hashlib.sha256(_HOST_MODULE.encode()).hexdigest()
    return (
        "// managed-by: ai-dotfiles\n"
        f"// source-sha256: {digest}\n"
        f"// generator: {DSH_LAUNCH_GENERATOR_VERSION}\n"
        + _HOST_MODULE.replace(
            "__RUNTIME_ANCHOR__", json.dumps(str(runtime.install_anchor))
        )
    )


def managed_settings_module_text(runtime: DshNativeRuntime) -> str:
    """Render the bounded native editor against the verified installed runtime."""
    source = resources.files("ai_dotfiles.scaffold.templates").joinpath(
        "dsh_managed_settings.mjs"
    )
    try:
        content = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ConfigError(f"Cannot read shipped DSH settings editor: {exc}") from exc
    return content.replace(
        "__RUNTIME_ANCHOR__", json.dumps(str(runtime.install_anchor))
    )


def _collect_plan(
    elements: Sequence[Element],
    layout: DshLayout,
    catalog: Path,
    runtime: DshNativeRuntime,
    cwd: Path,
    env: Mapping[str, str],
    targets: Sequence[Target],
    *,
    mode: InstallMode = "link",
) -> DshInstallPlan:
    plan = collect_dsh_elements(elements, layout, catalog, targets=targets, mode=mode)
    deferred = tuple(
        result.provenance.source
        for result in (*plan.skills, *plan.agents, *plan.rules)
        if result.status == "DEFERRED"
    )
    if deferred:
        metadata = native_frontmatter(runtime, deferred, cwd=cwd, env=env)
        plan = collect_dsh_elements(
            elements,
            layout,
            catalog,
            targets=targets,
            mode=mode,
            native_frontmatter=metadata,
        )
    return plan


def _refuse_retired_discovery(plan: DshInstallPlan) -> None:
    inventory = preflight_dsh_install(plan)
    retired = [
        key
        for key in inventory.records
        if key.startswith("skills/")
        and key not in plan.desired_output_keys
        and (plan.layout.dsh_dir / key).exists()
    ]
    desired = {
        result.payload.name
        for result in plan.shared_rules
        if result.payload is not None
    }
    protected = plan.instructions.keep_blocks if plan.instructions is not None else {}
    for relative, names in inventory.rule_blocks.items():
        path = (plan.layout.project_root or plan.layout.dsh_dir) / relative
        if path.exists():
            retired.extend(
                f"{relative}:{name}"
                for name in names
                if name not in desired
                and name not in protected.get(path.resolve(), set())
            )
    if retired:
        raise ConfigError(
            "Stale native-discovered DSH outputs require reconciliation before launch: "
            + ", ".join(retired)
            + "; run ai-dotfiles reconcile in the affected scope"
        )


def prepare_dsh_launch(
    args: Sequence[str],
    *,
    cwd: Path,
    process_env: Mapping[str, str],
    runtime: DshNativeRuntime | None = None,
    extra_sources: Sequence[DshConfigSource] = (),
    extra_install_plans: Sequence[DshInstallPlan] = (),
) -> DshLaunchPlan:
    """Collect current global/project originals and inspect without profile writes.

    Registered project-local originals are freshly rendered by their producer
    into the same catalog plan. Extra inputs remain an internal typed boundary.
    Serialized config.json and registry values are never activation inputs.
    """
    cwd = Path(os.path.abspath(cwd))
    arguments = parse_dsh_launch_arguments(args, cwd=cwd)
    runtime = runtime or discover_dsh_runtime(process_env=process_env)
    root = paths.find_project_root(cwd) or cwd
    layout = project_layout(root)
    catalog = paths.catalog_dir()
    installs: list[DshInstallPlan] = []
    sources: list[DshConfigSource] = []
    hook_sources: list[DshHookSource] = []
    local_inputs: list[DshLocalInputs] = []
    enabled = False
    instruction_guards: list[dict[str, str]] = []
    for manifest_path, scope_layout in (
        (paths.global_manifest_path(), global_layout()),
        (paths.project_manifest_path(root), layout),
    ):
        registered = scope_layout.local_registry_path.exists()
        registry = None
        if registered:
            try:
                if scope_layout.project_root is None:
                    raise ConfigError(
                        "Local migration is supported only in project scope"
                    )
                registry = load_dsh_local_registry(root)
            except AiDotfilesError as exc:
                raise ConfigError(
                    f"Local DSH registry {scope_layout.local_registry_path} "
                    f"cannot pass local migration integration validation: {exc}"
                ) from exc
        names = manifest.get_targets(manifest_path)
        mode: InstallMode = (
            "copy" if manifest.get_link_mode(manifest_path) == "copy" else "link"
        )
        try:
            targets = [Target(name) for name in names]
        except ValueError as exc:
            raise ConfigError(
                f"Unknown manifest target in {manifest_path}: {exc}"
            ) from exc
        elements = topological_sort(
            catalog, parse_elements(manifest.get_packages(manifest_path))
        )
        instructions = (
            project_instruction_plan(elements, targets, root, catalog)
            if scope_layout.project_root is not None
            else None
        )
        plan = (
            _collect_plan(
                elements,
                scope_layout,
                catalog,
                runtime,
                cwd,
                process_env,
                targets,
                mode=mode,
            )
            if "dsh" in names
            else plan_dsh_install(scope_layout, instructions=instructions)
        )
        if "dsh" in names:
            sources.extend(collect_dsh_config_sources(elements, catalog, scope_layout))
        local = None
        if registered:
            local = collect_dsh_local_inputs(
                root,
                manifest_packages=manifest.get_packages(manifest_path),
                catalog_plan=plan,
                mode=mode,
                registered_only=True,
            )
            deferred = tuple(
                result.provenance.source
                for result in (*local.local_results, *local.commands)
                if result.status == "DEFERRED"
            )
            if deferred:
                metadata = native_frontmatter(
                    runtime, deferred, cwd=cwd, env=process_env
                )
                local = collect_dsh_local_inputs(
                    root,
                    manifest_packages=manifest.get_packages(manifest_path),
                    catalog_plan=plan,
                    mode=mode,
                    registered_only=True,
                    native_frontmatter=metadata,
                )
            local_inputs.append(local)
            plan = local.install
            sources.extend(local.config_sources)
            hook_sources.extend(local.hook_sources)
        if instructions is not None:
            for block in instructions.blocks:
                if Target.DSH in block.contributors:
                    continue
                result = render_rule(block.sources[0])
                if result.status == "DEFERRED":
                    metadata = native_frontmatter(
                        runtime, [block.sources[0]], cwd=cwd, env=process_env
                    )
                    result = render_rule(
                        block.sources[0], native_frontmatter=metadata[block.sources[0]]
                    )
                if result.status == "READY":
                    continue
                start, end = block_markers(block.name)
                instruction_guards.append(
                    {
                        "path": str(block.path),
                        "name": block.name,
                        "source": str(block.sources[0]),
                        "field": "paths",
                        "start": start,
                        "end": end,
                        "reason": (
                            "DSH path activation is unsupported; "
                            "shared Codex bytes are preserved"
                        ),
                    }
                )
            for path, block_names in instructions.protected_blocks.items():
                proved_local = {
                    result.payload.name
                    for result in plan.shared_rules
                    if result.provenance.origin == "local"
                    and result.payload is not None
                    and path == root / "AGENTS.md"
                }
                for name in (
                    block_names
                    - instructions.wanted_blocks.get(path, set())
                    - proved_local
                ):
                    start, end = block_markers(name)
                    original = (
                        next(
                            (
                                root / source
                                for source, record in registry.sources.items()
                                if record["kind"] == "rule"
                                and record["element"] == f"rule:{name}"
                            ),
                            None,
                        )
                        if registry is not None
                        else None
                    )
                    instruction_guards.append(
                        {
                            "path": str(path),
                            "name": name,
                            "source": str(
                                original or root / ".codex/.ai-dotfiles-local.json"
                            ),
                            "field": (
                                "source" if original is not None else "rule_blocks"
                            ),
                            "start": start,
                            "end": end,
                            "reason": (
                                "local instruction activation cannot be proved "
                                "from protection-only provenance; migrate the "
                                "original local source to DSH before activating "
                                "this provider"
                            ),
                        }
                    )
        if "dsh" not in names and local is None:
            _refuse_retired_discovery(plan)
            continue
        enabled = True
        installs.append(plan)
    if not enabled and not extra_install_plans:
        raise ConfigError(
            'DSH target is not enabled; add "dsh" to targets in '
            "ai-dotfiles.json or global.json"
        )
    # The storage original is not ~/.claude/settings.json's merged destination.
    originals: tuple[
        tuple[Path, Literal["settings", "mcp"], Literal["global", "project"]], ...
    ] = (
        (paths.global_dir() / "settings.json", "settings", "global"),
        (root / ".claude/settings.local.json", "settings", "project"),
    )
    for source, kind, scope in originals:
        if source.is_file() and not (scope == "project" and local_inputs):
            sources.append(
                DshConfigSource(
                    source, kind, scope, str(source), str(source), source.parent
                )
            )
    for source, kind, ledger in (
        (
            root / ".claude/settings.json",
            "settings",
            root / ".claude/.ai-dotfiles-settings-ownership.json",
        ),
        (root / ".mcp.json", "mcp", root / ".claude/.ai-dotfiles-mcp-ownership.json"),
    ):
        if source.is_file() and not ledger.exists() and not local_inputs:
            sources.append(
                DshConfigSource(
                    source, kind, "project", str(source), str(source), source.parent
                )
            )
    sources.extend(extra_sources)
    installs.extend(extra_install_plans)
    layouts = [plan.layout for plan in installs]
    if len(set(layouts)) != len(layouts):
        raise ConfigError(
            "Extra DSH render plans duplicate an existing layout; the original "
            "producer must merge catalog/local results before managed activation"
        )
    current = next(
        (plan for plan in installs if plan.layout == layout), plan_dsh_install(layout)
    )
    hooks = collect_dsh_hooks(
        (*sources, *hook_sources), layout, project_root=root, install_plans=installs
    )
    contribution = hooks.contribution()
    skill_results = {
        result.payload.name: result
        for plan in sorted(
            installs, key=lambda item: item.layout.project_root is not None
        )
        for result in (
            *plan.skills,
            *(
                command
                for local in local_inputs
                if local.layout == plan.layout
                for command in local.commands
            ),
        )
        if result.status == "READY" and result.payload is not None
    }
    contributions = [] if contribution is None else [contribution]
    if skill_results:
        contributions.append(
            DshNativeContribution(
                "skills",
                "project",
                (),
                tuple(result.provenance for result in skill_results.values()),
                DshAuditRequirements((), (), ("skills",), ()),
            )
        )
    config = collect_dsh_configuration(sources, layout, contributions=contributions)
    config = compose_dsh_configuration(
        config, installs, target_plans=(project_target_plan(root, cwd),)
    )
    current = attach_dsh_config_outputs(attach_dsh_hook_outputs(current, hooks), config)
    host_path, helper_path, root_path = (
        layout.owned_dir / name
        for name in ("launch.mjs", "compose.mjs", "launch-root.json")
    )
    source = Path(__file__)
    provenance = DshProvenance(
        source,
        "builtin",
        "dsh-launch",
        hashlib.sha256(source.read_bytes()).hexdigest(),
        DSH_LAUNCH_GENERATOR_VERSION,
    )
    host_outputs = tuple(
        DshOutput(
            path,
            "generated",
            (provenance,),
            {"launch": DSH_LAUNCH_GENERATOR_VERSION},
            content=content.encode(),
        )
        for path, content in (
            (host_path, launch_module_text(runtime)),
            (helper_path, compose_module_text()),
            (
                layout.owned_dir / "managed-settings.mjs",
                managed_settings_module_text(runtime),
            ),
            (root_path, "[]\n"),
        )
    )
    current = replace(
        current,
        outputs=(
            *(
                (
                    replace(output, provenance=(provenance,))
                    if not output.provenance
                    else output
                )
                for output in current.outputs
            ),
            *host_outputs,
        ),
    )
    installs = [plan for plan in installs if plan.layout != layout] + [current]
    for plan in installs:
        _refuse_retired_discovery(plan)
    home = paths.dsh_home()
    profile_dir = home / "profiles" / arguments.profile
    inspected = inspect_dsh_configuration(
        config,
        runtime,
        profile_dir=profile_dir,
        home=home,
        cwd=cwd,
        process_env=process_env,
        cli_patch_files=arguments.patch_files,
    )
    source_hashes = {
        str(part.source.absolute()): part.source_sha256
        for plan in installs
        for result in (*plan.skills, *plan.agents, *plan.rules)
        for part in (result.provenance,)
    }
    source_hashes.update(
        {str(part.source.absolute()): part.source_sha256 for part in hooks.provenance}
    )
    source_hashes.update(
        {str(item["source"]): str(item["source_sha256"]) for item in config.sources}
    )
    source_hashes.update(
        {str(path.absolute()): digest for path, _, digest in config.permission_modes}
    )
    for local in local_inputs:
        verify_dsh_local_inputs(local)
        source_hashes.update(
            {
                str(result.provenance.source): result.provenance.source_sha256
                for result in local.commands
            }
        )
    request: dict[str, object] = {
        "localSourceRoot": str(root),
        "localSourceGuards": [
            {"path": str(guard.path), "source_sha256": guard.source_sha256}
            for local in local_inputs
            for guard in local.guards
        ],
        "runtimeAnchor": str(runtime.install_anchor),
        "helperUrl": helper_path.as_uri(),
        "rootPath": str(root_path),
        "sourceHashes": source_hashes,
        "instructionGuards": instruction_guards,
        "requiredSkills": [
            {"name": result.payload.name, "description": result.payload.description}
            for result in skill_results.values()
            if result.payload is not None
        ],
        "composition": {
            "profileDir": str(profile_dir),
            "home": str(home),
            "cwd": str(cwd),
            "domainLayers": [],
            "rows": list(config.rows),
            "cliPatchFiles": [str(path) for path in arguments.patch_files],
            "customSkillDirs": list(config.custom_skill_dirs),
            "telemetryDisabledEnv": process_env.get("DSH_TELEMETRY_DISABLED"),
        },
        "inspected": inspected,
    }
    # Preserve per-origin domain layers, rather than flattening namespace evidence.
    composition = request["composition"]
    assert isinstance(composition, dict)
    composition["domainLayers"] = [
        {
            "origin": item["origin"],
            "element": item["element"],
            "patches": validate_native_fragment(
                item["value"],
                source=Path(str(item["source"])),
                binding_root=Path(str(item["bindingRoot"])),
            ),
        }
        for item in config.sources
        if item["kind"] == "native"
    ]
    diagnostics = (
        *config.diagnostics,
        *config.permissions.diagnostics,
        *hooks.diagnostics,
        *(item for plan in installs for item in plan.diagnostics),
    )
    return DshLaunchPlan(
        runtime,
        cwd,
        arguments,
        config,
        tuple(installs),
        request,
        tuple(diagnostics),
        tuple(local_inputs),
    )


def execute_dsh_launch(plan: DshLaunchPlan, *, process_env: Mapping[str, str]) -> int:
    """Materialize guarded outputs and run the installed native host shell-free."""
    for local in plan.local_inputs:
        verify_dsh_local_inputs(local)
    for install in plan.installs:
        _refuse_retired_discovery(install)
    for install in plan.installs:
        apply_dsh_install(install)
    request = dict(plan.request)
    request.pop("inspected", None)
    # Final entries are inspected again by the actual host; origin base remains
    # the original profile even though the root's bytes are ai-dotfiles-owned.
    host_url = (plan.config.layout.owned_dir / "launch.mjs").as_uri()
    # Root config is prepared by the host using its freshly inspected rows.
    # It is already owned/preflighted; the process writes no profile files.
    try:
        # NamedTemporaryFile creates mode 0600; keep request values out of argv
        # and preserve stdin for the native headless "-" application argument.
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix="ai-dotfiles-dsh-", suffix=".json"
        ) as transport:
            json.dump(request, transport, allow_nan=False)
            transport.flush()
            bootstrap = (
                "const {readFileSync} = await import('node:fs'); "
                f"const host = await import({json.dumps(host_url)}); "
                "await host.runManaged(JSON.parse(readFileSync("
                f"{json.dumps(transport.name)}, 'utf8')), process.argv.slice(1));"
            )
            result = subprocess.run(
                [
                    str(plan.runtime.node),
                    "--input-type=module",
                    "-e",
                    bootstrap,
                    "--",
                    *plan.arguments.app_args,
                ],
                shell=False,
                cwd=plan.cwd,
                env=plan.config.child_environment(process_env),
                check=False,
            )
    except OSError as exc:
        raise ExternalError(f"Managed DSH host could not start: {exc}") from exc
    return result.returncode if result.returncode >= 0 else 128 - result.returncode
