// Bounded native settings editor for the managed, immutable profile tree.
import { createRequire } from 'node:module';
import { readFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { isDeepStrictEqual } from 'node:util';

const require = createRequire(__RUNTIME_ANCHOR__);
const load = name => import(pathToFileURL(require.resolve(name)).href);
const { Service, resolveConfig } = await load('@deepseek-ai/cordis');
const { deepEqual, isVolatile } = await load('@deepseek-ai/cosmokit');
const { withFileLock, writeFileAtomic } = await load('@deepseek-ai/dsh-atomic-write');
const { Scalar, isMap, isSeq, parseDocument } = await load('yaml');
const yaml = (await load('js-yaml')).default;
const { entryListSchema } = await load('@deepseek-ai/cordis-plugin-include');

const record = value => value !== null && typeof value === 'object'
  && !Array.isArray(value) && !Object.hasOwn(value, '__jsExpr');

// Match Loader's conservative raw comparison: only fixed object paths beneath
// schema-declared volatile nodes may change; opaque expressions stay whole.
function equalOutsideVolatile(left, right, schema, seen = new Set()) {
  if (schema?.meta?.volatile) return true;
  if (schema?.type !== 'object' || !schema.dict || seen.has(schema))
    return isDeepStrictEqual(left, right);
  left ??= schema.meta.default;
  right ??= schema.meta.default;
  if (!record(left) || !record(right)) return isDeepStrictEqual(left, right);
  seen.add(schema);
  try {
    return Object.keys({ ...left, ...right }).every(key =>
      equalOutsideVolatile(left[key], right[key], schema.dict[key], seen));
  } finally { seen.delete(schema); }
}

function plain(value) {
  if (isVolatile(value)) return plain(value.get());
  if (Array.isArray(value)) return value.map(plain);
  if (value !== null && typeof value === 'object')
    return Object.fromEntries(Object.entries(value).map(([key, child]) => [key, plain(child)]));
  return value;
}

function expressionNode(document, value) {
  if (value !== null && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).length === 1 && typeof value.__jsExpr === 'string') {
    const node = new Scalar(value.__jsExpr);
    node.tag = 'tag:yaml.org,2002:js';
    return node;
  }
  const node = document.createNode(value);
  if (isMap(node)) for (const pair of node.items)
    pair.value = expressionNode(document, value[pair.key.value]);
  else if (isSeq(node)) node.items = value.map(child => expressionNode(document, child));
  return node;
}

// Update changed values only, retaining comments and !!js nodes everywhere
// else, including the ordinary fields inside this entry's config.
function editValues(document, path, before, next) {
  if (isDeepStrictEqual(before, next)) return;
  const node = document.getIn(path, true);
  if (isMap(node) && record(before) && record(next)) {
    for (const key of Object.keys({ ...before, ...next })) {
      if (!Object.hasOwn(next, key)) document.deleteIn([...path, key]);
      else editValues(document, [...path, key], before[key], next[key]);
    }
  } else document.setIn(path, expressionNode(document, next));
}

function editDocument(before, entry, next, inherited) {
  const document = parseDocument(before, { customTags: [{
    tag: 'tag:yaml.org,2002:js', resolve: value => value,
  }] });
  if (document.errors[0]) throw document.errors[0];
  if (!isSeq(document.contents)) throw new Error('Profile patch must be a YAML sequence');
  const id = entry.options.id;
  const index = document.contents.items.findLastIndex((node, index) =>
    isMap(node) && document.getIn([index, 'id']) === id && !node.has('insert')
    && (!node.has('name') || document.getIn([index, 'name']) === entry.options.name));
  const stored = index < 0 ? {} :
    yaml.load(before, { schema: entryListSchema })[index].config ?? {};
  if (isDeepStrictEqual(next, inherited)) {
    for (let index = document.contents.items.length - 1; index >= 0; index--) {
      const node = document.contents.items[index];
      if (!isMap(node) || document.getIn([index, 'id']) !== id || node.has('insert')) continue;
      node.delete('config');
      if (node.items.length === Number(node.has('id')) + Number(node.has('name')))
        document.delete(index);
    }
  } else if (index < 0) {
    // Native configs replace the entire lower config. Store its ordinary
    // fields too so a volatile edit cannot erase required builtin values.
    document.add(expressionNode(document, { id, config: next }));
  } else {
    editValues(document, [index, 'config'], stored, next);
  }
  return String(document);
}

/** Preserve native SettingsForms/controller and replace only their editor seam. */
export default class ManagedConfigEditor extends Service {
  static inject = ['loader', 'profileContext', 'aiDotfilesManagedSettings'];
  constructor(ownerContext) {
    super(ownerContext, 'configEditor');
    this.ownerContext = ownerContext;
    this.queue = Promise.resolve();
  }
  get documentPath() { return this.ownerContext.profileContext.patchPath; }
  entries() {
    const boundary = this.ownerContext.aiDotfilesManagedSettings;
    const candidates = [...this.ownerContext.loader.entries()];
    const counts = new Map();
    for (const entry of candidates)
      counts.set(entry.options.id, (counts.get(entry.options.id) ?? 0) + 1);
    return candidates.filter(entry => boundary.owns(entry)
      && counts.get(entry.options.id) === 1);
  }
  configuration() {
    const boundary = this.ownerContext.aiDotfilesManagedSettings;
    const layers = boundary.read();
    return this.entries().map(entry => ({ entry,
      inherited: boundary.inherited(layers.loadedProfile, entry.options.id),
      override: structuredClone(layers.loadedProfile.patches.findLast(row =>
        row.id === entry.options.id && row.insert === undefined
        && row.config !== undefined)?.config ?? {}),
    }));
  }
  async edit(entry, change) {
    const operation = this.queue.then(() => this.write(entry, change));
    this.queue = operation.catch(() => {});
    await operation;
  }
  async write(entry, change) {
    const profile = this.ownerContext.profileContext;
    const boundary = this.ownerContext.aiDotfilesManagedSettings;
    await withFileLock(join(profile.dir, 'package.json'), async () => {
      if (!this.entries().includes(entry) || entry.fiber?.state !== 2)
        throw new Error('Configuration entry is no longer available');
      const layers = boundary.read();
      boundary.validate(layers, entry, entry.options.config);
      let before;
      let existed = true;
      try { before = await readFile(this.documentPath, 'utf8'); }
      catch (error) {
        if (error.code !== 'ENOENT') throw error;
        before = '[]\n'; existed = false;
      }
      if (!isDeepStrictEqual(boundary.read(yaml.load(before, {
        schema: entryListSchema })).loadedProfile.patches, layers.loadedProfile.patches))
        throw new Error('Native profile changed while settings were being read');
      const current = structuredClone(entry.options.config ?? {});
      const inherited = boundary.inherited(layers.loadedProfile, entry.options.id);
      const next = change(structuredClone(current), inherited);
      const fiber = entry.fiber;
      const schema = fiber.runtime?.Config;
      if (schema === undefined || !equalOutsideVolatile(current, next, schema))
        throw new Error('Managed settings accept only schema-declared volatile changes');
      const resolved = resolveConfig(fiber.runtime,
        fiber.ctx.waterfall(fiber, 'internal/config', next, () => next));
      if (!deepEqual(fiber.config, resolved, true))
        throw new Error('Configuration would change ordinary running values');
      if (isDeepStrictEqual(current, next)) return;
      const content = editDocument(before, entry, next, inherited);
      const patches = yaml.load(content, { schema: entryListSchema });
      boundary.validate(boundary.read(patches), entry, next);
      // No await between the final guard and persistence except the atomic
      // writer; the package lock coordinates native cross-process writers.
      await writeFileAtomic(this.documentPath, content, { mode: 0o600 });
      try {
        if (!this.entries().includes(entry) || entry.fiber !== fiber || fiber.state !== 2)
          throw new Error('Configuration entry changed during persistence');
        await entry.update({ config: next });
        if (entry.fiber !== fiber || fiber.state !== 2
          || !isDeepStrictEqual(plain(fiber.config), plain(resolved)))
          throw new Error('Configuration did not apply to the running volatile fields');
        boundary.committed(entry, next);
      } catch (error) {
        if (existed) await writeFileAtomic(this.documentPath, before, { mode: 0o600 });
        else await rm(this.documentPath, { force: true });
        if (entry.fiber === fiber && fiber.state === 2)
          await entry.update({ config: current });
        throw error;
      }
    });
  }
}
