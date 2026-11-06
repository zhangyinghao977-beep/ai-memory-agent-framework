// New-ticket protocol only. Original Body source/paragraph events are retained.
// Import targets must be NEW or already admitted private working copies. This is
// not original-session custody, a migration approval or cryptographic identity.
import {isDeepStrictEqual as equal} from 'node:util';
import {Body,hash} from '../hcx-fish-pool-20261106-v01/body.mjs';
import {ParagraphMemory} from '../hcx-round-recall-bridge-20261106-v01/vendor/paragraph/paragraph-memory.mjs';
import {planPrivateParagraph} from '../hcx-round-recall-bridge-20261106-v01/vendor/migration-plan.mjs';
import {RoundRecallBroker} from '../hcx-round-recall-bridge-20261106-v01/round-recall.mjs';
export const VERSION='hcx-memory-reference/v1';
export const PREPARATION_LOCK=true;
const need=(ok,code)=>{if(!ok)throw Error(code);},clone=x=>JSON.parse(JSON.stringify(x));
const privateScope=body=>({type:'private',actorId:body.actorId,sessionId:body.sessionId});
const identityKey=body=>hash([body.actorId,body.sessionId]);
const sourceTerm=(body,id)=>'body-source:'+hash([body.actorId,body.sessionId,id]);
const eventRow=(body,kind,subject)=>body.memory.db.prepare('SELECT * FROM events WHERE kind=? AND subject=? ORDER BY seq DESC LIMIT 1').get(kind,subject);
const parsed=row=>row?{...row,data:JSON.parse(row.data)}:null;
function assertBody(body){need(body instanceof Body&&!body.writePaused&&body.one('config','body')?.actorId===body.actorId&&body.one('config','body')?.sessionId===body.sessionId,'ACTUAL_BODY_IDENTITY_REQUIRED');}
function sourcePlan(body,row){
 const s=row.data;need(['initial','completed','wake'].includes(s.kind),'UNSUPPORTED_BODY_SOURCE_REQUIRES_REVIEW');
 if(s.kind==='completed')need(body.one('processed',s.ticketId)?.sourceId===row.subject&&s.provenance?.sessionId===body.sessionId&&hash(JSON.parse(s.raw))===hash(s.choice),'ACCEPTED_BODY_SOURCE_REQUIRED');
 if(s.kind==='initial')need(typeof s.text==='string'&&body.one('ready',row.subject),'INITIAL_SOURCE_NOT_READY');
 if(s.kind==='wake')need(body.one('source',s.sleepSource)?.choice?.action==='sleep'&&body.one('ready',row.subject),'WAKE_SOURCE_NOT_BOUND');
 const text=JSON.stringify(s),paragraphId=sourceTerm(body,row.subject),revision=hash(s),documentId='body-private-source:'+identityKey(body)+':'+row.subject,documentKey=hash([documentId,revision]);
 const provenance={sourceKind:'body-private-source',actorId:body.actorId,sessionId:body.sessionId,sourceId:row.subject,sourceEventId:row.id,sourceEventSeq:row.seq,originalParagraphId:paragraphId};
 const origin={documentKey,documentId,revision,source:'body-event:'+row.id,ordinal:0,start:0,end:text.length,digest:hash(text),provenance};
 return{paragraphId,lookupTerm:paragraphId,records:[{kind:'paragraph',subject:paragraphId,id:'paragraph:'+paragraphId,data:{text,chain:null,predecessor:null}},{kind:'paragraph-origin',subject:paragraphId,id:'origin:'+paragraphId,data:origin},{kind:'document',subject:documentKey,id:'document:'+documentKey,data:{documentKey,documentId,revision,source:origin.source,digest:origin.digest,provenance,paragraphCount:1,paragraphIds:[paragraphId]}}]};
}
export function syncBodyPrivateMemory({body,privateMemory,budgetRows=64}){
 assertBody(body);need(privateMemory instanceof ParagraphMemory&&equal(privateMemory.one('recall-store-scope','scope')?.data,privateScope(body)),'ACTUAL_PRIVATE_IMPORT_SCOPE_REQUIRED');
 need(Number.isSafeInteger(budgetRows)&&budgetRows>0,'IMPORT_WORK_BUDGET_REQUIRED');
 const subject=identityKey(body),prior=privateMemory.one('body-private-import',subject)?.data??{version:VERSION,actorId:body.actorId,sessionId:body.sessionId,boundary:0,importedCount:0,chain:'0'.repeat(64)};
 need(prior.version===VERSION&&prior.actorId===body.actorId&&prior.sessionId===body.sessionId&&Number.isSafeInteger(prior.boundary)&&prior.boundary>=0&&Number.isSafeInteger(prior.importedCount)&&prior.importedCount>=0&&/^[0-9a-f]{64}$/.test(prior.chain),'PRIVATE_IMPORT_IDENTITY_CHANGED');
 const head=body.memory.db.prepare('SELECT COALESCE(MAX(seq),0) AS n FROM events').get().n;
 need(prior.boundary<=head,'BODY_IMPORT_SOURCE_SHORTENED');
 const rows=body.memory.db.prepare("SELECT * FROM events WHERE seq>? AND seq<=? AND kind IN ('body-source','paragraph') ORDER BY seq LIMIT ?").all(prior.boundary,head,budgetRows+1);
 const page=rows.slice(0,budgetRows);let chain=prior.chain;
 // Import exactly one event transaction at a time. Deterministic IDs make a
 // crash before the page checkpoint retry-safe; no original data is removed.
 for(const raw of page){
  const row=parsed(raw),source=row.kind==='paragraph'?parsed(eventRow(body,'body-source',row.subject.slice('thought:'.length))):null;
  const plan=row.kind==='body-source'?sourcePlan(body,row):planPrivateParagraph({actorId:body.actorId,sessionId:body.sessionId,paragraph:row,completedSource:source});
  const paragraphId=plan.paragraphId,term=plan.lookupTerm??'body-memory',receipt={version:VERSION,actorId:body.actorId,sessionId:body.sessionId,eventId:row.id,eventSeq:row.seq,eventDigest:hash(row),contentDigest:hash(row.data),kind:row.kind,subject:row.subject,paragraphId,lookupTerm:term};
  const description={description:row.kind==='body-source'?'Exact private Body source. Read the original before choosing.':'Exact private thought from an accepted Body source.',terms:[...new Set(['body-memory',term])],source:'host-mechanical-index-not-authored-opinion'};
  privateMemory.db.exec('BEGIN IMMEDIATE');try{
   for(const r of plan.records)privateMemory.append(r.kind,r.subject,r.data,r.id);
   privateMemory.append('description',paragraphId,description,'body-import-description:'+row.id);
   privateMemory.append('body-private-event',row.id,receipt,'body-private-event:'+row.id);
   if(row.kind==='body-source')privateMemory.append('body-private-source',row.subject,receipt,'body-private-source:'+row.id);
   privateMemory.db.exec('COMMIT');
  }catch(e){privateMemory.db.exec('ROLLBACK');throw e;}
  chain=hash([chain,row.seq,hash(row)]);
 }
 const complete=rows.length<=budgetRows,boundary=complete?head:page.at(-1).seq;
 const next={version:VERSION,actorId:body.actorId,sessionId:body.sessionId,boundary,importedCount:prior.importedCount+page.length,chain};
 if(!equal(next,prior))privateMemory.append('body-private-import',subject,next,'body-private-import:'+subject+':'+boundary);
 return{...next,processed:page.length,complete,privateSeq:privateMemory.db.prepare('SELECT MAX(seq) AS n FROM events').get().n};
}
function brokerState(body,broker){
 assertBody(body);need(broker instanceof RoundRecallBroker&&broker.identity.actorId===body.actorId&&broker.identity.sessionId===body.sessionId,'ACTUAL_SAME_IDENTITY_RECALL_REQUIRED');
 const store=broker.adapter.store('private');need(equal(store.scope,privateScope(body))&&store.snapshotSeq===broker.memorySnapshot.privateSeq,'PRIVATE_PIN_CHANGED');
 const tail=store.db.prepare('SELECT * FROM events WHERE seq=?').get(store.snapshotSeq);
 need(tail&&hash(tail)===broker.memorySnapshot.privateTailDigest,'PRIVATE_TAIL_CHANGED');
 const coverage=store.at('body-private-import',identityKey(body),store.snapshotSeq)?.data;
 need(coverage?.version===VERSION&&coverage.actorId===body.actorId&&coverage.sessionId===body.sessionId,'PERSISTED_PRIVATE_IMPORT_REQUIRED');
 return{store,coverage};
}
function refFor(body,store,id){
 const original=parsed(eventRow(body,'body-source',id)),receipt=store.at('body-private-source',id,store.snapshotSeq)?.data;
 need(original&&receipt&&receipt.eventId===original.id&&receipt.eventSeq===original.seq&&receipt.eventDigest===hash(original)&&receipt.contentDigest===hash(original.data),'SOURCE_NOT_IN_FROZEN_PRIVATE_INDEX');
 const origin=store.at('paragraph-origin',receipt.paragraphId,store.snapshotSeq)?.data,paragraph=store.at('paragraph',receipt.paragraphId,store.snapshotSeq)?.data;
 need(origin?.revision===receipt.contentDigest&&origin.provenance?.sourceEventId===original.id&&paragraph?.text===JSON.stringify(original.data),'PRIVATE_SOURCE_ORIGINAL_MISMATCH');
 return{sourceId:id,sourceDigest:receipt.contentDigest,paragraphId:receipt.paragraphId,lookup:{scope:'private',term:receipt.lookupTerm}};
}
function memoryRef(broker,coverage){return{version:VERSION,roundId:broker.snapshot.roundId,snapshotDigest:broker.snapshot.snapshotDigest,memorySnapshotDigest:broker.memorySnapshotDigest,privateSeq:broker.memorySnapshot.privateSeq,privateTailDigest:broker.memorySnapshot.privateTailDigest,sharedSeq:broker.memorySnapshot.sharedSeq,sharedTailDigest:broker.memorySnapshot.sharedTailDigest,coverage:{boundary:coverage.boundary,importedCount:coverage.importedCount,chain:coverage.chain},lookup:{scope:'private',term:'body-memory'}};}
export function claimReferenced({body,broker,sharedContext,maxInputBytes=8192}){
 const {store,coverage}=brokerState(body,broker);need(Number.isSafeInteger(maxInputBytes)&&maxInputBytes>0,'INPUT_WORK_BUDGET_REQUIRED');
 const state=body.state();if(state.mode!=='awake')return null;
 need(!body.one('claim',state.source),'EXISTING_CLAIM_REQUIRES_ORIGINAL_PROTOCOL');
 const outstanding=body.memory.db.prepare("SELECT subject FROM events b WHERE b.kind='body-binding' AND NOT EXISTS(SELECT 1 FROM events p WHERE p.kind='body-processed' AND p.subject=b.subject) LIMIT 1").get();need(!outstanding,'UNRESOLVED_BINDING_NO_NEW_CLAIM');
 const relevant=body.memory.db.prepare("SELECT COALESCE(MAX(seq),0) AS n FROM events WHERE kind IN ('body-source','paragraph')").get().n;
 need(coverage.boundary>=relevant,'PRIVATE_INDEX_ADVANCE_REQUIRES_NEW_ROUND');
 const ready=body.memory.db.prepare("SELECT r.subject FROM events r WHERE r.kind='body-ready' AND NOT EXISTS(SELECT 1 FROM events c WHERE c.kind='body-claim' AND c.subject=r.subject) ORDER BY r.seq LIMIT 1").get();need(ready?.subject===state.source,'EXACT_READY_SOURCE_REQUIRED');
 if(sharedContext!==undefined)need(equal(sharedContext,{assemblyRef:{roundId:broker.snapshot.roundId,snapshotDigest:broker.snapshot.snapshotDigest,memorySnapshotDigest:broker.memorySnapshotDigest}}),'EXACT_SHORT_ROUND_CONTEXT_REQUIRED');
 const sourceRef=refFor(body,store,state.source),source=body.one('source',state.source),ticket={inputVersion:VERSION,id:'dispatch:'+state.source,actorId:body.actorId,sessionId:body.sessionId,source:state.source,policy:{epoch:broker.identity.policyEpoch,digest:broker.identity.policyDigest},sourceRef,memoryRef:memoryRef(broker,coverage),...(sharedContext===undefined?{}:{sharedContext:clone(sharedContext)}),...(source.kind==='wake'?{causalParentRef:refFor(body,store,source.sleepSource)}:{})};
 const payload={kind:'hcx-body-input',...ticket};need(Buffer.byteLength(JSON.stringify(payload))<=maxInputBytes,'REFERENCED_INPUT_RESOURCE_HELD');
 const proof={version:VERSION,ticketDigest:hash(ticket),modelPayloadDigest:hash(payload),identity:broker.identity,sourceDigest:sourceRef.sourceDigest,memoryRefDigest:hash(ticket.memoryRef)};
 return body.tx(()=>{
  need(equal(body.state(),state)&&!body.one('claim',state.source),'READY_CHANGED_BEFORE_REFERENCED_CLAIM');
  const config=body.one('config','body'),grants=body.memory.db.prepare("SELECT COALESCE(SUM(json_extract(data,'$.extra')),0) AS n FROM events WHERE kind='body-grant'").get().n,claims=body.memory.db.prepare("SELECT COUNT(*) AS n FROM events WHERE kind='body-claim'").get().n;
  if(claims>=config.allowance+grants){body.stateTo('held:'+state.source,{mode:'resource-held',source:state.source,wakeAt:null});return null;}
  body.put('claim',state.source,ticket);body.put('memory-reference-ticket',ticket.id,proof);return clone(ticket);
 });
}
export function verifyReferencedTicket({body,broker,ticket}){
 const {store,coverage}=brokerState(body,broker),proof=body.one('memory-reference-ticket',ticket?.id);
 need(ticket?.inputVersion===VERSION&&proof?.version===VERSION&&equal(body.one('claim',ticket.source),ticket),'ISSUED_REFERENCED_TICKET_REQUIRED');
 need(proof.ticketDigest===hash(ticket)&&proof.modelPayloadDigest===hash({kind:'hcx-body-input',...ticket})&&equal(proof.identity,broker.identity)&&equal(ticket.policy,{epoch:broker.identity.policyEpoch,digest:broker.identity.policyDigest}),'REFERENCED_TICKET_POLICY_OR_PAYLOAD_CHANGED');
 need(equal(ticket.sourceRef,refFor(body,store,ticket.source))&&equal(ticket.memoryRef,memoryRef(broker,coverage))&&proof.memoryRefDigest===hash(ticket.memoryRef),'REFERENCED_TICKET_SNAPSHOT_CHANGED');
 if(ticket.causalParentRef)need(equal(ticket.causalParentRef,refFor(body,store,body.one('source',ticket.source).sleepSource)),'REFERENCED_PARENT_CHANGED');
 return clone(proof);
}
export function acceptReferencedOpinion({wrapper,body,broker,sourceRef}){
 const claim=body.memory.db.prepare("SELECT data FROM events WHERE kind='body-claim' AND json_extract(data,'$.id')=?").get(sourceRef?.ticketId);
 need(claim,'REFERENCED_OPINION_CLAIM_REQUIRED');verifyReferencedTicket({body,broker,ticket:JSON.parse(claim.data)});
 // The reviewed wrapper verifies the same actual source, offer and exact
 // serialization of this NEW versioned ticket. No legacy payload is forged.
 return wrapper.accept(sourceRef);
}
