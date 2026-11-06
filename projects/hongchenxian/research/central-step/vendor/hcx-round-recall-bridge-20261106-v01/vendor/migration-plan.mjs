import { digest } from './recall-adapter.mjs';
const requireValue = (condition, message) => { if (!condition) throw Error(message); };
const clone = value => JSON.parse(JSON.stringify(value));
function records({ paragraphId, paragraphData, documentId, revision, source, provenance }) {
  const documentKey = digest([documentId, revision]), text = paragraphData.text, textDigest = digest(text);
  const origin = { documentKey, documentId, revision, source, ordinal: 0, start: 0, end: text.length, digest: textDigest, provenance };
  return {
    status: 'plan-only-not-applied', paragraphId, originalIdPreserved: true,
    records: [
      { kind: 'paragraph', subject: paragraphId, id: 'paragraph:' + paragraphId, data: clone(paragraphData) },
      { kind: 'paragraph-origin', subject: paragraphId, id: 'origin:' + paragraphId, data: origin },
      { kind: 'document', subject: documentKey, id: 'document:' + documentKey, data: { documentKey, documentId, revision, source, digest: textDigest, provenance, paragraphCount: 1, paragraphIds: [paragraphId] } }
    ],
    missing: ['Actor-authored or explicitly attributed index terms and description', 'Transactional append to NEW correctly scoped sidecar and durable migration receipt', 'Original source verification and all-event coverage accounting']
  };
}
// Never silently assign provenance to legacy paragraphs: a matching authoritative
// Body completion is required. IDs and full original text are kept, not resegmented.
export function planPrivateParagraph({ actorId, sessionId, paragraph, completedSource }) {
  requireValue(typeof actorId === 'string' && actorId && typeof sessionId === 'string' && sessionId, 'identity required');
  requireValue(paragraph?.kind === 'paragraph' && typeof paragraph.data?.text === 'string', 'original paragraph required');
  requireValue(completedSource?.kind === 'body-source' && completedSource.data?.kind === 'completed', 'completed source required');
  const s = completedSource.data;
  requireValue(paragraph.subject === 'thought:' + completedSource.subject && paragraph.data.text === s.choice?.thought, 'legacy paragraph/source mismatch');
  requireValue(s.provenance?.sessionId === sessionId && /^[a-f0-9]{64}$/.test(s.provenance.prefixHash), 'source provenance mismatch');
  const plan = records({ paragraphId: paragraph.subject, paragraphData: paragraph.data,
    documentId: 'body-private-paragraph:' + sessionId + ':' + paragraph.subject, revision: digest(s), source: 'body-source:' + completedSource.id,
    provenance: { ...s.provenance, actorId, sessionId, sourceId: completedSource.subject, sourceEventId: completedSource.id, originalParagraphId: paragraph.subject, sourceKind: 'private-thought' } });
  return { ...plan, scope: { type: 'private', actorId, sessionId }, originalParagraphEventId: paragraph.id, originalParagraphDigest: digest(paragraph.data), sourceDigest: digest(s) };
}
// Deliberate allowlist: never copy the record's raw completion (contains thought)
// or any unexpected field into a shared store. Only explicitly shared text.
export function planSharedRecord({ poolId, sharedRecord }) {
  const s = sharedRecord;
  requireValue(typeof poolId === 'string' && poolId && ['contribute', 'minutes'].includes(s?.kind), 'explicit contribution/minutes required');
  requireValue(typeof s.text === 'string' && s.text.trim() && typeof s.id === 'string' && s.id && typeof s.actorId === 'string' && s.actorId && typeof s.sessionId === 'string' && s.sessionId, 'shared identity/text required');
  requireValue(s.provenance?.sessionId === s.sessionId && /^[a-f0-9]{64}$/.test(s.provenance.prefixHash), 'shared source provenance mismatch');
  const p = s.provenance;
  requireValue(Number.isSafeInteger(p.assistantSeq) && p.assistantSeq >= 0 && Number.isSafeInteger(p.endSeq) && p.endSeq > p.assistantSeq && p.boundary === p.endSeq + 1, 'shared source coordinates required');
  requireValue(typeof s.sourceId === 'string' && s.sourceId && typeof s.ticketId === 'string' && s.ticketId, 'shared source/ticket required');
  requireValue(Array.isArray(s.refs) && s.refs.every(ref => typeof ref === 'string' && ref.trim()) && new Set(s.refs).size === s.refs.length, 'shared references must be strings');
  requireValue(s.kind === 'minutes' ? Number.isSafeInteger(s.epoch) && s.epoch > 0 : s.epoch === null, 'shared epoch mismatch');
  // Strict primitive allowlist at the nested boundary too. Source extensions
  // such as raw, thought, private annotations or objects are never copied.
  const provenance = { sessionId: p.sessionId, assistantSeq: p.assistantSeq, endSeq: p.endSeq, boundary: p.boundary, prefixHash: p.prefixHash };
  const allowed = { id: s.id, actorId: s.actorId, sessionId: s.sessionId, sourceId: s.sourceId, ticketId: s.ticketId, provenance, kind: s.kind, text: s.text, refs: s.refs, epoch: s.epoch };
  const plan = records({ paragraphId: s.id, paragraphData: { text: s.text, chain: null, predecessor: null },
    documentId: 'pool-explicit-shared:' + poolId + ':' + s.id, revision: digest(allowed), source: 'pool-shared:' + s.id,
    provenance: { ...provenance, actorId: s.actorId, sessionId: s.sessionId, sourceId: s.sourceId, ticketId: s.ticketId, originalParagraphId: s.id, sourceKind: 'explicit-shared-text', meetingKind: s.kind, epoch: s.epoch, refs: s.refs } });
  return { ...plan, scope: { type: 'shared', poolId }, sharedRecordDigest: digest(allowed), excludedPrivateRaw: true };
}
