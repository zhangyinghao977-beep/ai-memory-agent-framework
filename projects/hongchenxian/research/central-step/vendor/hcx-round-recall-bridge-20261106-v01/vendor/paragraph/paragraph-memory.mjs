import { createHash } from 'node:crypto';
import { Memory } from './vendor/memory.mjs';
const hash = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const integer = (n, min = 0) => { if (!Number.isSafeInteger(n) || n < min) throw Error('invalid page/window integer'); return n; };
const encode = value => Buffer.from(JSON.stringify(value)).toString('base64url');
function decode(cursor, binding) {
  let value;
  try { value = JSON.parse(Buffer.from(cursor, 'base64url').toString()); } catch { throw Error('invalid cursor'); }
  if (value.binding !== binding) throw Error('cursor belongs to another query/window');
  return value;
}
// Exact indexing is intentional: no inferred entity equality, translation, stemming or fuzzy recall.
export class ParagraphMemory extends Memory {
  ingestDocument({ documentId, revision, source, text, provenance = {} }) {
    for (const value of [documentId, revision, source, text])
      if (typeof value !== 'string' || !value.length) throw Error('document identity, revision, source and text required');
    const documentKey = hash([documentId, revision]);
    const digest = hash(text);
    const existing = this.one('document', documentKey);
    if (existing) {
      if (existing.data.digest !== digest || existing.data.source !== source || JSON.stringify(existing.data.provenance) !== JSON.stringify(provenance)) throw Error('immutable document revision conflict');
      return existing.data;
    }
    // Preserve exact source bytes as JS UTF-16 offsets; blank-line delimiters belong to preceding paragraph.
    const spans = []; let start = 0;
    for (const match of text.matchAll(/\r?\n[\t ]*\r?\n/g)) {
      const end = match.index + match[0].length;
      spans.push([start, end]); start = end;
    }
    if (start < text.length) spans.push([start, text.length]);
    if (!spans.length) spans.push([0, text.length]);
    this.db.exec('BEGIN IMMEDIATE');
    try {
      const ids = spans.map(([start, end], ordinal) => {
        const id = hash([documentKey, ordinal]);
        // Store raw spans even if whitespace-only: no import-time deletion or trimming.
        this.append('paragraph', id, { text: text.slice(start, end), chain: null, predecessor: ordinal ? hash([documentKey, ordinal - 1]) : null }, `paragraph:${id}`);
        this.append('paragraph-origin', id, { documentKey, documentId, revision, source, ordinal, start, end, digest, provenance }, `origin:${id}`);
        return id;
      });
      const result = { documentKey, documentId, revision, source, digest, provenance, paragraphCount: ids.length, paragraphIds: ids };
      this.append('document', documentKey, result, `document:${documentKey}`);
      this.db.exec('COMMIT'); return result;
    } catch (error) { this.db.exec('ROLLBACK'); throw error; }
  }
  registerIndex({ indexId, refs, summary = null, clerkId, sourceEventId }) {
    for (const value of [indexId, clerkId, sourceEventId])
      if (typeof value !== 'string' || !value.trim()) throw Error('index and clerk provenance required');
    if (!Array.isArray(refs) || refs.some(r => !['index', 'paragraph'].includes(r.kind) || typeof r.id !== 'string' || !r.id)) throw Error('typed index references required');
    if (summary !== null && typeof summary !== 'string') throw Error('summary must be supplied text or null');
    this.db.exec('BEGIN IMMEDIATE');
    try {
      const supersedes = this.one('index-node', indexId)?.id ?? null;
      const eventId = this.append('index-node', indexId, { refs, summary, clerkId, sourceEventId, supersedes });
      this.db.exec('COMMIT'); return eventId;
    } catch (error) { this.db.exec('ROLLBACK'); throw error; }
  }
  readIndex({ indexId, pageSize = 20, pageChars = 4000, cursor = null, snapshotSeq = null }) {
    integer(pageSize, 1); integer(pageChars, 1);
    const binding = hash(['index-v1', indexId]);
    const max = this.db.prepare('SELECT COALESCE(MAX(seq),0) AS seq FROM events').get().seq;
    const state = cursor ? decode(cursor, binding) : { snapshot: snapshotSeq ?? max, refOffset: 0, summaryOffset: 0 };
    integer(state.snapshot); integer(state.refOffset); integer(state.summaryOffset);
    if (state.snapshot > max) throw Error('invalid index snapshot');
    const row = this.db.prepare("SELECT * FROM events WHERE kind='index-node' AND subject=? AND seq<=? ORDER BY seq DESC LIMIT 1").get(indexId, state.snapshot);
    if (!row) return { status: 'missing-index', indexId, snapshotSeq: state.snapshot };
    const node = JSON.parse(row.data), summary = node.summary ?? '';
    if (state.refOffset > node.refs.length || state.summaryOffset > summary.length) throw Error('invalid index cursor offsets');
    if (state.summaryOffset > 0 && /[\uDC00-\uDFFF]/.test(summary[state.summaryOffset]) && /[\uD800-\uDBFF]/.test(summary[state.summaryOffset-1])) throw Error('invalid index cursor surrogate offset');
    let end = Math.min(summary.length, state.summaryOffset + pageChars);
    if (end < summary.length && /[\uD800-\uDBFF]/.test(summary[end-1]) && /[\uDC00-\uDFFF]/.test(summary[end])) end--;
    if (end === state.summaryOffset && end < summary.length) end += 2;
    const refs = node.refs.slice(state.refOffset, state.refOffset + pageSize).map((ref, i) => ({...ref, ordinal: state.refOffset + i,
      status: this.db.prepare('SELECT 1 FROM events WHERE kind=? AND subject=? AND seq<=? LIMIT 1').get(ref.kind === 'index' ? 'index-node' : 'paragraph', ref.id, state.snapshot) ? 'available' : 'missing-target' }));
    const next = { binding, snapshot: state.snapshot, refOffset: state.refOffset + refs.length, summaryOffset: end };
    return { status: 'ready', indexId, eventId: row.id, snapshotSeq: state.snapshot, refs,
      summary: node.summary === null ? null : { text: summary.slice(state.summaryOffset, end), start: state.summaryOffset, end, complete: end === summary.length, epistemicStatus: 'clerk-interpretation-not-original-fact' },
      provenance: { clerkId: node.clerkId, sourceEventId: node.sourceEventId, supersedes: node.supersedes },
      nextCursor: next.refOffset < node.refs.length || end < summary.length ? encode(next) : null };
  }
  registerSummary({ paragraphId, text, clerkId, sourceEventId }) {
    this.read(paragraphId);
    for (const value of [text, clerkId, sourceEventId])
      if (typeof value !== 'string' || !value.trim()) throw Error('supplied summary and clerk provenance required');
    return this.append('paragraph-summary', paragraphId, { text, clerkId, sourceEventId, derivedFrom: paragraphId });
  }
  origin(paragraphId) {
    const origin = this.one('paragraph-origin', paragraphId)?.data;
    if (!origin) throw Error('paragraph has no document provenance; explicit migration required');
    return origin;
  }
  lookupParagraphs({ term, pageSize = 20, cursor = null }) {
    if (typeof term !== 'string' || !term.trim()) throw Error('nonempty exact index term required');
    integer(pageSize, 1);
    const binding = hash(['lookup-v1', term]);
    const max = this.db.prepare('SELECT COALESCE(MAX(seq),0) AS seq FROM events').get().seq;
    const state = cursor ? decode(cursor, binding) : { snapshot: max, after: 0 };
    integer(state.snapshot); integer(state.after);
    if (state.snapshot > max || state.after > state.snapshot) throw Error('invalid cursor bounds');
    const rows = this.db.prepare(`SELECT p.subject AS id,p.seq FROM events p
      JOIN events d ON d.seq=(SELECT MAX(seq) FROM events WHERE kind='description' AND subject=p.subject AND seq<=?)
      WHERE p.kind='paragraph' AND p.seq>? AND p.seq<=? AND EXISTS
      (SELECT 1 FROM json_each(d.data,'$.terms') WHERE value=?) ORDER BY p.seq LIMIT ?`)
      .all(state.snapshot, state.after, state.snapshot, term, pageSize + 1);
    const more = rows.length > pageSize; const page = rows.slice(0, pageSize);
    // Metadata descriptions may be arbitrarily large; return only IDs, no full text/definition payload.
    return { matching: 'exact-case-sensitive', snapshot: state.snapshot,
      hits: page.map(({id,seq}) => ({ paragraphId: id, seq, provenance: this.one('paragraph-origin', id)?.data ?? null })),
      nextCursor: more ? encode({ binding, snapshot: state.snapshot, after: page.at(-1).seq }) : null };
  }
  readParagraphWindow({ paragraphId, before = 0, after = 0, pageChars = 4000, cursor = null, neighborMode = 'raw' }) {
    integer(before); integer(after); integer(pageChars, 1);
    if (!['raw', 'summary-preferred'].includes(neighborMode)) throw Error('invalid neighbor mode');
    const anchor = this.origin(paragraphId);
    const documentEvent = this.one('document', anchor.documentKey);
    const doc = documentEvent.data;
    const maxSnapshot = this.db.prepare('SELECT COALESCE(MAX(seq),0) AS seq FROM events').get().seq;
    const low = Math.max(0, anchor.ordinal - before), high = Math.min(doc.paragraphCount - 1, anchor.ordinal + after);
    const binding = hash(['window-v1', paragraphId, before, after, neighborMode]);
    const state = cursor ? decode(cursor, binding) : { ordinal: low, offset: 0, snapshot: maxSnapshot };
    integer(state.ordinal); integer(state.offset); integer(state.snapshot);
    if (state.snapshot > maxSnapshot || state.snapshot < documentEvent.seq) throw Error('invalid window snapshot');
    if (state.ordinal < low || state.ordinal > high) throw Error('invalid cursor ordinal');
    const fragments = []; let budget = pageChars, ordinal = state.ordinal, offset = state.offset;
    while (ordinal <= high && budget > 0) {
      const id = doc.paragraphIds[ordinal]; const origin = this.origin(id);
      const summaryRow = id !== paragraphId && neighborMode === 'summary-preferred' ? this.db.prepare(
        "SELECT * FROM events WHERE kind='paragraph-summary' AND subject=? AND seq<=? ORDER BY seq DESC LIMIT 1"
      ).get(id, state.snapshot) : null;
      const summary = summaryRow ? JSON.parse(summaryRow.data) : null;
      const text = summary ? summary.text : this.read(id).data.text;
      if (offset >= text.length || (offset > 0 && /[\uDC00-\uDFFF]/.test(text[offset]) && /[\uD800-\uDBFF]/.test(text[offset-1]))) throw Error('invalid cursor offset');
      let end = Math.min(text.length, offset + budget);
      if (end < text.length && /[\uD800-\uDBFF]/.test(text[end-1]) && /[\uDC00-\uDFFF]/.test(text[end])) end--;
      // A surrogate pair is indivisible; one-code-unit page may need two units.
      if (end === offset) end = offset + 2;
      const fragment = text.slice(offset, end);
      fragments.push({ paragraphId: id, previousParagraphId: doc.paragraphIds[ordinal-1] ?? null, nextParagraphId: doc.paragraphIds[ordinal+1] ?? null, matched: id === paragraphId, provenance: origin,
        representation: summary ? 'clerk-summary' : 'original',
        summaryMissing: id !== paragraphId && neighborMode === 'summary-preferred' && !summary,
        summaryProvenance: summary ? { eventId: summaryRow.id, clerkId: summary.clerkId, sourceEventId: summary.sourceEventId, derivedFrom: id } : null,
        fragmentStart: offset, fragmentEnd: end, sourceStart: summary ? null : origin.start + offset, sourceEnd: summary ? null : origin.start + end,
        paragraphComplete: offset === 0 && end === text.length, text: fragment });
      budget -= fragment.length;
      if (end < text.length) { offset = end; break; }
      ordinal++; offset = 0;
    }
    return { anchor: paragraphId, window: { low, high }, offsetUnit: 'UTF-16 code units', fragments,
      nextCursor: ordinal <= high ? encode({ binding, ordinal, offset, snapshot: state.snapshot }) : null };
  }
}
export function paragraphToolHandler(memory) {
  return async ({ tool, input }) => {
    if (tool === 'memory.read_index') return memory.readIndex(input);
    if (tool === 'memory.lookup_paragraphs') return memory.lookupParagraphs(input);
    if (tool === 'memory.read_paragraph_window') return memory.readParagraphWindow(input);
    throw Error('unknown paragraph tool');
  };
}
