import { createHash } from 'node:crypto';
export const VERSION = 'hcx-native-memory-local/v1';
export const PREPARATION_LOCK = true;
export const digest = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
export const clone = value => JSON.parse(JSON.stringify(value));
export const need = (ok, message) => { if (!ok) throw Error(message); };
const str = { type: 'string', minLength: 1 }, integer = { type: 'integer', minimum: 1 }, scope = { type: 'string', enum: ['private', 'shared'] };
const definitions = [
  ['hcx_memory_lookup', 'memory.lookup', 'Search an exact memory index term before reading a description or original.', ['scope', 'term'], { scope, term: str, pageSize: integer, cursor: str }],
  ['hcx_memory_read_index', 'memory.read_index', 'Read one versioned index layer; do not recursively expand the archive.', ['scope'], { scope, indexId: str, indexHandle: str, pageSize: integer, cursor: str }],
  ['hcx_memory_preview', 'memory.preview', 'Preview a supplied description for a previously delivered index hit.', ['hitHandle'], { hitHandle: str, pageChars: integer, cursor: str }],
  ['hcx_memory_preview_index', 'memory.preview_index', 'Preview the supplied introduction for a previously delivered index node.', ['indexHandle'], { indexHandle: str, pageChars: integer, cursor: str }],
  ['hcx_memory_read_original', 'memory.read_original', 'Read a selected original paragraph and requested same-document neighbors after preview.', ['readHandle', 'relevance'], { readHandle: str, relevance: str, before: { type: 'integer', minimum: 0 }, after: { type: 'integer', minimum: 0 }, pageChars: integer, cursor: str }],
];
export const TOOL_SCHEMAS = Object.freeze(definitions.map(([name, , description, required, properties]) => Object.freeze({ name, description, parameters: { type: 'object', required, additionalProperties: false, properties } })));
export const SCHEMA_DIGEST = digest(TOOL_SCHEMAS);
export const OPERATION = Object.freeze(Object.fromEntries(definitions.map(([name, op]) => [name, op])));
export function validateArguments(name, input) {
  const schema = TOOL_SCHEMAS.find(x => x.name === name)?.parameters;
  need(schema, 'UNKNOWN_MEMORY_TOOL'); need(input && typeof input === 'object' && !Array.isArray(input), 'INVALID_TOOL_ARGUMENTS');
  need(Object.keys(input).every(key => Object.hasOwn(schema.properties, key)), 'UNDECLARED_TOOL_ARGUMENT');
  for (const key of schema.required) need(Object.hasOwn(input, key), 'MISSING_TOOL_ARGUMENT');
  for (const [key, value] of Object.entries(input)) {
    const type = schema.properties[key];
    if (type.type === 'string') need(typeof value === 'string' && value.trim().length > 0 && (!type.enum || type.enum.includes(value)), 'INVALID_TOOL_ARGUMENT');
    else need(Number.isSafeInteger(value) && value >= type.minimum, 'INVALID_TOOL_READ_BUDGET');
  }
  if (name === 'hcx_memory_read_index') need(input.indexId || input.indexHandle, 'INDEX_ID_OR_HANDLE_REQUIRED');
  return clone(input);
}
export function makeToolPolicy({ actorId, sessionId, poolId, policyEpoch, policyDigest, enabled }) {
  need([actorId, sessionId, poolId, policyEpoch, policyDigest].every(x => typeof x === 'string' && x), 'POLICY_IDENTITY_REQUIRED');
  need(typeof enabled === 'boolean', 'EXPLICIT_TOOLS_MODE_REQUIRED');
  return { version: VERSION, actorId, sessionId, poolId, policyEpoch, policyDigest, toolsMode: enabled ? 'indexed-read-only-native-v1' : 'legacy-empty-tools', schemaDigest: enabled ? SCHEMA_DIGEST : digest([]), projectionVersion: 'hcx-history-surface-v1', evidenceClass: 'local-synthetic-only' };
}
export function assertToolPolicy(policy, schemas) {
  need(Array.isArray(schemas), 'TOOL_SCHEMA_LIST_REQUIRED');
  need(['indexed-read-only-native-v1', 'legacy-empty-tools'].includes(policy.toolsMode), 'UNKNOWN_TOOL_POLICY_MODE');
  need(digest(schemas) === policy.schemaDigest, 'TOOL_POLICY_SCHEMA_MISMATCH');
  need(policy.toolsMode === 'indexed-read-only-native-v1' ? digest(schemas) === SCHEMA_DIGEST : schemas.length === 0, 'TOOL_POLICY_MODE_MISMATCH');
}
export const render = value => [{ type: 'text', text: JSON.stringify(value) }];
export const presentationMeta = value => ({ kind: 'hcx-memory-receipt', version: VERSION, actorId: value.actorId, sessionId: value.sessionId, policyEpoch: value.policyEpoch, requestId: value.requestId, toolCallId: value.toolCallId, readDigest: value.readDigest });
// Source-informed schema only. Supported-dialect/runtime registration unverified.
export const OUTPUT_SCHEMA = { type: 'object', additionalProperties: false,
  required: ['kind', 'version', 'actorId', 'sessionId', 'policyEpoch', 'requestId', 'toolCallId', 'operation', 'read', 'readDigest', 'sourceReceipts'],
  properties: { kind: { type: 'string', enum: ['hcx-memory-read-result'] }, version: { type: 'string', enum: [VERSION] }, actorId: str, sessionId: str, policyEpoch: str, requestId: str, toolCallId: str, operation: str, read: { type: 'object' }, readDigest: str, sourceReceipts: { type: 'array', items: { type: 'object' } } } };
