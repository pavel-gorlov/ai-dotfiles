// Import-free post-Loader boundary for @deepseek-ai/dsh 0.2.0-rc.2.
export const name = 'ai-dotfiles-audit';
export const inject = ['loader'];
export const schemaVersion = 1;
export const generator = 1;

// Public Cordis FiberState constants in the pinned release (const enum).
const PENDING = 0;
const ACTIVE = 2;
const FAILED = 3;
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const keys = ['schemaVersion', 'generator', 'requiredIds', 'requiredTools', 'requiredServices', 'requiredSubagentProviders'];

export function validateAuditConfig(config) {
  if (!record(config) || Object.keys(config).length !== keys.length || keys.some(key => !Object.hasOwn(config, key))
    || config.schemaVersion !== schemaVersion || config.generator !== generator) {
    throw new Error('ai-dotfiles DSH audit: malformed/unknown audit schema or generator');
  }
  for (const key of keys.slice(2)) {
    if (!Array.isArray(config[key]) || config[key].some(value => typeof value !== 'string' || value.length === 0)
      || new Set(config[key]).size !== config[key].length) throw new Error(`ai-dotfiles DSH audit: invalid ${key}`);
  }
  return JSON.parse(JSON.stringify(config));
}

function errorText(error, seen = new Set()) {
  if (seen.has(error)) return '(cyclic cause)';
  seen.add(error);
  const message = error instanceof Error ? error.message : String(error);
  const cause = error instanceof Error && error.cause !== undefined ? `; ${errorText(error.cause, seen)}` : '';
  return message + cause;
}

function sameFilter(actual, expected) {
  if (expected === null) return actual === undefined;
  if (!record(actual)) return false;
  return ['allow', 'deny'].every(key => {
    if (!Object.hasOwn(expected, key)) return actual[key] === undefined;
    return Array.isArray(actual[key]) && JSON.stringify([...actual[key]].sort()) === JSON.stringify([...expected[key]].sort());
  });
}

function sameOptions(actual, expected) {
  if (expected === null) return actual === undefined;
  if (!record(actual)) return false;
  // Schemastery may retain omitted keys as undefined. JSON omits them, while
  // explicit route fields remain exact and key insertion order is irrelevant.
  const entries = value => Object.entries(value).filter(([, item]) => item !== undefined)
    .sort(([left], [right]) => left < right ? -1 : left > right ? 1 : 0);
  return JSON.stringify(entries(actual)) === JSON.stringify(entries(expected));
}

export class DshReadinessError extends Error {
  constructor(report) {
    super('ai-dotfiles DSH activation failed:\n' + report.failures.map(item => `${item.id}: ${item.reason}`).join('\n'));
    this.name = 'DshReadinessError';
    this.report = report;
  }
}

/** Await from the HOST after boot, never from this plugin's pending apply. */
export async function auditReady(ctx, input, { scope } = {}) {
  const config = validateAuditConfig(input);
  const failures = [];
  const diagnostics = [];
  const add = (id, code, reason) => failures.push({ id, code, reason });
  const loader = ctx.get('loader');
  if (loader === undefined) {
    add('loader', 'MISSING_SERVICE', 'native Loader is absent; activate the required provider');
  } else {
    await loader.await();
    // Cordis traces services per lookup; proxy identity is not lifecycle state.
    if (ctx.get('loader') === undefined) add('loader', 'INACTIVE_SERVICE', 'Loader was disposed during startup');
    const entries = [...loader.entries()];
    const matches = id => entries.filter(entry => entry.id === id || entry.options.id === id);
    for (const id of config.requiredIds) {
      const found = matches(id);
      if (found.length === 0) add(id, 'MISSING_ROW', 'required managed row is missing; reconcile its contribution');
      if (found.length > 1) add(id, 'AMBIGUOUS_ROW', 'required id matches multiple native rows; refuse the collision');
    }
    // Native startup ignores disabled and missing required ids and may only warn
    // for optional failures. Managed optional failures must still be fatal;
    // foreign optional failures are reported without changing native policy.
    for (const entry of entries) {
      const required = config.requiredIds.some(id => entry.id === id || entry.options.id === id)
        || ctx.get('aiDotfilesBridge')?.config.agents.some(agent => agent.rowId === entry.options.id);
      const report = (id, code, reason) => (required ? failures : diagnostics).push({ id, code, reason });
      let disabled;
      try { disabled = entry.disabled; }
      catch (error) { report(entry.id, 'DISABLED_EXPRESSION_FAILED', errorText(error)); continue; }
      if (disabled) {
        if (required) add(entry.id, 'DISABLED_ROW', 'required managed row is disabled (possibly by its parent); enable the native contribution');
        continue;
      }
      const fiber = entry.fiber;
      if (fiber === undefined) { report(entry.id, 'IMPORT_FAILED', `failed to import ${entry.options.name}; check the module/path and installed pinned runtime`); continue; }
      if (fiber.state === ACTIVE) continue;
      if (fiber.state === FAILED) {
        try { await fiber.await(); }
        catch (error) { report(entry.id, 'APPLY_FAILED', errorText(error)); continue; }
        report(entry.id, 'APPLY_FAILED', 'native plugin failed without a reported rejection');
      } else if (fiber.state === PENDING) {
        const missing = Object.keys(fiber.inject).filter(service => fiber.ctx.get(service) === undefined);
        report(entry.id, 'PENDING_SERVICE', `native plugin is pending; missing services: ${missing.join(', ') || '(service intercept/configuration unmet)'}`);
      } else report(entry.id, 'INACTIVE_ROW', `native plugin is inactive (FiberState ${fiber.state})`);
    }
  }
  const presets = ctx.get('agentPresets');
  if (presets !== undefined && scope === undefined) add('composition', 'COMPOSITION_NOT_SELECTED', 'audit of the chosen native composition is pending; the host must pass its unpublished/idle scoped Agent before starting the surface');
  const serviceFor = service => (scope?.ctx === undefined ? undefined : presets?.serviceFor(scope, service))
    ?? scope?.ctx?.get(service) ?? ctx.get(service);
  for (const service of config.requiredServices) {
    if (serviceFor(service) === undefined) add(service, 'MISSING_SERVICE', 'required native service is missing; this custom profile cannot activate the managed contributions');
  }
  const tools = serviceFor('tools');
  for (const tool of config.requiredTools) {
    if (tools?.get(tool, scope) === undefined) add(tool, 'MISSING_TOOL', 'required native capability is unavailable in the chosen composition; activate its provider (read_image also requires attachments)');
  }
  const subagents = serviceFor('subagents');
  for (const provider of config.requiredSubagentProviders) {
    const value = subagents?.getProvider(provider);
    if (value === undefined) add(provider, 'MISSING_PROVIDER', 'required native subagent provider is missing; activate the stock in-process spawn composition');
    else if (provider === 'spawn' && (value.inheritsParentContext !== false
      || ['persona', 'toolFilter', 'agentOptions', 'depthLimit'].some(key => value.capabilities[key] !== true))) {
      add(provider, 'PROVIDER_CAPABILITY', 'spawn provider lacks the required native child-composition capabilities');
    }
  }
  const bridge = ctx.get('aiDotfilesBridge');
  if (bridge === undefined || bridge.schemaVersion !== 1 || bridge.generator !== 1 || typeof bridge.verify !== 'function') {
    add('aiDotfilesBridge', 'MISSING_BRIDGE', 'the versioned literal/policy bridge did not activate');
  } else {
    // Derive required data too: a caller cannot omit a bridge filter/policy tool.
    const required = new Set(bridge.config.permissions.requiredTools);
    for (const agent of bridge.config.agents) {
      agent.requiredTools.forEach(tool => required.add(tool));
      required.add(agent.toolName);
      const matches = loader === undefined ? [] : [...loader.entries()].filter(entry => entry.options.id === agent.rowId);
      if (matches.length !== 1) add(agent.rowId, 'MANAGED_AGENT_ROW', 'expected exactly one generated native agent row');
      else {
        const value = matches[0].fiber?.config;
        if (value?.provider !== 'spawn' || value?.toolName !== agent.toolName || value?.persona !== agent.persona) {
          add(agent.rowId, 'MANAGED_AGENT_CONFIG', 'native agent provider/toolName/persona differs from the generated source');
        }
        if (!sameFilter(value?.toolFilter, agent.toolFilter)) add(agent.rowId, 'MANAGED_AGENT_FILTER', 'native allow/deny filter differs from the exact source; refuse an unrestricted/widened child');
        if (!sameOptions(value?.agentOptions, agent.agentOptions)) add(agent.rowId, 'MANAGED_AGENT_OPTIONS', 'native child route/options differ from the generated partial inheritance contract');
      }
    }
    for (const tool of required) {
      if (tools?.get(tool, scope) === undefined && !config.requiredTools.includes(tool)) add(tool, 'MISSING_TOOL', 'bridge required native capability is unavailable; reconcile the profile/providers');
    }
    const scopes = scope === undefined ? [undefined, ...(ctx.get('agents')?.list() ?? [])] : [scope];
    for (const scope of scopes) {
      try { await bridge.verify(scope); }
      catch (error) { add(scope?.id ?? 'systemPrompt', 'PROMPT_UNSUPPORTED', errorText(error)); }
    }
  }
  const report = { schemaVersion, generator, ready: failures.length === 0,
    composition: presets !== undefined && scope === undefined ? 'pending' : scope === undefined ? 'global' : 'selected',
    failures, diagnostics };
  if (!report.ready) throw new DshReadinessError(report);
  return report;
}

/** Expose a synchronous native service; the launcher awaits run AFTER boot. */
export function apply(ctx, input) {
  const config = validateAuditConfig(input);
  ctx.provide('aiDotfilesAudit', { schemaVersion, generator, config, run: options => auditReady(ctx, config, options) });
}
