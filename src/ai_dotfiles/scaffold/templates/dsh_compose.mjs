// Read-only native composition and the managed host's explicit readiness boundary.
// Domain JSON never evaluates code. User expressions remain native inert nodes;
// identity/namespace conflicts which require evaluation are refused.
import { createRequire } from 'node:module';
import { readFileSync, realpathSync } from 'node:fs';
import { extname, isAbsolute } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const VERSION = '0.2.0-rc.2';
const SCHEMA = 1;
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const expression = value => record(value) && Object.hasOwn(value, '__jsExpr');
const diagnostic = (code, origin, element, field, reason, blocking = true) => ({ code, origin, element, field, reason, blocking });
function refuse(code, origin, element, field, reason) {
  const error = new Error(reason);
  error.diagnostic = diagnostic(code, origin, element, field, reason);
  throw error;
}
function exactKeys(value, allowed, required, label) {
  if (!record(value) || Object.keys(value).some(key => !allowed.includes(key))
    || required.some(key => !Object.hasOwn(value, key))) throw new Error(`Invalid ${label} schema`);
}
function absolute(value, label) {
  if (typeof value !== 'string' || !isAbsolute(value) || value.includes('\0')) throw new Error(`${label} must be an absolute path`);
  return value;
}
function jsonData(value, label, seen = new Set(), forbidExpressions = false) {
  if (value === null || ['string', 'boolean'].includes(typeof value)) return;
  if (typeof value === 'number' && Number.isFinite(value)) return;
  if (typeof value !== 'object' || seen.has(value)) throw new Error(`Invalid JSON data in ${label}`);
  seen.add(value);
  if (Array.isArray(value)) value.forEach((child, index) => jsonData(child, `${label}[${index}]`, seen, forbidExpressions));
  else for (const [key, child] of Object.entries(value)) {
    if (forbidExpressions && key === '__jsExpr') {
      const error = new Error(`Executable/unsafe marker ${key} is forbidden in ${label}`);
      error.field = `${label}.${key}`;
      throw error;
    }
    jsonData(child, `${label}.${key}`, seen, forbidExpressions);
  }
  seen.delete(value);
}

/** Resolve actual published companions from the verified CLI installation. */
export async function loadNative(runtimeAnchor) {
  absolute(runtimeAnchor, 'runtimeAnchor');
  const metadata = JSON.parse(readFileSync(runtimeAnchor, 'utf8'));
  if (metadata.name !== '@deepseek-ai/dsh' || metadata.version !== VERSION || metadata.bin?.dsh !== 'lib/bin.js') throw new Error('Expected official @deepseek-ai/dsh 0.2.0-rc.2');
  const require = createRequire(runtimeAnchor);
  const packages = {};
  for (const name of ['dsh-app-boot', 'dsh-skill-filesystem', 'dsh-mcp-client', 'dsh-scope', 'dsh-agent-preset-registry', 'cordis-plugin-include']) {
    const anchor = require.resolve(`@deepseek-ai/${name}/package.json`);
    const actual = JSON.parse(readFileSync(anchor, 'utf8'));
    const version = name === 'cordis-plugin-include' ? '1.0.9' : VERSION;
    if (actual.name !== `@deepseek-ai/${name}` || actual.version !== version) throw new Error(`Native ${name} must be pinned to ${version}`);
    packages[name] = anchor;
  }
  const boot = await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-app-boot')).href);
  // The filesystem provider parses frontmatter using THIS package dependency.
  const yaml = await import(pathToFileURL(createRequire(packages['dsh-skill-filesystem']).resolve('yaml')).href);
  const scope = await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-scope')).href);
  const mcp = await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-mcp-client')).href);
  const include = await import(pathToFileURL(require.resolve('@deepseek-ai/cordis-plugin-include')).href);
  const includeYaml = await import(pathToFileURL(createRequire(packages['cordis-plugin-include']).resolve('js-yaml')).href);
  return { boot, yaml, scope, mcp, include, includeYaml, require, runtimeAnchor };
}

/** Match the native provider's delimiter/parser contract for all source types. */
export function parseFrontmatter(native, paths) {
  if (!Array.isArray(paths) || paths.some(path => typeof path !== 'string')) throw new Error('paths must be an array of paths');
  const frontmatter = {};
  for (const path of paths) {
    absolute(path, 'frontmatter path');
    const raw = readFileSync(path, 'utf8');
    const lines = raw.split('\n');
    if (lines[0].replace(/\r$/, '') !== '---') refuse('FRONTMATTER_INVALID', path, path, 'frontmatter', 'missing native YAML frontmatter delimiter');
    const closing = lines.findIndex((line, index) => index > 0 && line.replace(/\r$/, '') === '---');
    if (closing < 0) refuse('FRONTMATTER_INVALID', path, path, 'frontmatter', 'missing closing native YAML frontmatter delimiter');
    let data;
    try { data = native.yaml.parse(lines.slice(1, closing).join('\n')); }
    catch (error) { refuse('FRONTMATTER_INVALID', path, path, 'frontmatter', `native YAML parser: ${String(error)}`); }
    if (!record(data)) refuse('FRONTMATTER_INVALID', path, path, 'frontmatter', 'native YAML frontmatter must be a mapping');
    jsonData(data, path);
    frontmatter[path] = data;
  }
  return { frontmatter };
}

function entriesIn(rows, origin, { presets = false, includes, prefix = 'entries', parent, locations = includes?.locations } = {}) {
  if (!Array.isArray(rows)) refuse('DYNAMIC_COMPOSITION', origin, origin, 'entries', 'entry tree must be a literal array; expression target cannot be proved');
  const all = [];
  for (const [index, row] of rows.entries()) {
    const field = `${prefix}[${index}]`;
    if (!record(row) || Object.hasOwn(row, '__proto__')) refuse('DYNAMIC_COMPOSITION', origin, origin, field, 'entry must be literal native metadata');
    for (const key of ['id', 'name', 'group']) {
      if (key === 'name' ? typeof row.name !== 'string' : key === 'id' ? row.id !== undefined && typeof row.id !== 'string' : row.group !== undefined && row.group !== null && typeof row.group !== 'boolean') refuse('DYNAMIC_COMPOSITION', origin, typeof row.id === 'string' ? row.id : origin, `${field}.${key}`, `entry ${key} must be literal native metadata`);
    }
    locations?.set(row, { origin, field, parent });
    all.push(row);
    if (row.group === true && row.name !== '@deepseek-ai/dsh-agent-preset') all.push(...entriesIn(row.config, origin, { presets, includes, prefix: `${field}.config`, parent: row, locations }));
    if (presets && row.name === '@deepseek-ai/dsh-agent-preset') {
      if (!record(row.config) || typeof row.config.id !== 'string') refuse('DYNAMIC_COMPOSITION', origin, row.id ?? row.name, 'config.id', 'preset identity is not statically provable');
      if (presets === true || presets === row.config.id) all.push(...entriesIn(row.config.plugins, origin, { presets, includes, prefix: `${field}.config.plugins`, parent: row, locations }));
    }
    if (includes && ['cordis:include', '@deepseek-ai/cordis-plugin-include'].includes(row.name)) {
      const config = row.config;
      if (!record(config) || expression(config) || typeof config.path !== 'string') refuse('DYNAMIC_CONFLICT', origin, row.id ?? row.name, 'config.path', 'include path/config is not statically provable without native expression evaluation');
      let filename;
      try { filename = fileURLToPath(new URL(config.path, includes.baseUrl)); }
      catch (error) { refuse('INCLUDE_UNPROVABLE', origin, row.id ?? row.name, 'config.path', String(error)); }
      const extension = extname(filename);
      if (!['.json', '.yml', '.yaml'].includes(extension)) refuse('INCLUDE_UNPROVABLE', filename, row.id ?? row.name, 'config.path', 'only the native JSON/YAML entry-list include can be inspected without execution');
      let data, canonical;
      try {
        canonical = realpathSync(filename);
        const content = readFileSync(filename, 'utf8');
        data = extension === '.json' ? JSON.parse(content) : includes.native.includeYaml.load(content, { schema: includes.native.include.entryListSchema });
      } catch (error) {
        refuse(error.code === 'ENOENT' && config.initial !== undefined ? 'PROFILE_WRITE_REQUIRED' : 'INCLUDE_UNAVAILABLE', filename, row.id ?? row.name, 'config.path', `native include cannot be read safely; an absent initial file would be written at activation: ${String(error)}`);
      }
      if (includes.ancestors.has(canonical)) refuse('INCLUDE_CYCLE', filename, row.id ?? row.name, 'config.path', 'native include cycle prevents namespace proof');
      try { jsonData(data, 'entries', new Set(), includes.forbidExpressions === true); }
      catch (error) { refuse('INCLUDE_DATA_INVALID', filename, row.id ?? row.name, error.field ?? 'entries', String(error)); }
      validatePatches(config.patches ?? [], filename, includes.forbidExpressions === true);
      const children = includes.native.include.applyEntryPatches(data, config.patches, (message, ...args) => refuse('PATCH_UNMATCHED', filename, row.id ?? row.name, 'config.patches', `${message} ${args.join(' ')}`));
      includes.ancestors.add(canonical);
      try {
        all.push(...entriesIn(children, filename, { presets, includes: { ...includes, baseUrl: new URL('.', pathToFileURL(filename)).href }, parent: row, locations }));
      } finally { includes.ancestors.delete(canonical); }
    }
  }
  return all;
}
function namespaces(rows, origin, { includes, flat = false } = {}) {
  const found = { id: new Map(), toolName: new Map(), serverName: new Map() };
  for (const row of flat ? rows : entriesIn(rows, origin, { includes })) {
    const add = (field, value) => {
      if (value === undefined) return;
      if (typeof value !== 'string') refuse('DYNAMIC_CONFLICT', origin, row.id ?? row.name, `config.${field}`, `${field} conflict cannot be proved without evaluating a native expression`);
      found[field].set(value, row);
    };
    if (row.id !== undefined) add('id', row.id);
    // Unknown plugins may declare these native public identities too.
    if (expression(row.config)) refuse('DYNAMIC_CONFLICT', origin, row.id ?? row.name, 'config', 'whole config expression may hide tool/server identities');
    if (record(row.config)) {
      add('toolName', row.config.toolName);
      add('serverName', row.config.serverName);
    }
  }
  return found;
}
function assertNoCollision(user, managed, origin, includes) {
  const existing = namespaces(user, origin, { includes });
  const proposed = namespaces(managed, 'managed', { includes: includes && { ...includes, forbidExpressions: true } });
  for (const field of ['id', 'toolName', 'serverName']) {
    for (const [name] of proposed[field]) if (existing[field].has(name)) refuse('USER_COLLISION', origin, name, field, `foreign user ${field} collides with managed logical name ${name}`);
  }

}
function nativeMcpValidation(native, row) {
  try { native.mcp.Config(row.config); }
  catch (error) { refuse('NATIVE_CONFIG_INVALID', 'managed', row.id ?? row.name, 'config', `native MCP schema: ${String(error)}`); }
}
function selectionOf(rows, selectedPreset, origin) {
  const all = entriesIn(rows, origin);
  const presets = all.filter(row => row.name === '@deepseek-ai/dsh-agent-preset');
  if (!presets.length) {
    if (selectedPreset !== undefined) refuse('COMPOSITION_NOT_SELECTED', origin, selectedPreset, 'preset', 'requested preset is absent from this native profile');
    return { kind: 'global' };
  }
  let id = selectedPreset;
  if (id === undefined) {
    const registries = all.filter(row => row.name === '@deepseek-ai/dsh-agent-preset-registry');
    if (registries.length !== 1 || typeof registries[0].config?.default !== 'string') refuse('COMPOSITION_NOT_SELECTED', origin, origin, 'preset', 'native default preset is not statically provable; the host must choose a native composition');
    if (registries[0].config.selectedDefault !== undefined && typeof registries[0].config.selectedDefault !== 'string') refuse('COMPOSITION_NOT_SELECTED', origin, origin, 'selectedDefault', 'volatile native preset selection is not statically provable');
    id = registries[0].config.selectedDefault ?? registries[0].config.default;
  }
  const matches = presets.filter(row => row.config?.id === id);
  if (matches.length !== 1 || typeof matches[0].id !== 'string') refuse('COMPOSITION_NOT_SELECTED', origin, id, 'preset', 'selected native preset must have one unambiguous literal row id');
  return { kind: 'preset', id, entryId: matches[0].id };
}
function validatePatches(patches, origin, managed) {
  if (!Array.isArray(patches)) throw new Error('patches must be a top-level native array');
  for (const [index, patch] of patches.entries()) {
    if (!record(patch) || expression(patch) || Object.hasOwn(patch, '__proto__')) refuse('PATCH_INVALID', origin, origin, `patches[${index}]`, 'native patch must be a literal mapping');
    if (managed) jsonData(patch, origin, new Set(), true);
    if (patch.id !== undefined && (typeof patch.id !== 'string' || !patch.id)) refuse('PATCH_INVALID', origin, origin, `patches[${index}].id`, 'native patch target id must be a nonempty literal string');
    if (patch.name !== undefined && typeof patch.name !== 'string') refuse('PATCH_INVALID', origin, origin, `patches[${index}].name`, 'native patch name assertion must be literal');
    if (patch.insert !== undefined) entriesIn(patch.insert, origin, { presets: true });
    else if (!patch.id) refuse('PATCH_INVALID', origin, origin, `patches[${index}].id`, 'non-insert native patch requires an id');
  }
}

/** Resolve managed native names before insertion; retain source layers separately. */
function mergeDomainLayers(layers, locations) {
  if (!Array.isArray(layers)) throw new Error('domainLayers must be an array');
  for (const layer of layers) {
    exactKeys(layer, ['origin', 'element', 'patches'], ['origin', 'element', 'patches'], 'domain layer');
    validatePatches(layer.patches, `${layer.origin} ${layer.element}`, true);
  }
  const detached = structuredClone(layers);
  const declarations = [];
  const byRow = new Map();
  const introduced = new Map();
  const targets = new Map();
  for (const layer of detached) {
    for (const [patchIndex, patch] of layer.patches.entries()) {
      locations.set(patch, { origin: layer.origin, element: layer.element, field: `patches[${patchIndex}]` });
      // Bind to the source-visible declaration, before a later row can reuse
      // its id. Targeted insertions and their descendants share that ownership.
      const target = introduced.get(patch.id);
      targets.set(patch, target);
      const visit = (rows, parent, prefix) => rows.forEach((row, index) => {
        const field = `${prefix}[${index}]`;
        const identities = [row.id && `id:${row.id}`, row.config?.toolName && `tool:${row.config.toolName}`, row.config?.serverName && `server:${row.config.serverName}`].filter(Boolean);
        const declaration = { row, parent, identities, layer, field };
        locations.set(row, { origin: layer.origin, element: layer.element, field });
        declarations.push(declaration);
        byRow.set(row, declaration);
        if (row.id) introduced.set(row.id, declaration);
        if (row.group === true && Array.isArray(row.config)) visit(row.config, declaration, `${field}.config`);
        if (row.name === '@deepseek-ai/dsh-agent-preset' && Array.isArray(row.config?.plugins)) visit(row.config.plugins, declaration, `${field}.config.plugins`);
      });
      if (patch.insert) visit(patch.insert, target, `patches[${patchIndex}].insert`);
    }
  }
  // Recompute winners after retiring an insertion's parent. A retired child
  // cannot claim a namespace and suppress another domain's surviving row.
  // Reverse source order also means a losing multi-identity row claims none.
  let surviving = new Set(declarations);
  const seen = new Set();
  let changed;
  for (let pass = 0; ; pass++) {
    const state = declarations.map(item => surviving.has(item) ? '1' : '0').join('');
    if (seen.has(state) || pass > declarations.length) {
      const item = changed ?? declarations.find(item => item.parent) ?? declarations[0];
      refuse('DOMAIN_PRECEDENCE_UNPROVABLE', item.layer.origin, item.layer.element, item.field,
        seen.has(state) ? 'native declaration precedence has an insertion/shadowing cycle; stable surviving ownership cannot be proved'
          : 'native declaration precedence cannot be proved within the bounded insertion ownership pass');
    }
    seen.add(state);
    const next = new Set();
    const claimed = new Set();
    for (let index = declarations.length - 1; index >= 0; index--) {
      const item = declarations[index];
      if (item.parent && !surviving.has(item.parent)) continue;
      if (item.identities.some(identity => claimed.has(identity))) continue;
      next.add(item);
      item.identities.forEach(identity => claimed.add(identity));
    }
    const differences = declarations.filter(item => surviving.has(item) !== next.has(item));
    if (!differences.length) break;
    changed = differences.find(item => item.parent) ?? differences[0];
    surviving = next;
  }
  const filter = rows => rows.filter(row => surviving.has(byRow.get(row))).map(row => {
    if (row.group === true && Array.isArray(row.config)) row.config = filter(row.config);
    if (row.name === '@deepseek-ai/dsh-agent-preset' && Array.isArray(row.config?.plugins)) row.config.plugins = filter(row.config.plugins);
    return row;
  });
  for (const layer of detached) {
    layer.patches = layer.patches.filter(patch => {
      const target = targets.get(patch);
      if (target && !surviving.has(target)) return false;
      if (patch.insert) patch.insert = filter(patch.insert);
      return true;
    });
  }
  return detached;
}

/** Prove final foreign namespaces against the surviving domain declarations.
 * Native ids retain declaration ownership through whole-config replacements.
 * New included descendants inherit their actual managed Include's ownership;
 * duplicate ids are refused BEFORE that ownership can hide a foreign row.
 */
function assertEffectiveDomainNamespaces(entries, chosen, selection, bindings, coreIds, overrides, includes, origin) {
  const locations = new WeakMap();
  const inspect = (rows, parent) => entriesIn(rows, origin, { includes: { ...includes, locations }, parent });
  const rootRows = inspect(entries);
  const selectedEntry = selection.kind === 'preset' ? rootRows.find(row => row.id === selection.entryId) : undefined;
  const visible = [...rootRows, ...(selectedEntry ? inspect(chosen, selectedEntry) : [])];
  const owners = new Map();
  for (const row of visible) {
    const parent = locations.get(row).parent;
    const binding = bindings.get(row.id);
    const inherited = owners.get(parent);
    // An Include's descendants live in that Include's separate native tree.
    // A foreign tree reusing a leaf id cannot inherit declaration ownership.
    owners.set(row, inherited ? binding ?? { ...inherited, inherited: true }
      : binding?.included ? undefined : binding);
  }
  const detail = (row, field) => {
    const location = locations.get(row);
    let changed, cursor = row;
    while (cursor && !changed) {
      changed = overrides.get(cursor.id);
      cursor = locations.get(cursor)?.parent;
    }
    const suffix = field === 'id' ? '.id' : `.config.${field}`;
    const override = changed ? `; effective override ${changed.origin} ${changed.element} ${changed.field}${changed.row ? suffix : field !== 'id' && Object.hasOwn(changed.config ?? {}, field) ? '.' + field : ''}` : '';
    return `${row.id ?? row.name} at ${location.origin} ${location.field}${suffix}${override}`;
  };
  const collision = (owner, managed, foreign, field, name) => {
    const suffix = owner.inherited ? ['cordis:include', '@deepseek-ai/cordis-plugin-include'].includes(owner.plugin) ? '.config.path' : owner.plugin === '@deepseek-ai/dsh-agent-preset' ? '.config.plugins' : '.config'
      : field === 'id' ? '.id' : `.config.${field}`;
    const effective = field === 'id' ? `effective conflicting rows ${detail(managed, field)} / ${detail(foreign, field)}; duplicate id prevents unique declaration ownership`
      : `effective managed ${detail(managed, field)}; effective foreign ${detail(foreign, field)}`;
    refuse('USER_COLLISION', owner.origin, owner.element, owner.field + suffix,
      `foreign effective ${field} collides with managed logical name ${name}; original managed declaration ${owner.sourceOrigin} ${owner.origin} ${owner.field}; ${effective}`);
  };
  const ids = new Map();
  for (const row of visible) {
    const earlier = ids.get(row.id);
    if (earlier && (owners.get(earlier) || owners.get(row))) {
      const owner = owners.get(earlier) ?? owners.get(row);
      collision(owner, owners.get(earlier) ? earlier : row, owners.get(earlier) ? row : earlier, 'id', row.id);
    }
    if (row.id !== undefined) ids.set(row.id, row);
  }
  const foreign = visible.filter(row => !owners.get(row) && !coreIds.has(row.id));
  const foreignNames = namespaces(foreign, 'effective foreign', { flat: true });
  for (const row of visible) {
    const owner = owners.get(row);
    if (!owner) continue;
    const ownNames = namespaces([row], `${owner.origin} ${owner.element}`, { flat: true });
    for (const field of ['id', 'toolName', 'serverName']) for (const [name] of ownNames[field]) {
      if (foreignNames[field].has(name)) collision(owner, row, foreignNames[field].get(name), field, name);
    }
  }
  return visible;
}

/** No initProfile/loadProfile/prepareProfile/runProfile/dump-config or boot here. */
export async function inspectComposition(native, request) {
  const { boot } = native;
  const profileDir = absolute(request.profileDir, 'profileDir');
  const home = absolute(request.home, 'home');
  const cwd = absolute(request.cwd, 'cwd');
  const origin = profileDir;
  let manifest;
  try { manifest = boot.readProfileManifest('ai-dotfiles', profileDir); }
  catch (error) { refuse('PROFILE_UNAVAILABLE', origin, origin, 'package.json', String(error)); }
  if ((manifest.dsh?.profile?.bundles ?? []).includes('@deepseek-ai/dsh-experimental-schedule-bundle')) refuse('PROFILE_WRITE_REQUIRED', origin, origin, 'dsh.profile.bundles', 'native loadProfileDirectory would remove a retired schedule bundle and rewrite package.json; inspection refuses user-profile repair');
  const profile = boot.loadProfileDirectory('ai-dotfiles', profileDir, native.runtimeAnchor);
  if (profile.skippedBundles.length) refuse('PROFILE_BUNDLE_UNAVAILABLE', origin, origin, 'dsh.profile.bundles', profile.skippedBundles.map(item => `${item.packageName}: ${item.reason}`).join('; '));
  const cliLayers = (request.cliPatchFiles ?? []).map(file => ({ origin: absolute(file, 'CLI overlay'), element: 'CLI', patches: boot.loadOverlayPatches('ai-dotfiles', file) }));
  const cli = cliLayers.flatMap(layer => layer.patches);
  const context = { name: profile.name, dir: profile.dir, patchPath: profile.patchPath,
    installAnchor: native.runtimeAnchor, cwd, home, startedBundles: profile.layers.map(layer => layer.packageName),
    overlays: [], telemetryDisabledEnv: request.telemetryDisabledEnv };
  const nativePatches = boot.readProfilePatches('ai-dotfiles', context, profile);
  validatePatches(nativePatches, origin, false);
  validatePatches(cli, 'CLI', false);
  const diagnostics = [];
  const warn = (source, blocking) => message => diagnostics.push(diagnostic('PATCH_UNMATCHED', source, source, 'patches', message, blocking));
  const userEntries = boot.composeEntries([nativePatches], warn(origin, false));
  const includes = { native, baseUrl: pathToFileURL(`${profileDir}/cordis.yml`).href, ancestors: new Set() };
  // Include declarations live in their own native patch index. We inspect their
  // namespaces but cannot replace an included preset through the root index.
  const visibleUser = entriesIn(userEntries, origin, { includes });
  if (visibleUser.some(row => row.name === '@deepseek-ai/dsh-agent-preset' && !entriesIn(userEntries, origin).includes(row))) refuse('INCLUDED_COMPOSITION_UNPROVABLE', origin, origin, 'preset', 'an included preset cannot receive the managed composition through the native root patch index without rewriting its user file');
  const managed = structuredClone(request.rows ?? []);
  jsonData(managed, 'managed rows', new Set(), true);
  const managedIds = new Set(entriesIn(managed, 'managed').map(row => row.id));
  const early = [];
  const domainLocations = new WeakMap();
  const layers = mergeDomainLayers(request.domainLayers ?? [{ origin: 'domain', element: 'domain', patches: request.domainPatches ?? [] }], domainLocations);
  for (const layer of layers) {
    exactKeys(layer, ['origin', 'element', 'patches'], ['origin', 'element', 'patches'], 'domain layer');
    if (typeof layer.origin !== 'string' || typeof layer.element !== 'string') throw new Error('Invalid domain layer provenance');
    const source = `${layer.origin} ${layer.element}`;
    validatePatches(layer.patches, source, true);
    for (const patch of layer.patches) {
      if (patch.insert) assertNoCollision(userEntries, patch.insert, origin, includes);
      if (!managedIds.has(patch.id) || patch.insert) early.push(patch);
    }
  }
  let afterDomains = userEntries;
  for (const layer of layers) {
    const ordinary = layer.patches.filter(patch => !managedIds.has(patch.id) || patch.insert);
    afterDomains = boot.composeEntries([[{ insert: afterDomains }, ...ordinary]], warn(`${layer.origin} ${layer.element}`, true));
  }
  const cliSelectionEntries = boot.composeEntries([nativePatches, early, cli], warn('CLI selection', false));
  const selection = selectionOf(cliSelectionEntries, request.selectedPreset, origin);
  const allUser = selection.kind === 'preset'
    ? [...afterDomains, ...entriesIn(afterDomains, origin).find(row => row.id === selection.entryId).config.plugins]
    : afterDomains;
  assertNoCollision(allUser, managed, origin, includes);
  if (selection.kind === 'preset' && entriesIn(allUser, origin, { includes }).some(row => row.id === 'ai-dotfiles-managed')) refuse('USER_COLLISION', origin, 'ai-dotfiles-managed', 'id', 'foreign user id collides with the managed preset group');
  // Native replacement of generated agent config is supported exactly. Only
  // explicit route/options may differ; persona/filter/identity stay immutable.
  let replacedManaged = managed;
  for (const layer of layers) {
    const targets = layer.patches.filter(patch => managedIds.has(patch.id) && !patch.insert);
    replacedManaged = boot.composeEntries([[{ insert: replacedManaged }, ...targets]], warn(`${layer.origin} ${layer.element}`, true));
  }
  const domainIds = [];
  const domainBindings = new Map();
  for (const layer of layers) for (const patch of layer.patches) {
    if (!patch.insert) continue;
    const locations = new WeakMap();
    const rows = entriesIn(patch.insert, `${layer.origin} ${layer.element}`, {
      // Audit/collision ownership follows root plus the chosen native tree.
      // Unselected preset plugins remain inert and their includes are not read.
      presets: selection.kind === 'preset' ? selection.id : false,
      includes: { ...includes, locations, forbidExpressions: true },
      prefix: `${domainLocations.get(patch).field}.insert`,
    });
    for (const row of rows) {
      const location = domainLocations.get(row) ?? locations.get(row);
      if (typeof row.id === 'string' && row.id) domainBindings.set(row.id, { ...location, element: layer.element, sourceOrigin: layer.origin, included: !domainLocations.has(row), plugin: row.name });
      if (row.disabled === true) continue;
      if (typeof row.id !== 'string' || !row.id) refuse('MANAGED_ID_UNPROVABLE', location.origin, layer.element, `${location.field}.id`, 'managed domain/include descendant requires a nonempty literal id for exact native readiness validation');
      domainIds.push(row.id);
    }
  }
  const auditRow = replacedManaged.find(row => row.id === 'ai-dotfiles-audit');
  if (auditRow) auditRow.config.requiredIds = [...new Set([...auditRow.config.requiredIds, ...domainIds])].sort();
  const originalAudit = managed.find(row => row.id === 'ai-dotfiles-audit');
  if (originalAudit) originalAudit.config.requiredIds = structuredClone(auditRow.config.requiredIds);
  approveManagedOverrides(managed, replacedManaged, 'domain');
  const additions = request.customSkillDirs ?? [];
  if (!Array.isArray(additions) || additions.some(value => typeof value !== 'string' || !isAbsolute(value))) throw new Error('customSkillDirs must be absolute native directory paths');
  const compositionPatches = [];
  if (selection.kind === 'preset') {
    const preset = entriesIn(afterDomains, origin).find(row => row.id === selection.entryId);
    const plugins = structuredClone(preset.config.plugins);
    mergeSkillDirs(plugins, additions, origin);
    if (replacedManaged.length) plugins.push({ id: 'ai-dotfiles-managed', name: 'cordis:group', group: true,
      isolate: { aiDotfilesBridge: true, aiDotfilesAudit: true }, config: replacedManaged });
    compositionPatches.push({ id: preset.id, config: { ...preset.config, plugins } });
  } else {
    const providers = entriesIn(afterDomains, origin).filter(row => row.name === '@deepseek-ai/dsh-skill-filesystem');
    if (additions.length) {
      if (providers.length !== 1 || !providers[0].id) refuse('SKILL_PROVIDER_UNAVAILABLE', origin, origin, 'customSkillDirs', 'one existing native filesystem provider is required; custom profiles are not repaired');
      const provider = structuredClone(providers[0]);
      mergeSkillDirs([provider], additions, origin);
      compositionPatches.push({ id: provider.id, config: provider.config });
    }
    if (replacedManaged.length) compositionPatches.push({ insert: replacedManaged });
  }
  let patches = [...nativePatches, ...early, ...compositionPatches, ...cli];
  let entries = boot.composeEntries([patches], warn('CLI', false));
  const finalSelection = selectionOf(entries, request.selectedPreset, origin);
  if (JSON.stringify(finalSelection) !== JSON.stringify(selection)) refuse('COMPOSITION_CHANGED', 'CLI', origin, 'preset', 'explicit CLI overlay changed the selected composition; inspect again with that native selection');
  const chosen = finalSelection.kind === 'preset' ? entriesIn(entries, origin).find(row => row.id === finalSelection.entryId).config.plugins : entries;
  const changedBridge = approveManagedOverrides(replacedManaged, chosen, 'CLI');
  const finalRequiredIds = new Set(entriesIn(replacedManaged, 'managed').map(row => row.id));
  const overrides = new Map();
  for (const layer of [...layers, ...cliLayers]) for (const [index, patch] of layer.patches.entries()) {
    const location = domainLocations.get(patch) ?? { origin: layer.origin, element: layer.element, field: `patches[${index}]` };
    const recordRows = (rows, prefix) => {
      const rowLocations = new WeakMap();
      for (const row of entriesIn(rows, layer.origin, { presets: true, prefix, locations: rowLocations })) {
        const at = rowLocations.get(row);
        overrides.set(row.id, { ...at, element: layer.element, row: true });
      }
    };
    if (patch.insert) recordRows(patch.insert, location.field + '.insert');
    if (patch.config !== undefined) {
      overrides.set(patch.id, { ...location, field: location.field + '.config', config: patch.config });
      if (Array.isArray(patch.config)) recordRows(patch.config, location.field + '.config');
      if (Array.isArray(patch.config?.plugins)) recordRows(patch.config.plugins, location.field + '.config.plugins');
    }
  }
  const visibleFinal = assertEffectiveDomainNamespaces(entries, chosen, finalSelection, domainBindings, finalRequiredIds, overrides, includes, origin);
  const foreignFinal = visibleFinal.filter(row => !finalRequiredIds.has(row.id));
  const foreignNames = namespaces(foreignFinal, 'CLI', { flat: true });
  const requiredNames = namespaces(replacedManaged, 'managed');
  for (const field of ['toolName', 'serverName']) for (const [name] of requiredNames[field]) if (foreignNames[field].has(name)) refuse('USER_COLLISION', 'CLI', name, field, `foreign CLI ${field} collides with managed logical name ${name}`);
  for (const row of visibleFinal) if (row.name === '@deepseek-ai/dsh-mcp-client') nativeMcpValidation(native, row);
  // Rebind bridge option evidence after an explicit native route override.
  // This does not deep-merge the replaced agent config or relax restrictions.
  if (changedBridge !== undefined) {
    if (selection.kind === 'preset') {
      const preset = entriesIn(entries, origin).find(row => row.id === selection.entryId);
      patches.push({ id: preset.id, config: structuredClone(preset.config) });
    } else patches.push({ id: changedBridge.id, config: structuredClone(changedBridge.config) });
    entries = boot.composeEntries([patches], warn('CLI', false));
  }
  return { entries, patches, selection, diagnostics, valid: !diagnostics.some(item => item.blocking),
    profile: { name: profile.name, dir: profile.dir, patchPath: profile.patchPath, startedBundles: context.startedBundles } };
}
function same(left, right) {
  if (left === right) return true;
  if (Array.isArray(left) && Array.isArray(right)) return left.length === right.length && left.every((value, index) => same(value, right[index]));
  if (!record(left) || !record(right)) return false;
  return Object.keys(left).length === Object.keys(right).length && Object.keys(left).every(key => Object.hasOwn(right, key) && same(left[key], right[key]));
}
function approveManagedOverrides(originalRows, chosen, origin) {
  const actualRows = entriesIn(chosen, origin);
  const original = entriesIn(originalRows, 'managed');
  const originalBridge = original.find(row => row.id === 'ai-dotfiles-bridge');
  const bridge = actualRows.find(row => row.id === 'ai-dotfiles-bridge');
  let changed = false;
  for (const required of original) {
    const matches = actualRows.filter(row => row.id === required.id);
    if (matches.length !== 1) refuse('MANAGED_ROW_OVERRIDDEN', origin, required.id, 'id', 'required managed row was removed or duplicated');
    const actual = matches[0];
    const before = structuredClone(required);
    const after = structuredClone(actual);
    if (required.name === '@deepseek-ai/dsh-tool-subagent') {
      const options = actual.config?.agentOptions;
      if (options !== undefined && (!record(options) || Object.entries(options).some(([key, value]) => !['provider', 'model', 'reasoningEffort', 'maxTokens'].includes(key)
        || (key === 'maxTokens' ? !Number.isSafeInteger(value) || value < 1 : typeof value !== 'string' || !value)))) refuse('NATIVE_OPTIONS_INVALID', origin, required.id, 'config.agentOptions', 'explicit native routes require literal provider/model/reasoningEffort or positive safe-integer maxTokens');
      if (record(before.config)) delete before.config.agentOptions;
      if (record(after.config)) delete after.config.agentOptions;
      if (bridge && !same(options ?? null, bridge.config.agents.find(agent => agent.rowId === required.id)?.agentOptions)) changed = true;
    }
    if (!same(before, after)) refuse('MANAGED_ROW_OVERRIDDEN', origin, required.id, 'config', 'native whole-config replacement changed/removed managed identity, literal instructions or restrictions');
  }
  if (changed && bridge && originalBridge) {
    for (const agent of bridge.config.agents) {
      const row = actualRows.find(row => row.id === agent.rowId);
      agent.agentOptions = structuredClone(row.config.agentOptions ?? null);
    }
    return bridge;
  }
}

function mergeSkillDirs(rows, additions, origin) {
  if (!additions.length) return;
  const providers = entriesIn(rows, origin).filter(row => row.name === '@deepseek-ai/dsh-skill-filesystem');
  if (providers.length !== 1) refuse('SKILL_PROVIDER_UNAVAILABLE', origin, origin, 'customSkillDirs', 'one existing filesystem provider is required in the chosen native scope');
  const provider = providers[0];
  if (provider.config !== undefined && !record(provider.config)) refuse('DYNAMIC_CONFLICT', origin, provider.id, 'config', 'provider config expression cannot be safely merged');
  const config = provider.config ?? {};
  if (config.customSkillDirs !== undefined && (!Array.isArray(config.customSkillDirs) || config.customSkillDirs.some(item => typeof item !== 'string'))) refuse('DYNAMIC_CONFLICT', origin, provider.id, 'config.customSkillDirs', 'native customSkillDirs expression cannot be safely merged');
  provider.config = { ...config, customSkillDirs: [...new Set([...(config.customSkillDirs ?? []), ...additions])] };
}

/** Bind the actual unpublished Agent setup context to the inspected native preset. */
export async function mountSelectedComposition(ctx, selection) {
  if (selection.kind === 'global') return;
  if (selection.kind !== 'preset' || typeof selection.id !== 'string') throw new Error('Invalid managed native selection');
  const presets = ctx.get('agentPresets');
  if (presets === undefined) throw new Error('Selected native preset registry is unavailable');
  return presets.mount(ctx, selection.id);
}

/** The managed host calls this AFTER Loader settlement and BEFORE surface release.
 * scope is its actual unpublished/idle Agent, never an offline fake session.
 * This function deliberately does not manufacture an Agent or commit appReady
 * unless the exact native scoped audit succeeds. Ordinary CLI runProfile does
 * not call this function; its use remains the launch host's responsibility.
 */
export async function auditBeforeReady(ctx, { selection, scope, commit }) {
  await ctx.loader.await();
  if (selection.kind === 'preset') {
    if (scope?.ctx === undefined || ctx.get('agentPresets')?.composedPreset(scope.ctx) !== selection.id) throw new Error('COMPOSITION_NOT_SELECTED: managed host has not bound its actual chosen native scope');
  }
  const audit = (scope?.ctx === undefined ? undefined : ctx.get('agentPresets')?.serviceFor(scope, 'aiDotfilesAudit'))
    ?? scope?.ctx?.get('aiDotfilesAudit') ?? ctx.get('aiDotfilesAudit');
  if (audit === undefined) throw new Error('Managed DSH audit service is missing');
  const report = await audit.run({ scope });
  if (typeof commit !== 'function') throw new Error('Managed readiness commit callback is required');
  await commit(report);
  return report;
}

/** Strict stdin/stdout JSON adapter. Importing the helper performs no request. */
export async function runRequest() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  const diagnostics = [];
  let result = {};
  let ok = false;
  try {
    const request = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    exactKeys(request, ['schemaVersion', 'operation', 'runtimeAnchor', 'paths', 'profileDir', 'home', 'cwd', 'domainPatches', 'domainLayers', 'rows', 'cliPatchFiles', 'customSkillDirs', 'selectedPreset', 'telemetryDisabledEnv'], ['schemaVersion', 'operation', 'runtimeAnchor'], 'native request');
    if (request.schemaVersion !== SCHEMA) throw new Error('Unsupported native request schema version');
    const native = await loadNative(request.runtimeAnchor);
    if (request.operation === 'frontmatter') result = parseFrontmatter(native, request.paths);
    else if (request.operation === 'compose') {
      result = await inspectComposition(native, request);
      diagnostics.push(...result.diagnostics);
      if (!result.valid) throw new Error('Managed patches have unresolved native targets');
    } else throw new Error('Unknown native operation');
    ok = true;
  } catch (error) {
    diagnostics.push(error.diagnostic ?? diagnostic('NATIVE_INSPECTION_FAILED', 'native', 'configuration', 'composition', String(error)));
  }
  process.stdout.write(JSON.stringify({ schemaVersion: SCHEMA, ok, result, diagnostics }));
}
