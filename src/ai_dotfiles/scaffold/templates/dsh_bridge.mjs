// Pinned @deepseek-ai/dsh 0.2.0-rc.2 public Cordis/prompt/tools contract.
// No imports: generated file-URL plugins resolve no user npm dependencies.
export const name = 'ai-dotfiles-bridge';
export const inject = ['systemPrompt', 'tools'];
export const schemaVersion = 1;
export const generator = 1;

const PERSONA = 'deployment:persona-prefix';
const MARKER = 'ai-dotfiles:literal-bridge';
const ROSTER = 'ai-dotfiles:agent-descriptions';
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const fail = reason => { throw new Error(`ai-dotfiles DSH bridge: ${reason}`); };
const string = (value, field) => {
  if (typeof value !== 'string' || value.length === 0) fail(`${field} needs a non-empty string`);
};
const strings = (value, field) => {
  if (!Array.isArray(value)) fail(`${field} needs a string array`);
  value.forEach(item => string(item, field));
  if (new Set(value).size !== value.length) fail(`${field} has duplicate names`);
};
const equalNames = (left, right) => JSON.stringify([...left].sort()) === JSON.stringify([...right].sort());

function fields(value, keys, label) {
  if (!record(value) || !equalNames(Object.keys(value), keys)) fail(`malformed ${label} fields`);
}

function provenance(value, label) {
  fields(value, ['source', 'origin', 'element', 'source_sha256', 'generator'], label);
  for (const key of ['source', 'origin', 'element']) string(value[key], `${label}.${key}`);
  if (!/^[a-f0-9]{64}$/.test(value.source_sha256) || !Number.isSafeInteger(value.generator) || value.generator < 1) {
    fail(`malformed ${label} source hash/generator`);
  }
}

function policy(value) {
  fields(value, ['schemaVersion', 'generator', 'deny', 'ask', 'requiredTools', 'blocked', 'contributions', 'diagnostics'], 'permissions');
  if (value.schemaVersion !== 1 || value.generator !== 1) fail('unknown permission schema/generator');
  if (value.blocked !== false) fail('blocked or malformed permission policy; correct the original source');
  for (const key of ['deny', 'ask', 'requiredTools']) strings(value[key], `permissions.${key}`);
  if (!Array.isArray(value.contributions) || !Array.isArray(value.diagnostics)) fail('malformed permission source records');
  const translated = { deny: new Set(), ask: new Set() };
  for (const item of value.contributions) {
    fields(item, ['decision', 'entry', 'nativeTools', 'field', 'provenance'], 'permission contribution');
    if (item.decision !== 'deny' && item.decision !== 'ask') fail('unknown permission decision');
    string(item.entry, 'permission entry');
    string(item.field, 'permission field');
    strings(item.nativeTools, 'permission nativeTools');
    if (item.nativeTools.length === 0) fail('empty translated permission contribution');
    provenance(item.provenance, 'permission provenance');
    item.nativeTools.forEach(tool => translated[item.decision].add(tool));
  }
  for (const item of value.diagnostics) {
    fields(item, ['value', 'code', 'origin', 'element', 'field', 'reason', 'blocking', 'provenance'], 'permission diagnostic');
    for (const key of ['code', 'origin', 'element', 'field', 'reason']) string(item[key], `permission diagnostic ${key}`);
    provenance(item.provenance, 'diagnostic provenance');
    if (item.blocking !== false) fail(`blocking permission diagnostic: ${item.origin} ${item.field}: ${item.reason}`);
  }
  for (const decision of ['deny', 'ask']) {
    if (!equalNames(value[decision], translated[decision])) fail(`permission ${decision} differs from source contributions`);
  }
  if (!equalNames(value.requiredTools, new Set([...value.deny, ...value.ask]))) fail('permission requiredTools is incomplete');
}

/** Reject malformed/unknown/blocked data; never substitute an empty policy. */
export function validateBridgeConfig(config) {
  fields(config, ['schemaVersion', 'generator', 'agents', 'rules', 'permissions'], 'bridge config');
  if (config.schemaVersion !== schemaVersion || config.generator !== generator) fail('unknown bridge schema/generator');
  if (!Array.isArray(config.agents) || !Array.isArray(config.rules)) fail('agents/rules need arrays');
  const agentNames = new Set();
  for (const agent of config.agents) {
    fields(agent, ['name', 'toolName', 'description', 'persona', 'sourceModel', 'provenance', 'rowId', 'requiredTools', 'toolFilter', 'agentOptions'], 'agent');
    string(agent.name, 'agent name');
    if (!/^[A-Za-z0-9_][A-Za-z0-9_-]*$/.test(agent.name) || agentNames.has(agent.name)) fail('invalid/duplicate managed agent name');
    agentNames.add(agent.name);
    if (agent.toolName !== `ai_dotfiles_agent_${agent.name}` || agent.rowId !== `ai-dotfiles-agent-${agent.name}`) fail('agent native namespace mismatch');
    string(agent.description, 'agent description');
    if (typeof agent.persona !== 'string') fail('agent persona needs literal text');
    if (agent.sourceModel !== null && typeof agent.sourceModel !== 'string') fail('invalid agent sourceModel');
    strings(agent.requiredTools, 'agent requiredTools');
    if (agent.toolFilter !== null) {
      if (!record(agent.toolFilter) || Object.keys(agent.toolFilter).length === 0
        || Object.keys(agent.toolFilter).some(key => key !== 'allow' && key !== 'deny')) fail('invalid agent toolFilter');
      for (const value of Object.values(agent.toolFilter)) strings(value, 'agent toolFilter');
    }
    const filterNames = new Set([...(agent.toolFilter?.allow ?? []), ...(agent.toolFilter?.deny ?? [])]);
    if (!equalNames(agent.requiredTools, filterNames)) fail('agent requiredTools differs from exact filter');
    if (agent.agentOptions !== null) {
      if (!record(agent.agentOptions) || Object.keys(agent.agentOptions).some(key => !['provider', 'model', 'reasoningEffort', 'maxTokens'].includes(key))) fail('invalid agentOptions');
      for (const [key, value] of Object.entries(agent.agentOptions)) {
        if (key === 'maxTokens') {
          if (!Number.isSafeInteger(value) || value < 1) fail('invalid native maxTokens');
        } else string(value, `agentOptions.${key}`);
      }
    }
    provenance(agent.provenance, 'agent provenance');
  }
  const ruleNames = new Set();
  for (const rule of config.rules) {
    fields(rule, ['name', 'body', 'description', 'provenance'], 'literal rule');
    string(rule.name, 'rule name');
    if (ruleNames.has(rule.name)) fail('duplicate literal rule name');
    ruleNames.add(rule.name);
    if (typeof rule.body !== 'string' || (rule.description !== null && typeof rule.description !== 'string')) fail('invalid literal rule text');
    provenance(rule.provenance, 'rule provenance');
  }
  policy(config.permissions);
  // Cordis config and its caller remain untouched. JSON parsing errors propagate.
  return JSON.parse(JSON.stringify(config));
}

const ruleSection = rule => `ai-dotfiles:rule:${rule.name}`;
function roster(ctx, config, scope) {
  if (ctx.tools.get('run_code', scope) === undefined) return '';
  const visible = config.agents.filter(agent => ctx.tools.get(agent.toolName, scope) !== undefined);
  return visible.length === 0 ? '' : 'Available ai-dotfiles agents:\n\n'
    + visible.map(agent => `${agent.toolName}\n${agent.description}`).join('\n\n');
}

/** Check the FINAL native result; complete sections are restored after waterfall. */
export function verifyBridgeAssembly(ctx, config, assembly, scope) {
  const section = name => assembly.sections.find(item => item.name === name);
  if (section(MARKER)?.text !== '' || section(MARKER)?.interpolate !== false) {
    fail('literal bridge sections were discarded; complete persona mode is unsupported (use a composable native persona)');
  }
  for (const rule of config.rules) {
    const actual = section(ruleSection(rule));
    if (actual?.text !== rule.body || actual?.interpolate !== false) fail(`literal rule ${rule.name} was removed/changed by the native composition`);
  }
  const prefix = section(PERSONA);
  if (prefix !== undefined && config.agents.some(agent => agent.persona === prefix.text) && prefix.interpolate !== false) {
    fail('generated persona lost literal interpolation protection; complete persona mode is unsupported');
  }
  if (section(ROSTER)?.text !== roster(ctx, config, scope) || section(ROSTER)?.interpolate !== false) fail('literal agent-description roster was removed/changed');
  for (const tool of assembly.tools) {
    const agent = config.agents.find(item => item.toolName === tool.name);
    if (agent !== undefined && tool.description !== agent.description) fail(`native description changed for ${tool.name}`);
  }
  return assembly;
}

/** Preserve stock spawn, scope/filter inheritance and native approval/sandbox. */
export function apply(ctx, input) {
  const config = validateBridgeConfig(input);
  const personas = new Set(config.agents.map(agent => agent.persona));
  const agents = new Map(config.agents.map(agent => [agent.toolName, agent]));
  ctx.systemPrompt.section({ name: MARKER, order: 0, text: '', interpolate: false });
  for (const rule of config.rules) {
    ctx.systemPrompt.section({ name: ruleSection(rule), order: 700, text: rule.body, interpolate: false });
  }
  ctx.systemPrompt.section({
    name: ROSTER, order: 4990, interpolate: false,
    text: context => roster(ctx, config, context.scope),
  });
  ctx.on('system-prompt/assemble', async (_assembly, _context, next) => {
    const assembly = await next();
    return {
      ...assembly,
      sections: assembly.sections.map(section => section.name === PERSONA && personas.has(section.text)
        ? { ...section, interpolate: false } : section),
      tools: assembly.tools.map(tool => agents.has(tool.name)
        ? { ...tool, description: agents.get(tool.name).description } : tool),
    };
  }, { prepend: true });
  const denied = new Set(config.permissions.deny);
  const asked = new Set(config.permissions.ask);
  ctx.tools.guard(exec => denied.has(exec.name)
    ? `ai-dotfiles permissions deny tool "${exec.name}"` : undefined);
  ctx.on('tools/pre-execute', async (exec, next) => {
    const downstream = await next();
    if (downstream.kind !== 'allow') return downstream;
    if (denied.has(exec.name)) return { kind: 'deny', reason: `ai-dotfiles permissions deny tool "${exec.name}"` };
    return asked.has(exec.name) ? { kind: 'ask', reason: `ai-dotfiles permissions require approval for tool "${exec.name}"` } : downstream;
  }, { prepend: true });
  const verify = async scope => verifyBridgeAssembly(ctx, config,
    await ctx.systemPrompt.assemble({ scope, ...(scope?.session === undefined ? {} : { agent: scope }) }), scope);
  ctx.provide('aiDotfilesBridge', { schemaVersion, generator, config, verify });
  // Agent creation is serial and rollback-covered. Do not wait for Loader here:
  // a declarative agent may itself be an unfinished Loader task.
  ctx.on('agent/created', async ({ agent }) => { await verify(agent); });
  ctx.on('agent/pre-step', async ({ agent }, next) => {
    await verify(agent);
    return next();
  }, { prepend: true });
}
