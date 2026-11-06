import { DatabaseSync } from 'node:sqlite';
import { createHash } from 'node:crypto';
import { realpathSync } from 'node:fs';
import { ParagraphMemory } from './paragraph/paragraph-memory.mjs';

export const VERSION = 'hcx-indexed-recall/v1';
export const digest = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const copy = value => JSON.parse(JSON.stringify(value));
const need = (ok, message) => { if (!ok) throw Error(message); };
const natural = (value, min = 0) => need(Number.isSafeInteger(value) && value >= min, 'invalid read budget/offset');
const nonempty = value => typeof value === 'string' && value.trim().length > 0;
const bytes = value => Buffer.byteLength(JSON.stringify(value));
const encode = value => Buffer.from(JSON.stringify(value)).toString('base64url');
function decode(value) { try { return JSON.parse(Buffer.from(value, 'base64url').toString()); } catch { throw Error('invalid cursor'); } }
function textEnd(text, offset, amount) {
  natural(offset); natural(amount, 1); need(offset <= text.length, 'invalid text offset');
  const low = c => /[\uDC00-\uDFFF]/.test(c), high = c => /[\uD800-\uDBFF]/.test(c);
  need(!(offset > 0 && low(text[offset]) && high(text[offset - 1])), 'split surrogate cursor');
  let end = Math.min(text.length, offset + amount);
  if (end < text.length && high(text[end - 1]) && low(text[end])) end--;
  if (end === offset && end < text.length) end += 2;
  return end;
}
export class RecallResourceHold extends Error {
  constructor(requiredBytes, budgetBytes) { super('RECALL_RESPONSE_RESOURCE_HELD'); this.requiredBytes = requiredBytes; this.budgetBytes = budgetBytes; }
}

// These readers never instantiate Memory: its constructor writes schema/PRAGMAs.
// Scope metadata is migration evidence, not cryptographic actor authentication.
class ReadPartition {
  constructor(path, expectedScope, snapshotSeq = null) {
    this.path = realpathSync(path); this.db = new DatabaseSync(this.path, { readOnly: true });
    try {
      this.db.exec('PRAGMA query_only=ON');
      this.max = this.db.prepare('SELECT COALESCE(MAX(seq),0) AS seq FROM events').get().seq;
      natural(snapshotSeq); need(snapshotSeq <= this.max, 'snapshot outside admitted source');
      // Temp view shadows unqualified events for every reviewed reader query,
      // including origin/document/read() paths. Main source tables stay read-only.
      this.db.exec('PRAGMA query_only=OFF');
      this.db.exec('CREATE TEMP VIEW events AS SELECT * FROM main.events WHERE seq<='+snapshotSeq);
      this.db.exec('PRAGMA query_only=ON');
      const row = this.db.prepare("SELECT data FROM events WHERE kind='recall-store-scope' AND subject='scope' ORDER BY seq DESC LIMIT 1").get();
      need(row && digest(JSON.parse(row.data)) === digest(expectedScope), 'store scope mismatch or explicit migration required');
      this.scope = copy(expectedScope); this.snapshotSeq = snapshotSeq;
      this.reader = Object.create(ParagraphMemory.prototype); this.reader.db = this.db;
      this.max = this.db.prepare('SELECT COALESCE(MAX(seq),0) AS seq FROM events').get().seq;
    } catch (error) { this.db.close(); throw error; }
  }
  close() { this.db.close(); }
  at(kind, subject, snapshot) {
    const row = this.db.prepare('SELECT * FROM events WHERE kind=? AND subject=? AND seq<=? ORDER BY seq DESC LIMIT 1').get(kind, subject, snapshot);
    return row ? { ...row, data: JSON.parse(row.data) } : null;
  }
}

/** Read-only, local-only host capability broker. Keep one instance per actor/session.
 * Handles only prove this broker emitted an index/preview, NOT cognition or relevance.
 * Host identity and trustworthy store mounts are prerequisites, not model fields.
 */
export class RecallAdapter {
  #issuedPages = new WeakMap();
  constructor({ actorId, sessionId, poolId, privatePath, sharedPath, maxResponseBytes = 16384, snapshots }) {
    need([actorId, sessionId, poolId].every(nonempty), 'host identity required'); natural(maxResponseBytes, 1); need(snapshots && Object.keys(snapshots).sort().join(',')==='private,shared','explicit snapshot vector required');
    need(realpathSync(privatePath) !== realpathSync(sharedPath), 'private and shared stores must be physically separate');
    Object.assign(this, { actorId, sessionId, poolId, maxResponseBytes }); this.handles = new Map();
    const own = new ReadPartition(privatePath, { type: 'private', actorId, sessionId }, snapshots.private);
    try { this.stores = { private: own, shared: new ReadPartition(sharedPath, { type: 'shared', poolId }, snapshots.shared) }; }
    catch (error) { own.close(); throw error; }
  }
  close() { for (const store of Object.values(this.stores)) store.close(); }
  store(scope) { need(Object.hasOwn(this.stores, scope), 'unknown scope'); return this.stores[scope]; }
  receipt(handle, kind) {
    const value = this.handles.get(handle); need(value && (!kind || value.kind === kind), 'unknown, expired, or wrong-stage handle'); return value;
  }
  stage(kind, data, pending) {
    const receipt = { version: VERSION, actorId: this.actorId, sessionId: this.sessionId, kind, ...data };
    const id = digest(receipt); pending.push([id, receipt]); return id;
  }
  fit(build, { pageSize = 20, pageChars = 4000 } = {}) {
    natural(pageSize, 1); natural(pageChars, 1);
    for (;;) {
      const pending = [], value = build({ pageSize, pageChars, pending });
      value.version = VERSION; value.effectiveReadBudget = { pageSize, pageChars };
      const length = bytes(value);
      if (length <= this.maxResponseBytes) {
        for (const [id, receipt] of pending) this.handles.set(id, receipt);
        this.#issuedPages.set(value, digest(value));
        return value;
      }
      if (pageSize > 1) pageSize = Math.max(1, Math.floor(pageSize / 2));
      else if (pageChars > 1) pageChars = Math.max(1, Math.floor(pageChars / 2));
      else throw new RecallResourceHold(length, this.maxResponseBytes);
    }
  }
  // Index first: no descriptions or original paragraph text are emitted here.
  lookup({ scope, term, pageSize = 20, cursor = null }) {
    const store = this.store(scope); let inner = null;
    if (cursor) { const c = decode(cursor); need(c.scope === scope && c.term === term && c.actorId === this.actorId && c.sessionId === this.sessionId, 'lookup cursor scope/query mismatch'); inner = c.inner; }
    return this.fit(({ pageSize, pending }) => {
      const found = store.reader.lookupParagraphs({ term, pageSize, cursor: inner });
      return { stage: 'index', scope, matching: found.matching, snapshotSeq: found.snapshot,
        hits: found.hits.map(hit => ({ ...hit, hitHandle: this.stage('hit', { scope, paragraphId: hit.paragraphId, snapshot: found.snapshot }, pending) })),
        nextCursor: found.nextCursor ? encode({ scope, term, actorId: this.actorId, sessionId: this.sessionId, inner: found.nextCursor }) : null,
        noHitMeaning: 'No hit is not proof that prior work never occurred.' };
    }, { pageSize });
  }
  // One level at a time. No total-node, dictionary, or hierarchy-depth cap.
  // Introduction/summary text is deliberately read later through previewIndex().
  readIndex({ scope, indexId = null, indexHandle = null, pageSize = 20, cursor = null }) {
    const store = this.store(scope); let offset = 0, snapshot = store.db.prepare('SELECT COALESCE(MAX(seq),0) AS seq FROM events').get().seq;
    if (indexHandle) { const h = this.receipt(indexHandle, 'index'); need(h.scope === scope && (!indexId || h.indexId === indexId), 'index handle scope mismatch'); indexId = h.indexId; snapshot = h.snapshot; }
    need(nonempty(indexId), 'index identity required');
    if (cursor) { const c = decode(cursor); need(c.scope === scope && c.indexId === indexId && c.actorId === this.actorId && c.sessionId === this.sessionId, 'index cursor mismatch'); need(!indexHandle || c.snapshot === snapshot, 'index cursor snapshot mismatch'); snapshot = c.snapshot; offset = c.offset; }
    natural(snapshot); natural(offset); need(snapshot <= store.db.prepare('SELECT COALESCE(MAX(seq),0) AS seq FROM events').get().seq, 'future index snapshot');
    return this.fit(({ pageSize, pending }) => {
      const row = store.at('index-node', indexId, snapshot);
      if (!row) return { stage: 'index', status: 'missing-index', scope, indexId, snapshotSeq: snapshot };
      need(offset <= row.data.refs.length, 'index cursor offset');
      const refs = row.data.refs.slice(offset, offset + pageSize).map((ref, i) => {
        const present = !!store.at(ref.kind === 'index' ? 'index-node' : 'paragraph', ref.id, snapshot);
        return { ...ref, ordinal: offset + i, status: present ? 'available' : 'missing-target',
          handle: present ? this.stage(ref.kind === 'index' ? 'index' : 'hit', { scope, [ref.kind === 'index' ? 'indexId' : 'paragraphId']: ref.id, snapshot }, pending) : null };
      });
      return { stage: 'index', status: 'ready', scope, indexId, eventId: row.id, snapshotSeq: snapshot, refs,
        previewHandle: this.stage('index', { scope, indexId, snapshot }, pending),
        provenance: { clerkId: row.data.clerkId, sourceEventId: row.data.sourceEventId, supersedes: row.data.supersedes },
        nextCursor: offset + refs.length < row.data.refs.length ? encode({ scope, indexId, snapshot, offset: offset + refs.length, actorId: this.actorId, sessionId: this.sessionId }) : null };
    }, { pageSize });
  }
  previewIndex({ indexHandle, pageChars = 1000, cursor = null }) {
    const h = this.receipt(indexHandle, 'index');
    return this.previewText({ h, handle: indexHandle, kind: 'index-node', subject: h.indexId, field: 'summary', pageChars, cursor, issueReadHandle: false });
  }
  // Only a matched index hit may fetch the cheap supplied description.
  preview({ hitHandle, pageChars = 1000, cursor = null }) {
    const h = this.receipt(hitHandle, 'hit');
    return this.previewText({ h, handle: hitHandle, kind: 'description', subject: h.paragraphId, field: 'description', pageChars, cursor, issueReadHandle: true });
  }
  previewText({ h, handle, kind, subject, field, pageChars, cursor, issueReadHandle }) {
    let offset = 0;
    if (cursor) { const c = decode(cursor); need(c.handle === handle, 'preview cursor mismatch'); offset = c.offset; }
    natural(offset); const store = this.store(h.scope);
    return this.fit(({ pageChars, pending }) => {
      const row = store.at(kind, subject, h.snapshot), text = row?.data[field];
      if (typeof text !== 'string' || !text.length) return { stage: 'preview', scope: h.scope, status: 'missing-description', paragraphId: h.paragraphId ?? null, indexId: h.indexId ?? null, snapshotSeq: h.snapshot, readHandle: null };
      need(offset < text.length, 'preview cursor offset');
      const end = textEnd(text, offset, pageChars);
      return { stage: 'preview', scope: h.scope, status: 'ready', paragraphId: h.paragraphId ?? null, indexId: h.indexId ?? null,
        eventId: row.id, snapshotSeq: h.snapshot, representation: 'supplied-interpretation-not-original-fact', text: text.slice(offset, end), start: offset, end, complete: end === text.length,
        provenance: { source: row.data.source ?? null, clerkId: row.data.clerkId ?? null, sourceEventId: row.data.sourceEventId ?? null },
        readHandle: issueReadHandle ? this.stage('preview', { scope: h.scope, paragraphId: h.paragraphId, snapshot: h.snapshot, descriptionEventId: row.id }, pending) : null,
        nextCursor: end < text.length ? encode({ handle, offset: end }) : null };
    }, { pageSize: 1, pageChars });
  }
  // The requesting actor supplies a relevance reason. This records a choice,
  // not a claim that the host independently verified semantic relevance.
  readOriginal({ readHandle, relevance, before = 0, after = 0, pageChars = 4000, cursor = null }) {
    const h = this.receipt(readHandle, 'preview'); need(nonempty(relevance), 'explicit relevance choice required'); natural(before); natural(after);
    const store = this.store(h.scope), origin = store.at('paragraph-origin', h.paragraphId, h.snapshot)?.data;
    need(origin, 'original provenance missing; explicit migration required');
    const document = store.at('document', origin.documentKey, h.snapshot);
    need(document, 'source document missing at lookup snapshot');
    const low = Math.max(0, origin.ordinal - before);
    let inner = encode({ binding: digest(['window-v1', h.paragraphId, before, after, 'raw']), ordinal: low, offset: 0, snapshot: h.snapshot });
    if (cursor) { const c = decode(cursor); need(c.readHandle === readHandle && c.before === before && c.after === after && c.relevance === relevance, 'original cursor mismatch'); inner = c.inner; const native = decode(inner); need(native.snapshot === h.snapshot, 'original cursor snapshot mismatch'); }
    return this.fit(({ pageChars }) => {
      const page = store.reader.readParagraphWindow({ paragraphId: h.paragraphId, before, after, pageChars, cursor: inner, neighborMode: 'raw' });
      return { stage: 'original', scope: h.scope, status: 'ready', ...page, snapshotSeq: h.snapshot,
        selection: { paragraphId: h.paragraphId, descriptionEventId: h.descriptionEventId, relevance },
        nextCursor: page.nextCursor ? encode({ readHandle, before, after, relevance, inner: page.nextCursor }) : null };
    }, { pageSize: 1, pageChars });
  }
  dispatch({ tool, input }) {
    const methods = { 'memory.lookup': 'lookup', 'memory.read_index': 'readIndex', 'memory.preview': 'preview', 'memory.preview_index': 'previewIndex', 'memory.read_original': 'readOriginal' };
    need(Object.hasOwn(methods, tool), 'unknown read-only recall tool'); return this[methods[tool]](input);
  }
  // Process-local issuance check, not cryptographic or durable authentication.
  // Never accept model-authored JSON pages or restart-deserialized pages here.
  checkedPages(scope, pages) {
    need(Array.isArray(pages), 'selected pages required');
    for (const page of pages) need(page && page.scope === scope && this.#issuedPages.get(page) === digest(page), 'page was not emitted unchanged by this broker');
    return pages;
  }
  composeClaim({ dispatchId, sourceRef, intent, controlContext, privatePages = [], sharedPages = [], maxBytes = 32768 }) {
    return composeUnboundClaim({ actorId: this.actorId, sessionId: this.sessionId, dispatchId, sourceRef, intent, controlContext,
      privateRecall: { descriptor: this.descriptor('private'), pages: this.checkedPages('private', privatePages) },
      sharedRecall: { descriptor: this.descriptor('shared'), pages: this.checkedPages('shared', sharedPages) }, maxBytes });
  }
  descriptor(scope) {
    const store = this.store(scope);
    return { version: VERSION, scope, storeIdentity: store.scope, snapshotSeq: store.db.prepare('SELECT COALESCE(MAX(seq),0) AS seq FROM events').get().seq,
      workflow: ['memory.lookup or memory.read_index', 'memory.preview', 'memory.read_original'], retention: 'append-only; no automatic forgetting', noHitIsProofOfAbsence: false };
  }
}

// Pure claim composition: this is a NEW unbound draft, never a rewrite of a
// stored Body claim/binding. It does not accept or enumerate a memory archive.
// LOW-LEVEL TRUSTED-HOST ONLY: structural validation is not page authentication.
// Model-supplied pages must NEVER be passed here; use adapter.composeClaim().
export function composeUnboundClaim({ actorId, sessionId, dispatchId, sourceRef, intent, controlContext, privateRecall, sharedRecall, maxBytes = 32768 }) {
  need([actorId, sessionId, dispatchId].every(nonempty), 'identity/dispatch required'); natural(maxBytes, 1);
  need(sourceRef && nonempty(sourceRef.sourceId) && nonempty(sourceRef.eventId) && /^[a-f0-9]{64}$/.test(sourceRef.digest), 'exact source reference required');
  need(intent && nonempty(intent.sourceId) && typeof intent.text === 'string' && intent.text.length && intent.digest === digest(intent.text), 'verified active intent text required');
  need(controlContext && Number.isSafeInteger(controlContext.policyEpoch) && controlContext.policyEpoch >= 0 && Object.hasOwn(controlContext, 'safetyHold'), 'explicit policy epoch and safety hold required');
  need(privateRecall?.descriptor?.storeIdentity?.actorId === actorId && privateRecall.descriptor.storeIdentity.sessionId === sessionId && privateRecall.descriptor.scope === 'private', 'private memory identity mismatch');
  need(sharedRecall?.descriptor?.scope === 'shared', 'shared memory scope required');
  for (const [scope, recall] of [['private', privateRecall], ['shared', sharedRecall]]) {
    need(Array.isArray(recall.pages), 'selected response pages required');
    need(recall.pages.every(p => p.version === VERSION && p.scope === scope), 'cross-scope recall page');
  }
  const candidate = copy({ kind: 'hcx-indexed-body-input', version: VERSION, status: 'unbound-candidate', actorId, sessionId, id: dispatchId,
    sourceRef, intent, controlContext, privateRecall, sharedRecall });
  const length = bytes(candidate); if (length > maxBytes) throw new RecallResourceHold(length, maxBytes);
  return candidate;
}

// Reads only one source and the initial intent, plus SQL counters. Does not call
// Body.claim(), Body.memories(), constructors, tx(), bind(), or rewrite history.
export function prepareClaimCandidate({ bodyPath, adapter, controlContext, privatePages = [], sharedPages = [], intentReview = null, maxBytes = 32768 }) {
  const db = new DatabaseSync(bodyPath, { readOnly: true });
  try {
    db.exec('PRAGMA query_only=ON; BEGIN');
    const one = (kind, subject) => {
      const row = db.prepare('SELECT * FROM events WHERE kind=? AND subject=? ORDER BY seq DESC LIMIT 1').get('body-' + kind, subject);
      return row ? { ...row, data: JSON.parse(row.data) } : null;
    };
    const config = one('config', 'body')?.data;
    need(config?.actorId === adapter.actorId && config.sessionId === adapter.sessionId, 'Body identity mismatch');
    const stateRow = db.prepare("SELECT data FROM events WHERE kind='body-state' ORDER BY seq DESC LIMIT 1").get();
    const state = stateRow ? JSON.parse(stateRow.data) : { mode: 'new' };
    if (state.mode !== 'awake') return { status: 'no-ready-claim', mode: state.mode };
    const unresolved = db.prepare("SELECT COUNT(*) AS n FROM events c WHERE c.kind='body-claim' AND NOT EXISTS (SELECT 1 FROM events p WHERE p.kind='body-processed' AND p.subject=json_extract(c.data,'$.id'))").get().n;
    need(unresolved === 0, 'existing claim/binding must be reconciled unchanged before migration');
    const ready = db.prepare("SELECT * FROM events r WHERE r.kind='body-ready' AND NOT EXISTS (SELECT 1 FROM events c WHERE c.kind='body-claim' AND c.subject=r.subject) ORDER BY seq LIMIT 1").get();
    if (!ready) return { status: 'no-ready-claim', mode: state.mode };
    const claimed = db.prepare("SELECT COUNT(*) AS n FROM events WHERE kind='body-claim'").get().n;
    const grants = db.prepare("SELECT COALESCE(SUM(json_extract(data,'$.extra')),0) AS n FROM events WHERE kind='body-grant'").get().n;
    if (claimed >= config.allowance + grants) return { status: 'resource-held', reason: 'existing-request-allowance', persisted: false };
    need(controlContext.safetyHold === false, 'safety hold blocks claim preparation');
    const source = one('source', ready.subject); need(source, 'ready source missing');
    const initials = db.prepare("SELECT subject,data FROM events WHERE kind='body-source' AND json_extract(data,'$.kind')='initial' ORDER BY seq LIMIT 2").all();
    need(initials.length === 1, 'exactly one original intent required; active-intent migration must be explicit');
    const intentSource = initials[0], text = JSON.parse(intentSource.data).text;
    need(intentReview?.sourceId === intentSource.subject && intentReview.digest === digest(text) && intentReview.policyEpoch === controlContext.policyEpoch && intentReview.coverage === 'reviewed-no-unrepresented-user-corrections', 'active intent coverage requires explicit host review; initial invitation is not enough');
    return adapter.composeClaim({ dispatchId: 'dispatch:' + ready.subject,
      sourceRef: { sourceId: ready.subject, eventId: source.id, eventSeq: source.seq, kind: source.data.kind, digest: digest(source.data) },
      intent: { sourceId: intentSource.subject, text, digest: digest(text), coverage: intentReview.coverage, reviewedPolicyEpoch: intentReview.policyEpoch },
      controlContext, privatePages, sharedPages, maxBytes });
  } finally { db.close(); }
}
