import { DatabaseSync } from 'node:sqlite';
import { createHash } from 'node:crypto';
import { isDeepStrictEqual } from 'node:util';
import { existsSync, lstatSync, realpathSync, readFileSync, writeFileSync, copyFileSync, mkdtempSync, constants, openSync, closeSync, fstatSync } from 'node:fs';
import { resolve, dirname, basename, join } from 'node:path';
import { tmpdir } from 'node:os';
import { validateWal, verifyDerivedPages } from './vendor/wal-format.mjs';
export const VERSION = 'hcx-rolling-history/v1';
// Intents are JSON values, not a promised serialization key order. Compare all
// fields structurally; retain the exact original event and its existing digest.
export function matchesReplacementIntent(event, replacement) {
  const { seq, time, ...intent } = event;
  return isDeepStrictEqual(intent, replacement);
}
export const hash = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const clone = value => JSON.parse(JSON.stringify(value));
const need = (value, code) => { if (!value) throw Error(code); };
const SCOPE = ['actorId', 'sessionId', 'policyEpoch', 'policyDigest'];
const SURFACE = ['system/message', 'user/message', 'assistant/message', 'tool/result'];
const message = e => e.type === 'user/message' ? e.data : e.data?.message;
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const nonempty = value => typeof value === 'string' && value.length > 0;
const logOnly = event => need(event.surfaceOp === undefined && event.sourceEventSeqs === undefined, 'LOG_ONLY_EVENT_SURFACE_INTENT_HELD');
const ZERO = '0'.repeat(64);
const size = value => Buffer.byteLength(JSON.stringify(value));
const positive = (value, fallback) => { const n = value ?? fallback; need(Number.isSafeInteger(n) && n > 0, 'POSITIVE_READ_BUDGET_REQUIRED'); return n; };

const present = path => { try { lstatSync(path); return true; } catch (error) { if (error.code === 'ENOENT') return false; throw error; } };
function pinnedRead(path) {
  const fd = openSync(path, constants.O_RDONLY | constants.O_NOFOLLOW);
  try {
    const a = fstatSync(fd, { bigint: true }); need(a.isFile() && a.nlink === 1n, 'SOURCE_COMPONENT_ALIAS_OR_TYPE');
    const bytes = readFileSync(fd), b = fstatSync(fd, { bigint: true });
    for (const key of ['dev','ino','size','mtimeNs','ctimeNs']) need(a[key] === b[key], 'SOURCE_CHANGED_DURING_READ');
    const fingerprint = Object.fromEntries(['dev','ino','size','mtimeNs','ctimeNs'].map(k => [k, String(b[k])]));
    fingerprint.sha256 = createHash('sha256').update(bytes).digest('hex'); return { bytes, fingerprint };
  } finally { closeSync(fd); }
}
function verifyExistingCandidate(path, identity) {
  const marker = path + '.identity.json', expected = { version: VERSION, ...identity };
  const suffixes = ['', '-wal', '-shm', '.identity.json'], ownedSuffixes = [...suffixes, '.owner.sqlite', '.owner.sqlite-journal'];
  if (!present(path)) {
    need(ownedSuffixes.every(suffix => !present(path + suffix)), 'PARTIAL_OR_FOREIGN_ARCHIVE_PATH_HELD');
    return null;
  }
  need(lstatSync(path).isFile() && present(marker) && lstatSync(marker).isFile() && !lstatSync(marker).isSymbolicLink(), 'EXISTING_NON_CANDIDATE_ARCHIVE_REJECTED');
  need(hash(JSON.parse(pinnedRead(marker).bytes.toString('utf8'))) === hash(expected), 'EXISTING_ARCHIVE_IDENTITY_MISMATCH');
  // No SQL connection to the original during preflight. A read-only SQLite
  // connection could create sidecars or silently ignore a damaged WAL.
  const snapshot = mkdtempSync(join(tmpdir(), 'hcx-rolling-admission-copy-')), copyPath = join(snapshot, 'archive.sqlite'), pins = new Map();
  for (const suffix of suffixes) if (present(path + suffix)) pins.set(suffix, pinnedRead(path + suffix));
  const guard = () => {
    need(suffixes.every(suffix => present(path + suffix) === pins.has(suffix)), 'ARCHIVE_INVENTORY_CHANGED');
    for (const [suffix, pin] of pins) need(hash(pinnedRead(path + suffix).fingerprint) === hash(pin.fingerprint), 'ARCHIVE_IDENTITY_OR_BYTES_CHANGED');
  };
  guard();
  const dbBytes = pins.get('').bytes, walBytes = pins.get('-wal')?.bytes;
  need(!pins.has('-shm') || pins.has('-wal'), 'SHM_WITHOUT_WAL_HELD');
  need(!pins.has('-wal') || walBytes.length >= 32, 'EMPTY_OR_TRUNCATED_WAL_HELD');
  const walProof = walBytes?.length ? validateWal(dbBytes, walBytes) : null;
  // A copied working DB may be checkpointed. The original remains untouched.
  for (const [suffix, pin] of pins) if (suffix !== '.identity.json') writeFileSync(copyPath + suffix, pin.bytes, { flag: 'wx', mode: 0o600 });
  let db;
  try {
    db = new DatabaseSync(copyPath);
    need(db.prepare('PRAGMA integrity_check').all().every(row => Object.values(row)[0] === 'ok'), 'ARCHIVE_COPY_INTEGRITY_FAILURE');
    if (walProof) {
      need(db.prepare('PRAGMA wal_checkpoint(TRUNCATE)').get().busy === 0, 'ARCHIVE_COPY_CHECKPOINT_FAILED');
      need(Object.values(db.prepare('PRAGMA journal_mode=DELETE').get())[0] === 'delete', 'ARCHIVE_COPY_CHECKPOINT_FAILED');
      db.close(); db = null;
      verifyDerivedPages(dbBytes, walBytes, readFileSync(copyPath), walProof);
      db = new DatabaseSync(copyPath, { readOnly: true });
    }
    const tables = new Set(db.prepare("SELECT name FROM sqlite_master WHERE type='table'").all().map(r => r.name));
    need(['records','originals','nodes','turns','checkpoints','indices','observations','source_requests','work_pending'].every(name => tables.has(name)), 'EXISTING_NON_CANDIDATE_ARCHIVE_REJECTED');
    const row = db.prepare("SELECT data,digest FROM records WHERE kind='identity' AND id='fixed'").get();
    need(row && hash(JSON.parse(row.data)) === row.digest && hash(JSON.parse(row.data)) === hash(expected), 'EXISTING_ARCHIVE_IDENTITY_MISMATCH');
  } finally { db?.close(); }
  guard(); return guard;
}

// Candidate-local database only. Originals/turns/plans/records are append-only.
// nodes is a disposable derived cache: deactivating a node does not delete it or
// its original event. No retention, index-count, dictionary or depth cap exists.
export class RollingHistoryBridge {
  constructor({ path, persistenceCtx, agent, identity, pageSize = 64, pageBytes = 1024 * 1024, responseBytes = 32768, workEvents = 2048, onAdmissionStage = () => {} }) {
    need(SCOPE.every(k => typeof identity?.[k] === 'string' && identity[k]), 'IDENTITY_REQUIRED');
    this.identity = Object.freeze(clone(identity)); this.agent = agent; this.session = agent.session; this.persistenceCtx = persistenceCtx;
    this.pageSize = positive(pageSize); this.pageBytes = positive(pageBytes); this.responseBytes = positive(responseBytes); this.workEvents = positive(workEvents);
    this.assertOwner(agent); need(typeof persistenceCtx.sessions?.flush === 'function' && typeof persistenceCtx.sessionPersistence?.open === 'function' && typeof persistenceCtx.sessionPersistence?.stat === 'function', 'ROOT_PERSISTENCE_REQUIRED');
    const absolute = resolve(path); need(!existsSync(absolute) || !lstatSync(absolute).isSymbolicLink(), 'ARCHIVE_SYMLINK_REJECTED');
    this.path = join(realpathSync(dirname(absolute)), basename(absolute));
    let sourceGuard = verifyExistingCandidate(this.path, this.identity);
    if (!sourceGuard) {
      // A new-path check is not ownership: another actor could create the path
      // before SQLite opens it. Atomically reserve our own empty inode first.
      const fd = openSync(this.path, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
      try { need(fstatSync(fd).size === 0, 'FRESH_PLACEHOLDER_NOT_EMPTY'); } finally { closeSync(fd); }
      writeFileSync(this.path + '.identity.json', JSON.stringify({ version: VERSION, ...this.identity }) + '\n', { flag: 'wx', mode: 0o600 });
      const empty = pinnedRead(this.path), marker = pinnedRead(this.path + '.identity.json');
      sourceGuard = () => {
        need(!present(this.path + '-wal') && !present(this.path + '-shm') && !present(this.path + '-journal'), 'FRESH_ARCHIVE_SIDECAR_RACE');
        need(hash(pinnedRead(this.path).fingerprint) === hash(empty.fingerprint) && hash(pinnedRead(this.path + '.identity.json').fingerprint) === hash(marker.fingerprint), 'FRESH_ARCHIVE_IDENTITY_OR_BYTES_CHANGED');
      };
    }
    onAdmissionStage('after-verification'); sourceGuard();
    this.owner = new DatabaseSync(this.path + '.owner.sqlite');
    try {
      this.owner.exec('PRAGMA busy_timeout=0; BEGIN EXCLUSIVE');
      onAdmissionStage('owner-acquired'); sourceGuard?.();
      this.db = new DatabaseSync(this.path);
      this.db.exec(`PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;
        CREATE TABLE IF NOT EXISTS records(n INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT,id TEXT,data TEXT,digest TEXT,UNIQUE(kind,id));
        CREATE TABLE IF NOT EXISTS originals(seq INTEGER PRIMARY KEY,type TEXT,turn INTEGER,callId TEXT,json TEXT,digest TEXT,chain TEXT);
        CREATE INDEX IF NOT EXISTS original_type_seq ON originals(type,seq);
        CREATE INDEX IF NOT EXISTS original_kind_turn ON originals(type,turn,seq);
        CREATE INDEX IF NOT EXISTS original_call ON originals(callId,type,seq);
        CREATE TABLE IF NOT EXISTS source_requests(callId TEXT PRIMARY KEY,assistantSeq INTEGER,turn INTEGER,step INTEGER,dispatchId TEXT,name TEXT,owned INTEGER,nativeBound INTEGER,callSeq INTEGER,resultSeq INTEGER,closed INTEGER);
        CREATE INDEX IF NOT EXISTS request_pending ON source_requests(nativeBound,owned,name,assistantSeq);
        CREATE TABLE IF NOT EXISTS work_pending(kind TEXT,id TEXT,active INTEGER,PRIMARY KEY(kind,id));
        CREATE INDEX IF NOT EXISTS work_active ON work_pending(kind,active,id);
        CREATE INDEX IF NOT EXISTS request_dispatch ON source_requests(dispatchId,callId);
        CREATE TABLE IF NOT EXISTS nodes(seq INTEGER PRIMARY KEY,pos INTEGER,active INTEGER);
        CREATE INDEX IF NOT EXISTS node_active_order ON nodes(active,pos);
        CREATE TABLE IF NOT EXISTS turns(turn INTEGER PRIMARY KEY,startSeq INTEGER,endSeq INTEGER,firstSurface INTEGER,lastSurface INTEGER);
        CREATE INDEX IF NOT EXISTS turn_end ON turns(endSeq);
        CREATE TABLE IF NOT EXISTS checkpoints(n INTEGER PRIMARY KEY AUTOINCREMENT,boundary INTEGER UNIQUE,data TEXT,digest TEXT);
        CREATE TABLE IF NOT EXISTS indices(id TEXT PRIMARY KEY,data TEXT,digest TEXT);
        CREATE TABLE IF NOT EXISTS observations(indexId TEXT PRIMARY KEY,eventSeq INTEGER,eventDigest TEXT);
        CREATE INDEX IF NOT EXISTS observed_order ON observations(eventSeq);
        CREATE TRIGGER IF NOT EXISTS original_no_update BEFORE UPDATE ON originals BEGIN SELECT RAISE(ABORT,'append only'); END;
        CREATE TRIGGER IF NOT EXISTS original_no_delete BEFORE DELETE ON originals BEGIN SELECT RAISE(ABORT,'append only'); END;`);
      for (const table of ['records', 'turns', 'checkpoints', 'indices', 'observations']) for (const action of ['UPDATE', 'DELETE']) this.db.exec(`CREATE TRIGGER IF NOT EXISTS ${table}_no_${action} BEFORE ${action} ON ${table} BEGIN SELECT RAISE(ABORT,'append only'); END;`);
      this.put('identity', 'fixed', { version: VERSION, ...this.identity });
      // Cold cache repair only. Authoritative records remain append-only.
      this.db.exec(`BEGIN IMMEDIATE; UPDATE work_pending SET active=0;
        INSERT OR REPLACE INTO work_pending SELECT a.kind,a.id,1 FROM records a LEFT JOIN records b ON b.id=a.id AND b.kind=CASE a.kind WHEN 'native-call' THEN 'native-complete' ELSE 'projection-observed' END WHERE a.kind IN ('native-call','projection-plan') AND b.id IS NULL;
        UPDATE source_requests SET nativeBound=EXISTS(SELECT 1 FROM records WHERE kind='native-call' AND id=source_requests.callId); COMMIT;`);
      need(this.db.prepare('PRAGMA quick_check').get().quick_check === 'ok', 'ARCHIVE_SQLITE_CHECK_FAILED');
    } catch (error) { this.db?.close(); this.owner.close(); throw error; }
    this.audited = false; this.syncing = false; this.hits = new Map(); this.reads = new Map(); this.cursors = new Map(); this.issuedPlans = new WeakMap();
  }
  close() { this.db.close(); this.owner.close(); }
  assertOwner(agent = this.agent) { need(agent === this.agent && agent.session === this.session && agent.id === this.identity.sessionId && this.session.id === this.identity.sessionId, 'EXACT_AGENT_SESSION_REQUIRED'); }
  healthy() { need(!this.poisoned && !this.one('hold', 'permanent'), 'ROLLING_BRIDGE_HELD'); this.assertOwner(); }
  hold(code = 'ROLLING_INTEGRITY_HOLD') { this.poisoned = true; try { this.put('hold', 'permanent', { code: 'ROLLING_INTEGRITY_HOLD' }); } catch {} throw Error(code); }
  put(kind, id, data) {
    const ownsTransaction = !this.db.isTransaction;
    if (ownsTransaction) this.db.exec('BEGIN IMMEDIATE');
    try {
      const raw = JSON.stringify(data), prior = this.db.prepare('SELECT data,digest FROM records WHERE kind=? AND id=?').get(kind, id);
      if (prior) need(prior.data === raw && prior.digest === hash(data), 'IMMUTABLE_RECORD_CONFLICT');
      else this.db.prepare('INSERT INTO records(kind,id,data,digest) VALUES(?,?,?,?)').run(kind, id, raw, hash(data));
      const end = { 'native-call': 'native-complete', 'projection-plan': 'projection-observed' }[kind];
      if (end && !this.db.prepare('SELECT 1 FROM records WHERE kind=? AND id=?').get(end, id)) this.db.prepare('INSERT OR REPLACE INTO work_pending VALUES(?,?,1)').run(kind, id);
      const start = { 'native-complete': 'native-call', 'projection-observed': 'projection-plan' }[kind];
      if (start) this.db.prepare('UPDATE work_pending SET active=0 WHERE kind=? AND id=?').run(start, id);
      if (kind === 'native-call') this.db.prepare('UPDATE source_requests SET nativeBound=1 WHERE callId=?').run(id);
      if (ownsTransaction) this.db.exec('COMMIT'); return clone(data);
    } catch (error) { if (ownsTransaction && this.db.isTransaction) this.db.exec('ROLLBACK'); throw error; }
  }
  one(kind, id) { const row = this.db.prepare('SELECT data,digest FROM records WHERE kind=? AND id=?').get(kind, id); if (!row) return null; const data = JSON.parse(row.data); need(hash(data) === row.digest, 'RECORD_DIGEST_MISMATCH'); return data; }
  list(kind) { return this.db.prepare('SELECT id,data FROM records WHERE kind=? ORDER BY n').all(kind).map(r => ({ id: r.id, data: this.one(kind, r.id) })); }
  pending(kind, completedKind) {
    need(({ 'native-call': 'native-complete', 'projection-plan': 'projection-observed' })[kind] === completedKind, 'PENDING_QUERY_CONTRACT');
    const rows = this.db.prepare('SELECT id FROM work_pending WHERE kind=? AND active=1 ORDER BY id LIMIT ?').all(kind, this.workEvents + 1);
    need(rows.length <= this.workEvents, 'PENDING_WORK_BUDGET_HOLD'); return rows.map(r => ({ id: r.id, data: this.one(kind, r.id) }));
  }
  checkpoint() { const row = this.db.prepare('SELECT data,digest FROM checkpoints ORDER BY n DESC LIMIT 1').get(); if (row) { const data = JSON.parse(row.data); need(hash(data) === row.digest, 'CHECKPOINT_DIGEST_MISMATCH'); return data; } return { boundary: 0, chainDigest: ZERO, headerDigest: null, replaceGeneration: 0, contentGeneration: 0, parser: null }; }
  event(seq) { const row = this.db.prepare('SELECT json,digest FROM originals WHERE seq=?').get(seq); need(row, 'SOURCE_EVENT_MISSING'); const event = JSON.parse(row.json); need(hash(event) === row.digest, 'SOURCE_EVENT_DIGEST_MISMATCH'); return event; }
  findEvents({ type, turn, callId, after = -1, before = Number.MAX_SAFE_INTEGER, latest = false }) {
    need(typeof type === 'string', 'EVENT_TYPE_REQUIRED');
    let rows;
    if (callId !== undefined) {
      rows = type === 'assistant/message'
        ? this.db.prepare('SELECT assistantSeq AS seq FROM source_requests WHERE callId=? AND assistantSeq>? AND assistantSeq<?').all(callId, after, before)
        : this.db.prepare('SELECT seq FROM originals WHERE callId=? AND type=? AND seq>? AND seq<? ORDER BY seq LIMIT ?').all(callId, type, after, before, this.workEvents + 1);
      if (turn !== undefined) rows = rows.filter(r => this.event(r.seq).data.turn === turn);
    } else if (turn !== undefined) rows = this.db.prepare(`SELECT seq FROM originals WHERE type=? AND turn=? AND seq>? AND seq<? ORDER BY seq ${latest ? 'DESC' : 'ASC'} LIMIT ?`).all(type, turn, after, before, latest ? 1 : this.workEvents + 1);
    else rows = this.db.prepare(`SELECT seq FROM originals WHERE type=? AND seq>? AND seq<? ORDER BY seq ${latest ? 'DESC' : 'ASC'} LIMIT ?`).all(type, after, before, latest ? 1 : this.workEvents + 1);
    need(rows.length <= this.workEvents, 'EVENT_QUERY_BUDGET_HOLD'); return rows.map(r => this.event(r.seq));
  }
  pendingSourceRequests() {
    const rows = this.db.prepare(`SELECT * FROM source_requests WHERE nativeBound=0 AND owned=1 ORDER BY assistantSeq LIMIT ?`).all(this.workEvents + 1);
    need(rows.length <= this.workEvents, 'PENDING_SOURCE_WORK_BUDGET_HOLD'); return rows;
  }
  currentNodes() { const rows = this.db.prepare('SELECT seq FROM nodes WHERE active=1 ORDER BY pos LIMIT ?').all(this.workEvents + 1); need(rows.length <= this.workEvents, 'SURFACE_WORK_BUDGET_HOLD'); return rows.map(r => r.seq); }
  currentMessages() { this.healthy(); const values = this.currentNodes().map(seq => message(this.event(seq))); need(size(values) <= this.pageBytes, 'CURRENT_REQUEST_BYTES_HOLD'); return values; }
  visibleIndexIds() { return this.currentNodes().map(seq => this.event(seq)).filter(e => e.type === 'user/message' && e.data.source?.kind === VERSION).map(e => e.data.source.indexId); }
  _surface(event, state) {
    need(event.surfaceOp === 'append', 'UNPLANNED_SURFACE_TRANSFORM_HELD');
    const m = message(event); need(m?.role === ({ 'system/message': 'system', 'user/message': 'user', 'assistant/message': 'assistant', 'tool/result': 'tool' })[event.type] && typeof m.id === 'string' && Array.isArray(m.content), 'SURFACE_MESSAGE_SHAPE');
    if (event.type === 'system/message') need(this.db.prepare('SELECT count(*) AS n FROM nodes').get().n === 0, 'SYSTEM_POLICY_CHANGE_REQUIRES_SEPARATE_MIGRATION');
    const pos = this.db.prepare('SELECT COALESCE(MAX(pos),-1)+1 AS p FROM nodes').get().p;
    this.db.prepare('INSERT INTO nodes(seq,pos,active) VALUES(?,?,1)').run(event.seq, pos);
    if (state.parser && event.type !== 'system/message') { state.parser.firstSurface ??= event.seq; state.parser.lastSurface = event.seq; }
  }
  _inbox(event, state) {
    // Public ReactLoopInbox.mutate / inboxProjectionDefinition: an immediate
    // durable queue mutation, not a surface message or evidence of execution.
    // Keep full messages unchanged in originals; only pending IDs are needed
    // here to check normalized bounds and uniqueness across both queues.
    logOnly(event);
    const d = event.data;
    need(object(d) && Object.keys(d).every(key => ['target', 'start', 'removedCount', 'inserted', 'outcome'].includes(key)) && ['next-turn', 'next-step'].includes(d.target) && Array.isArray(d.inserted), 'INBOX_SPLICE_SHAPE_HELD');
    const inbox = state.inboxIds ?? { 'next-turn': [], 'next-step': [] }, pending = inbox[d.target];
    const removed = d.removedCount === undefined ? 0 : d.removedCount;
    need(Number.isSafeInteger(d.start) && d.start >= 0 && d.start <= pending.length && Number.isSafeInteger(removed) && removed >= 0 && removed <= pending.length - d.start, 'INBOX_SPLICE_BOUNDS_HELD');
    need((d.outcome === undefined || (d.outcome === 'canceled' && removed > 0)) && (removed > 0 || d.inserted.length > 0), 'INBOX_SPLICE_OUTCOME_HELD');
    for (const m of d.inserted) need(object(m) && m.role === 'user' && nonempty(m.id) && object(m.source) && nonempty(m.source.kind) && Array.isArray(m.content), 'INBOX_USER_MESSAGE_SHAPE_HELD');
    const next = [...pending.slice(0, d.start), ...d.inserted.map(m => m.id), ...pending.slice(d.start + removed)];
    const ids = [...next, ...inbox[d.target === 'next-turn' ? 'next-step' : 'next-turn']];
    need(new Set(ids).size === ids.length, 'INBOX_DUPLICATE_PENDING_MESSAGE_ID_HELD');
    state.inboxIds = { ...inbox, [d.target]: next };
  }
  _fold(event, state) {
    if (event.type === 'user/message' && event.data?.source?.kind === VERSION) return this._observeReplacement(event, state);
    if (event.type === 'session/end-seed') {
      // Clean restore boundary only. This records lifecycle history; it never
      // clears pending work, grants writer ownership, or turns unknown into done.
      logOnly(event); need(!state.parser && object(event.data) && Object.keys(event.data).length === 0 && event.ignorable === undefined, 'UNSUPPORTED_SEED_BOUNDARY_HELD');
      return;
    }
    if (event.type === 'agent/inbox/spliced') return this._inbox(event, state);
    if (SURFACE.includes(event.type)) this._surface(event, state);
    const d = event.data, p = state.parser;
    if (event.type === 'request/header') {
      logOnly(event);
      need(object(d) && object(d.header) && object(d.header.config) && (d.header.tools === undefined || Array.isArray(d.header.tools)) && (d.header.adapterDefaults === undefined || object(d.header.adapterDefaults)) && d.header.system === undefined, 'REQUEST_HEADER_SHAPE_HELD');
      // Old explicit-local fixtures omit reason inside their turn. Only the
      // four public rc5 reasons admit a header outside a turn; no catch-all.
      need((d.reason === undefined && p) || ['initial', 'resume', 'change', 'series'].includes(d.reason), 'REQUEST_HEADER_REASON_HELD');
      need(d.startsSeries === undefined || d.startsSeries === true, 'REQUEST_HEADER_SERIES_HELD');
      return;
    }
    if (event.type === 'turn/start') {
      need(!p && Number.isSafeInteger(d.turn) && !this.db.prepare('SELECT 1 FROM turns WHERE turn=?').get(d.turn), 'OVERLAPPING_OR_REUSED_TURN');
      state.parser = { turn: d.turn, startSeq: event.seq, step: null, pending: {}, firstSurface: null, lastSurface: null, userCount: 0 }; return;
    }
    if (event.type === 'system/message' && !p) return;
    need(p, 'UNSUPPORTED_OUTSIDE_TURN_EVENT');
    if (event.type === 'request/context') {
      logOnly(event);
      need(p.step !== null && object(d) && nonempty(d.provider) && nonempty(d.model) && (d.contextWindow === undefined || (Number.isSafeInteger(d.contextWindow) && d.contextWindow > 0)) && (d.systemPromptUpdate === undefined || d.systemPromptUpdate === 'in-history'), 'REQUEST_CONTEXT_SHAPE_OR_STEP_HELD');
      return;
    }
    if (event.type === 'system/message') { need(p.step !== null && d.turn === p.turn && d.step === p.step, 'TURN_STEP_LINEAGE_MISMATCH'); return; }
    if (event.type === 'user/message') { need(event.sourceEventSeqs === undefined, 'ATTRIBUTED_USER_REQUIRES_REVIEW'); p.userCount++; p.dispatchId = event.data.source?.ticketId ?? p.dispatchId; return; }
    if (event.type === 'step/start') { need(p.step === null && d.turn === p.turn && Number.isSafeInteger(d.step), 'INVALID_STEP_START'); p.step = d.step; p.pending = {}; return; }
    if (['assistant/message', 'tool/call', 'tool/result', 'step/end'].includes(event.type)) need(p.step !== null && d.turn === p.turn && d.step === p.step, 'TURN_STEP_LINEAGE_MISMATCH');
    if (event.type === 'assistant/message') {
      need(event.sourceEventSeqs === undefined && d.interrupted !== true && d.message.source?.kind === 'model', 'INTERRUPTED_OR_TRANSFORMED_ASSISTANT_HELD');
      need(Object.values(p.pending).every(c => c.resultSeq !== undefined), 'ASSISTANT_WITH_UNRESOLVED_TOOLS');
      for (const block of d.message.content.filter(b => b.type === 'tool-call')) {
        need(typeof block.id === 'string' && typeof block.name === 'string' && typeof block.arguments === 'string' && !p.pending[block.id], 'TOOL_REQUEST_INVALID');
        p.pending[block.id] = { name: block.name, arguments: block.arguments, assistantSeq: event.seq };
        this.db.prepare('INSERT INTO source_requests(callId,assistantSeq,turn,step,dispatchId,name,owned,nativeBound,closed) VALUES(?,?,?,?,?,?,?,0,0)').run(block.id, event.seq, p.turn, p.step, p.dispatchId ?? null, block.name, this.one('native-dispatch', p.dispatchId ?? '') ? 1 : 0);
      }
    } else if (event.type === 'tool/call') {
      const c = p.pending[d.callId]; need(c && c.name === d.name && c.arguments === d.arguments && c.callSeq === undefined, 'TOOL_CALL_SOURCE_MISMATCH'); c.callSeq = event.seq; this.db.prepare('UPDATE source_requests SET callSeq=? WHERE callId=?').run(event.seq, d.callId);
    } else if (event.type === 'tool/result') {
      const m = d.message, c = p.pending[m.toolCallId];
      need(!['TOOL_OUTCOME_UNKNOWN', 'TOOL_NOT_STARTED'].includes(d.error?.code), 'UNRESOLVED_RECOVERY_ANCHOR_HELD');
      need(c && c.callSeq !== undefined && c.resultSeq === undefined && m.source?.kind === 'tool' && m.source.callId === m.toolCallId && hash(event.sourceEventSeqs) === hash([c.callSeq]) && typeof m.isError === 'boolean', 'TOOL_RESULT_SOURCE_MISMATCH');
      c.resultSeq = event.seq; this.db.prepare('UPDATE source_requests SET resultSeq=? WHERE callId=?').run(event.seq, m.toolCallId);
    } else if (event.type === 'step/end') { need(Object.values(p.pending).every(c => c.callSeq !== undefined && c.resultSeq !== undefined), 'INCOMPLETE_TOOL_GROUP_HELD'); this.db.prepare('UPDATE source_requests SET closed=1 WHERE turn=? AND step=?').run(p.turn, p.step); p.step = null; }
    else if (event.type === 'turn/end') {
      need(p.step === null && d.turn === p.turn && d.reason?.kind === 'completed' && p.userCount > 0 && p.firstSurface !== null, 'INCOMPLETE_TURN_HELD');
      this.db.prepare('INSERT INTO turns(turn,startSeq,endSeq,firstSurface,lastSurface) VALUES(?,?,?,?,?)').run(p.turn, p.startSeq, event.seq, p.firstSurface, p.lastSurface); state.parser = null;
    } else need(['assistant/message', 'tool/call', 'tool/result'].includes(event.type), 'UNKNOWN_OR_CONTENT_PROJECTION_HELD');
  }
  _ingest(events, headerDigest) {
    const state = this.checkpoint(); state.headerDigest ??= headerDigest; need(state.headerDigest === headerDigest, 'SOURCE_HEADER_CHANGED');
    this.db.exec('BEGIN IMMEDIATE');
    try {
      for (const event of events) {
        need(event.seq === state.boundary && typeof event.type === 'string', 'SOURCE_SEQUENCE_GAP');
        const digest = hash(event); state.chainDigest = hash([state.chainDigest, event.seq, digest]);
        const turn = event.data?.turn ?? state.parser?.turn ?? null, callId = event.type === 'tool/call' ? event.data.callId : event.type === 'tool/result' ? event.data.message?.toolCallId : null;
        this.db.prepare('INSERT INTO originals(seq,type,turn,callId,json,digest,chain) VALUES(?,?,?,?,?,?,?)').run(event.seq, event.type, turn, callId, JSON.stringify(event), digest, state.chainDigest);
        this._fold(event, state); state.boundary++;
      }
      state.nodesDigest = hash(this.currentNodes()); this.db.prepare('INSERT INTO checkpoints(boundary,data,digest) VALUES(?,?,?)').run(state.boundary, JSON.stringify(state), hash(state)); this.db.exec('COMMIT');
    } catch (error) { this.db.exec('ROLLBACK'); throw error; }
  }
  async sync() {
    try { this.healthy(); need(!this.syncing, 'CONCURRENT_SYNC_HELD'); } catch (error) { this.hold(error.message); } this.syncing = true; let handle;
    try {
      need(await this.persistenceCtx.sessions.flush(this.session) === true, 'SOURCE_FLUSH_NOT_PARTICIPATING'); this.assertOwner();
      const boundary = this.session.seq, before = await this.persistenceCtx.sessionPersistence.stat(this.identity.sessionId), headerDigest = hash(before?.header);
      need(Number.isSafeInteger(boundary) && boundary >= this.checkpoint().boundary && before?.header?.id === this.identity.sessionId, 'SOURCE_BOUNDARY_OR_HEADER_MISMATCH');
      handle = await this.persistenceCtx.sessionPersistence.open(this.identity.sessionId, 'read');
      // A newly attached official session may have only its durable file header.
      // Pin it even with zero events; otherwise first baseline stores null and
      // a later cold resume cannot prove the same source identity.
      if (boundary === 0 && this.checkpoint().headerDigest === null) this._ingest([], headerDigest);
      let offset = this.audited ? this.checkpoint().boundary : 0, chain = ZERO;
      while (offset < boundary) {
        const count = Math.min(this.pageSize, boundary - offset), page = await handle.read(offset, count);
        need(Array.isArray(page.events) && page.events.length > 0 && page.events.length <= count && size(page.events) <= this.pageBytes, 'SOURCE_PAGE_RESOURCE_OR_SHAPE_HOLD');
        let fresh = [];
        for (const e of page.events) {
          need(e.seq === offset++, 'SOURCE_SEQUENCE_GAP');
          if (e.seq < this.checkpoint().boundary && !fresh.length) {
            const row = this.db.prepare('SELECT digest,chain FROM originals WHERE seq=?').get(e.seq); chain = hash([chain, e.seq, hash(e)]);
            need(row && row.digest === hash(e) && row.chain === chain, 'RESTORED_SOURCE_PREFIX_CHANGED');
          } else fresh.push(e);
        }
        if (fresh.length) this._ingest(fresh, headerDigest);
      }
      need(this.checkpoint().boundary === boundary && (this.checkpoint().headerDigest === null || this.checkpoint().headerDigest === headerDigest), 'SOURCE_CHECKPOINT_MISMATCH');
      const checkpoint = this.checkpoint(); if (checkpoint.boundary) { const tail = this.db.prepare('SELECT chain FROM originals WHERE seq=?').get(checkpoint.boundary - 1); need(tail?.chain === checkpoint.chainDigest && hash(this.currentNodes()) === checkpoint.nodesDigest, 'SOURCE_DERIVED_CHECKPOINT_MISMATCH'); }
      const after = await this.persistenceCtx.sessionPersistence.stat(this.identity.sessionId); this.assertOwner();
      need(this.session.seq === boundary && hash(after?.header) === headerDigest, 'SOURCE_CHANGED_DURING_SYNC'); this.audited = true; return this.checkpoint();
    } catch (error) { this.hold(error.message); }
    finally { try { await handle?.close(); } catch { this.hold('SOURCE_HANDLE_CLOSE_FAILED'); } finally { this.syncing = false; } }
  }
  _index(indexId) { const row = this.db.prepare('SELECT data,digest FROM indices WHERE id=?').get(indexId); need(row, 'INDEX_NOT_FOUND'); const index = JSON.parse(row.data); need(hash(index) === row.digest && SCOPE.every(k => index.identity[k] === this.identity[k]), 'INDEX_SCOPE_OR_DIGEST_MISMATCH'); return index; }
  prepare({ retainTurns = 2, maxTurns = 8 } = {}) {
    this.healthy(); need(this.audited && !this.checkpoint().parser, 'COMPLETED_SOURCE_REQUIRED'); retainTurns = positive(retainTurns); maxTurns = positive(maxTurns);
    need(this.pending('projection-plan', 'projection-observed').length === 0, 'UNOBSERVED_PROJECTION_HOLD');
    const head = this.db.prepare('SELECT indexId,eventSeq FROM observations ORDER BY eventSeq DESC LIMIT 1').get(), previous = head ? this._index(head.indexId) : null;
    const eligible = this.db.prepare('SELECT count(*) AS n FROM turns WHERE endSeq>?').get(previous?.rangeEnd ?? -1).n - retainTurns;
    if (eligible <= 0) return null;
    const turns = this.db.prepare('SELECT * FROM turns WHERE endSeq>? ORDER BY endSeq LIMIT ?').all(previous?.rangeEnd ?? -1, Math.min(eligible, maxTurns));
    const first = turns[0], last = turns.at(-1), nodes = this.currentNodes(), startSeq = head?.eventSeq ?? first.firstSurface, start = nodes.indexOf(startSeq), end = nodes.indexOf(last.lastSurface);
    need(start >= 1 && end >= start, 'PROJECTION_MUST_PRESERVE_SYSTEM_HEAD');
    const covered = nodes.slice(start, end + 1), expected = this.db.prepare('SELECT seq FROM nodes WHERE active=1 AND seq>=? AND seq<=? AND seq<>? ORDER BY pos').all(first.firstSurface, last.lastSurface, head?.eventSeq ?? -1).map(r => r.seq);
    need(hash(covered) === hash([...(head ? [head.eventSeq] : []), ...expected]), 'PROJECTION_INTERVAL_NOT_COMPLETE');
    const checkpoint = this.checkpoint();
    const material = { version: VERSION, identity: this.identity, headerDigest: checkpoint.headerDigest, rangeStart: first.startSeq, rangeEnd: last.endSeq, sourceBoundary: checkpoint.boundary, sourceChainDigest: checkpoint.chainDigest, children: previous ? [previous.indexId] : [], coveredSurface: covered };
    const indexId = 'rolling-index:' + hash(material), index = { ...material, indexId };
    const replacement = { type: 'user/message', data: { id: 'rolling-reference:' + hash(material), role: 'user', source: { kind: VERSION, indexId, ...this.identity }, content: [{ type: 'text', text: JSON.stringify({ kind: 'exact-history-index', indexId, note: 'Exact original messages, tool calls/results and source events remain retained. This is a host index, not a summary or decision. Use indexed history tools; prior indices remain children.' }) }] }, surfaceOp: { op: 'replace', startSeq, endSeq: last.lastSurface }, sourceEventSeqs: covered };
    const plan = { version: VERSION, indexId, checkpoint, nodesDigest: hash(nodes), replacement, officialAppendAllowed: false };
    need(size(plan) <= this.pageBytes, 'PROJECTION_WORK_BYTES_HOLD');
    this.db.exec('BEGIN IMMEDIATE'); try { this.db.prepare('INSERT INTO indices VALUES(?,?,?)').run(indexId, JSON.stringify(index), hash(index)); this.put('projection-plan', indexId, plan); this.db.exec('COMMIT'); } catch (error) { this.db.exec('ROLLBACK'); this.hold(error.message); }
    this.issuedPlans.set(plan, hash(plan)); return plan;
  }
  verifyPlan(plan) {
    this.healthy(); need(this.audited && this.issuedPlans.get(plan) === hash(plan), 'PLAN_NOT_ISSUED_OR_RESTARTED');
    need(hash(this.one('projection-plan', plan.indexId)) === hash(plan) && hash(this.checkpoint()) === hash(plan.checkpoint) && hash(this.currentNodes()) === plan.nodesDigest && this.session.seq === plan.checkpoint.boundary, 'PLAN_SOURCE_OR_SURFACE_STALE');
    return plan;
  }
  _observeReplacement(event, state) {
    need(!state.parser, 'REPLACEMENT_DURING_TURN_HELD');
    const indexId = event.data.source.indexId, plan = this.one('projection-plan', indexId); need(plan, 'UNOWNED_REPLACEMENT_HELD');
    const { seq } = event;
    need(seq === plan.checkpoint.boundary, 'REPLACEMENT_BOUNDARY_MISMATCH');
    need(matchesReplacementIntent(event, plan.replacement), 'REPLACEMENT_INTENT_MISMATCH');
    need(hash(this.currentNodes()) === plan.nodesDigest, 'REPLACEMENT_SURFACE_MISMATCH');
    need(state.replaceGeneration === plan.checkpoint.replaceGeneration && state.contentGeneration === plan.checkpoint.contentGeneration, 'REPLACEMENT_GENERATION_MISMATCH');
    const nodes = this.currentNodes(), start = nodes.indexOf(event.surfaceOp.startSeq), end = nodes.indexOf(event.surfaceOp.endSeq); need(start >= 1 && end >= start && hash(nodes.slice(start, end + 1)) === hash(event.sourceEventSeqs), 'REPLACEMENT_COVERAGE_MISMATCH');
    const pos = this.db.prepare('SELECT pos FROM nodes WHERE seq=? AND active=1').get(nodes[start]).pos;
    for (const shadow of nodes.slice(start, end + 1)) this.db.prepare('UPDATE nodes SET active=0 WHERE seq=?').run(shadow);
    this.db.prepare('INSERT INTO nodes VALUES(?,?,1)').run(seq, pos); this.db.prepare('INSERT INTO observations VALUES(?,?,?)').run(indexId, seq, hash(event));
    this.put('projection-observed', indexId, { eventSeq: seq, eventDigest: hash(event) }); state.replaceGeneration++; state.contentGeneration++;
  }
  async reconcilePendingProjection() {
    // If append succeeded before a process loss, source sync observes it exactly.
    // Missing or changed append never authorizes replay of the old intent.
    await this.sync(); const pending = this.pending('projection-plan', 'projection-observed');
    if (pending.length) this.hold('PROJECTION_OUTCOME_UNKNOWN_NO_REPLAY');
    return this.checkpoint();
  }
  _bounded(value) { need(size(value) <= this.responseBytes, 'READ_RESPONSE_BYTES_HOLD'); return value; }
  _base(index, operation) { return { version: VERSION, ...this.identity, indexId: index.indexId, operation, headerDigest: index.headerDigest, sourceBoundary: index.sourceBoundary, sourceChainDigest: index.sourceChainDigest }; }
  _cursor(raw, stage, indexId, binding) { if (raw === undefined) return 0; const c = this.cursors.get(raw); need(c && c.stage === stage && c.indexId === indexId && c.binding === binding, 'CURSOR_NOT_ISSUED'); return c.offset; }
  readIndex({ indexId, pageSize, cursor }) {
    this.healthy(); need(this.audited, 'COLD_SOURCE_AUDIT_REQUIRED'); const index = this._index(indexId), count = Math.min(positive(pageSize, 16), this.workEvents), offset = this._cursor(cursor, 'index', indexId, indexId);
    const rows = this.db.prepare('SELECT seq,type,digest FROM originals WHERE seq>=? AND seq<=? ORDER BY seq LIMIT ?').all(index.rangeStart + offset, index.rangeEnd, count), entries = [];
    const make = () => ({ ...this._base(index, 'read_index'), startOffset: offset, endOffset: offset + entries.length, children: offset === 0 ? index.children.map(indexId => ({ indexId })) : [], entries, nextCursor: offset + entries.length < index.rangeEnd - index.rangeStart + 1 ? 'cursor:' + hash([indexId, 'index', offset + entries.length]) : null });
    for (const row of rows) { entries.push({ seq: row.seq, type: row.type, eventDigest: row.digest, hitHandle: 'hit:' + hash([indexId, row.seq, row.digest]) }); if (size(make()) > this.responseBytes) { entries.pop(); break; } }
    need(entries.length || offset === index.rangeEnd - index.rangeStart + 1, 'READ_RESPONSE_BYTES_HOLD'); const result = this._bounded(make());
    for (const e of entries) this.hits.set(e.hitHandle, { indexId, seq: e.seq });
    if (result.nextCursor) this.cursors.set(result.nextCursor, { stage: 'index', indexId, binding: indexId, offset: offset + entries.length }); return result;
  }
  _fragment(index, seq, raw, operation, binding, offset, pageChars, extra = {}) {
    const points = Array.from(raw), length = Math.min(positive(pageChars, 512), points.length - offset); need(length >= 0, 'READ_OFFSET_INVALID');
    const make = count => ({ ...this._base(index, operation), stageBinding: binding, seq, eventDigest: hash(this.event(seq)), ...extra, offsetUnit: 'unicode-code-points', startOffset: offset, endOffset: offset + count, totalChars: points.length, fragment: points.slice(offset, offset + count).join(''), nextCursor: offset + count < points.length ? 'cursor:' + hash([index.indexId, operation, binding, offset + count]) : null });
    let n = length; while (n > 0 && size(make(n)) > this.responseBytes) n = Math.floor(n / 2);
    need(n > 0 || offset === points.length, 'READ_RESPONSE_BYTES_HOLD'); const result = this._bounded(make(n));
    if (result.nextCursor) this.cursors.set(result.nextCursor, { stage: operation, indexId: index.indexId, binding, offset: offset + n }); return result;
  }
  reissuePage(result) {
    // Host seam only: the native adapter first verifies the exact persisted body
    // against its source-observed result. Model-supplied pages never enter here.
    this.healthy(); need(this.audited && SCOPE.every(k => result[k] === this.identity[k]) && result.version === VERSION, 'REISSUE_SCOPE_MISMATCH');
    const index = this._index(result.indexId); need(result.sourceChainDigest === index.sourceChainDigest && result.headerDigest === index.headerDigest, 'REISSUE_SOURCE_MISMATCH');
    if (result.operation === 'read_index') {
      for (const e of result.entries) { need(hash(this.event(e.seq)) === e.eventDigest && e.hitHandle === 'hit:' + hash([index.indexId, e.seq, e.eventDigest]) && e.seq >= index.rangeStart && e.seq <= index.rangeEnd, 'REISSUE_ENTRY_MISMATCH'); this.hits.set(e.hitHandle, { indexId: index.indexId, seq: e.seq }); }
      if (result.nextCursor) { need(result.nextCursor === 'cursor:' + hash([index.indexId, 'index', result.endOffset]), 'REISSUE_CURSOR_MISMATCH'); this.cursors.set(result.nextCursor, { stage: 'index', indexId: index.indexId, binding: index.indexId, offset: result.endOffset }); }
    } else {
      need(['preview', 'original'].includes(result.operation) && hash(this.event(result.seq)) === result.eventDigest, 'REISSUE_EVENT_MISMATCH');
      if (result.operation === 'preview') { const ref = { indexId: index.indexId, seq: result.seq }; need(result.readHandle === 'read:' + hash([result.stageBinding, ref]), 'REISSUE_READ_HANDLE_MISMATCH'); this.reads.set(result.readHandle, ref); }
      if (result.nextCursor) { need(result.nextCursor === 'cursor:' + hash([index.indexId, result.operation, result.stageBinding, result.endOffset]), 'REISSUE_CURSOR_MISMATCH'); this.cursors.set(result.nextCursor, { stage: result.operation, indexId: index.indexId, binding: result.stageBinding, offset: result.endOffset }); }
    }
  }
  preview({ hitHandle, pageChars, cursor }) {
    this.healthy(); const hit = this.hits.get(hitHandle); need(hit, 'INDEX_STAGE_REQUIRED'); const index = this._index(hit.indexId), event = this.event(hit.seq), raw = JSON.stringify(message(event)?.content ?? event.data), excerpt = Array.from(raw).slice(0, 512).join('');
    const readHandle = 'read:' + hash([hitHandle, hit]), offset = this._cursor(cursor, 'preview', index.indexId, hitHandle);
    const result = this._fragment(index, hit.seq, excerpt, 'preview', hitHandle, offset, pageChars, { previewKind: 'exact-mechanical-excerpt', readHandle, excerptComplete: Array.from(raw).length <= 512 }); this.reads.set(readHandle, hit); return result;
  }
  readOriginal({ readHandle, relevance, pageChars, cursor }) {
    this.healthy(); need(typeof relevance === 'string' && relevance.trim(), 'RELEVANCE_REQUIRED'); const ref = this.reads.get(readHandle); need(ref, 'PREVIEW_STAGE_REQUIRED'); const index = this._index(ref.indexId), binding = hash([readHandle, relevance]), offset = this._cursor(cursor, 'original', index.indexId, binding);
    return this._fragment(index, ref.seq, JSON.stringify(this.event(ref.seq)), 'original', binding, offset, pageChars, { fullEvent: true, serialization: 'JSON.stringify(original complete event)' });
  }
}
