import { DatabaseSync } from 'node:sqlite';
import { randomUUID } from 'node:crypto';

// Experimental local persistence, not a model, scheduler, or security boundary.
export class Memory {
  constructor(path) {
    this.db = new DatabaseSync(path);
    this.db.exec(`PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;
      CREATE TABLE IF NOT EXISTS events (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
        time TEXT NOT NULL, kind TEXT NOT NULL, subject TEXT NOT NULL, data TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS events_kind_subject_seq ON events(kind,subject,seq);
      CREATE INDEX IF NOT EXISTS events_kind_seq ON events(kind,seq);
      CREATE TRIGGER IF NOT EXISTS immutable_update BEFORE UPDATE ON events
        BEGIN SELECT RAISE(ABORT, 'append only'); END;
      CREATE TRIGGER IF NOT EXISTS immutable_delete BEFORE DELETE ON events
        BEGIN SELECT RAISE(ABORT, 'append only'); END;`);
  }
  append(kind, subject, data, id = randomUUID()) {
    const body = JSON.stringify(data);
    const old = this.db.prepare('SELECT * FROM events WHERE id=?').get(id);
    if (old) {
      if (old.kind !== kind || old.subject !== subject || old.data !== body)
        throw new Error('idempotency key reused for different content');
      return old.id;
    }
    this.db.prepare('INSERT INTO events(id,time,kind,subject,data) VALUES(?,?,?,?,?)')
      .run(id, new Date().toISOString(), kind, subject, body);
    return id;
  }
  events(kind) {
    const rows = kind ? this.db.prepare('SELECT * FROM events WHERE kind=? ORDER BY seq').all(kind)
      : this.db.prepare('SELECT * FROM events ORDER BY seq').all();
    return rows.map(r => ({ ...r, data: JSON.parse(r.data) }));
  }
  one(kind, subject) {
    const row = this.db.prepare('SELECT * FROM events WHERE kind=? AND subject=? ORDER BY seq DESC LIMIT 1').get(kind, subject);
    return row ? { ...row, data: JSON.parse(row.data) } : null;
  }
  bounds(limit = 20, after = 0) {
    if (!Number.isSafeInteger(limit) || limit < 1 || limit > 100 || !Number.isSafeInteger(after) || after < 0)
      throw new Error('invalid page bounds');
  }
  paragraph(text, { id = randomUUID(), chain = null, predecessor = null } = {}) {
    if (typeof text !== 'string' || !text.trim()) throw new Error('empty paragraph');
    if (chain !== null && !this.one('chain-open', chain)) throw new Error('unknown chain');
    if (predecessor !== null) this.read(predecessor);
    this.append('paragraph', id, { text, chain, predecessor }, `paragraph:${id}`);
    return id;
  }
  read(id) {
    const row = this.one('paragraph', id);
    if (!row) throw new Error('unknown paragraph');
    return row;
  }
  describe(id, description, terms) {
    this.read(id);
    if (typeof description !== 'string' || !description.trim() || !Array.isArray(terms) ||
        !terms.length || terms.some(t => typeof t !== 'string' || !t.trim()))
      throw new Error('description and index terms required');
    return this.append('description', id, { description, terms, source: 'logic-provided' });
  }
  catalog(limit = 20, after = 0, mode = 'all', term = '') {
    this.bounds(limit, after);
    if (!['all', 'missing', 'search'].includes(mode)) throw new Error('invalid catalog mode');
    const rows = this.db.prepare(`SELECT p.subject AS id,p.seq,json_extract(p.data,'$.chain') AS chain,
      d.data AS metadata FROM events p LEFT JOIN events d ON d.seq=(SELECT MAX(seq) FROM events
      WHERE kind='description' AND subject=p.subject)
      WHERE p.kind='paragraph' AND p.seq>? AND
      (?='all' OR (?='missing' AND d.seq IS NULL) OR (?='search' AND EXISTS
        (SELECT 1 FROM json_each(d.data,'$.terms') WHERE value=?))) ORDER BY p.seq LIMIT ?`)
      .all(after, mode, mode, mode, term, limit);
    return rows.map(r => ({ id: r.id, seq: r.seq, chain: r.chain,
      description: r.metadata ? JSON.parse(r.metadata).description : null,
      terms: r.metadata ? JSON.parse(r.metadata).terms : [] }));
  }
  missing(limit = 20, after = 0) { return this.catalog(limit, after, 'missing'); }
  search(term, limit = 5, after = 0) {
    if (typeof term !== 'string' || !term.trim()) throw new Error('nonempty exact index term required');
    return this.catalog(limit, after, 'search', term);
  }
  expand(node, chain = randomUUID()) {
    this.read(node);
    this.append('chain-open', chain, { parentNode: node }, `chain:${chain}`);
    return chain;
  }
  progress(chain, node) {
    const paragraph = this.read(node);
    if (!this.one('chain-open', chain)) throw new Error('unknown chain');
    if (paragraph.data.chain !== null && paragraph.data.chain !== chain) throw new Error('node belongs to another chain');
    this.append('chain-progress', chain, { node });
  }
  latestNodes(limit = 100) {
    this.bounds(limit);
    return this.db.prepare(`SELECT DISTINCT json_extract(e.data,'$.node') AS node FROM events e
      WHERE e.kind='chain-progress' AND e.seq=(SELECT MAX(seq) FROM events
      WHERE kind='chain-progress' AND subject=e.subject) ORDER BY e.seq DESC LIMIT ?`).all(limit).map(e => e.node);
  }
  // Returns references only. Caller explicitly reads selected paragraphs, never whole memory.
  context(maxNodes = 8) {
    if (!Number.isSafeInteger(maxNodes) || maxNodes < 1 || maxNodes > 99) throw new Error('invalid budget');
    const current = this.latestNodes(maxNodes + 1);
    if (current.length > maxNodes) return { status: 'capacity-required', requiredAtLeast: current.length, nodes: [] };
    const recent = this.db.prepare("SELECT subject FROM events WHERE kind='paragraph' ORDER BY seq DESC LIMIT ?")
      .all(maxNodes).map(e => e.subject);
    return { status: 'ready', nodes: [...new Set([...current, ...recent])].slice(0, maxNodes) };
  }
  start(call, tool, input) {
    this.append('call-start', call, { tool, input }, `start:${call}`);
  }
  claimStart(call, tool, input) {
    const result = this.db.prepare('INSERT OR IGNORE INTO events(id,time,kind,subject,data) VALUES(?,?,?,?,?)')
      .run(`start:${call}`, new Date().toISOString(), 'call-start', call, JSON.stringify({ tool, input }));
    return result.changes === 1;
  }
  finish(call, status, result) {
    if (!['completed', 'interrupted', 'failed'].includes(status)) throw new Error('invalid terminal state');
    if (!this.one('call-start', call)) throw new Error('call not started');
    this.append('call-end', call, { status, result }, `end:${call}`);
    // Completion is durable before it can become available to the report consumer.
  }
  pending(limit = 20, after = 0) {
    return this.unmatched('call-end', 'report-ack', limit, after);
  }
  async report(currentLogic, send, limit = 20) {
    this.bounds(limit);
    const cursor = this.one('report-scan', 'dispatcher')?.data.after ?? 0;
    const batch = this.db.prepare(`SELECT e.* FROM events e WHERE kind='call-end' AND NOT EXISTS
      (SELECT 1 FROM events d WHERE d.kind='report-ack' AND d.subject=e.subject)
      ORDER BY CASE WHEN e.seq>? THEN 0 ELSE 1 END,e.seq LIMIT ?`).all(cursor, limit)
      .map(e => ({ ...e, data: JSON.parse(e.data) }));
    const failures = []; let delivered = 0;
    for (const e of batch) {
      const recipient = typeof currentLogic === 'function' ? currentLogic() : currentLogic;
      if (!recipient) break;
      this.append('report-scan', 'dispatcher', { after: e.seq });
      try {
        await send({ eventId: e.id, call: e.subject, recipient, ...e.data });
      } catch (error) {
        const failure = { eventId: e.id, message: String(error?.message ?? error) };
        this.append('report-failed', e.subject, failure); failures.push(failure); continue;
      }
      this.append('report-ack', e.subject, { recipient }, `ack:${e.subject}`);
      delivered++;
    }
    // At-least-once: a crash after send but before ack may repeat eventId.
    return { delivered, failures };
  }
  unmatched(kind, completion, limit = 20, after = 0) {
    this.bounds(limit, after);
    return this.db.prepare(`SELECT e.* FROM events e WHERE kind=? AND seq>? AND NOT EXISTS
      (SELECT 1 FROM events d WHERE d.kind=? AND d.subject=e.subject) ORDER BY seq LIMIT ?`)
      .all(kind, after, completion, limit).map(e => ({ ...e, data: JSON.parse(e.data) }));
  }
  unfinished(limit = 20, after = 0) {
    return this.unmatched('call-start', 'call-end', limit, after);
  }
  close() { this.db.close(); }
}
