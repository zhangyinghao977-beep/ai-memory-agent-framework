import { RecallAdapter, digest } from './vendor/recall-adapter.mjs';
import { OPERATION, TOOL_SCHEMAS, validateArguments } from './vendor/legacy-tool-contract.mjs';
import { ARCHIVE_SCHEMAS, RollingHistoryNativeAdapter, installScopedHistoryTools } from './vendor/rolling/native-history.mjs';
export const PREPARATION_LOCK=true;
export const VERSION='hcx-round-recall/v1';
export { digest, installScopedHistoryTools };
const need=(v,m)=>{if(!v)throw Error(m);},copy=v=>JSON.parse(JSON.stringify(v));
const str=v=>typeof v==='string'&&v.length>0,hex=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
function schema(value){const v=copy(value),todo=[v];while(todo.length){const n=todo.pop();if(n.minLength!==undefined){delete n.minLength;n.description='Nonempty string; enforced at execution.';}if(n.minimum!==undefined){const min=n.minimum;delete n.minimum;n.description='Safe integer >= '+min+'; enforced at execution.';}todo.push(...Object.values(n.properties??{}));}return v;}
export const SCHEMAS=Object.freeze([...TOOL_SCHEMAS.map(s=>({...copy(s),parameters:schema(s.parameters)})),...ARCHIVE_SCHEMAS]);
const issuedCores=new WeakMap();
function freeze(value){const stack=[value];while(stack.length){const x=stack.pop();if(x&&typeof x==='object'&&!Object.isFrozen(x)){stack.push(...Object.values(x));Object.freeze(x);}}return value;}
const key=(o,keys)=>o&&typeof o==='object'&&!Array.isArray(o)&&Object.keys(o).sort().join(',')===[...keys].sort().join(',');
export function checkSnapshot(snapshot,identity){
  need(key(snapshot,['roundId','roster','sharedEpoch','sharedRefs','topic','urgent','snapshotDigest']),'ROUND_SNAPSHOT_SHAPE');
  const {snapshotDigest,...value}=snapshot;need(digest(value)===snapshotDigest,'ROUND_SNAPSHOT_DIGEST');
  need(str(value.roundId)&&str(value.topic)&&typeof value.urgent==='boolean'&&Number.isSafeInteger(value.sharedEpoch)&&value.sharedEpoch>=0,'ROUND_SNAPSHOT_FIELDS');
  need(Array.isArray(value.roster)&&value.roster.length===10&&new Set(value.roster.map(m=>m.actorId)).size===10&&new Set(value.roster.map(m=>m.sessionId)).size===10,'TEN_IDENTITIES_REQUIRED');
  need(value.roster.every(m=>key(m,['actorId','sessionId'])&&str(m.actorId)&&str(m.sessionId))&&value.roster.some(m=>m.actorId===identity.actorId&&m.sessionId===identity.sessionId),'SAME_ROSTER_IDENTITY_REQUIRED');
  need(Array.isArray(value.sharedRefs)&&value.sharedRefs.every(r=>key(r,['id','digest'])&&str(r.id)&&hex(r.digest))&&new Set(value.sharedRefs.map(r=>r.id)).size===value.sharedRefs.length,'SHARED_REFERENCE_DIRECTORY');
  return copy(snapshot);
}
// Host-owned immutable round object and isolated admitted store copies only.
// The constructor is not a model API or authentication of the file mount.
export class RoundRecallBroker {
  #pages=new WeakMap(); #closed=false;
  constructor({identity,snapshot,privatePath,sharedPath,privateSeq,sharedSeq,maxResponseBytes=16384}){
    need(['actorId','sessionId','poolId','policyEpoch','policyDigest'].every(k=>str(identity?.[k])),'HOST_POLICY_IDENTITY_REQUIRED');this.maxResponseBytes=maxResponseBytes;
    this.identity=Object.freeze(copy(identity));this.snapshot=freeze(checkSnapshot(snapshot,identity));this.refs=new Map(snapshot.sharedRefs.map(r=>[r.id,r.digest]));
    this.memorySnapshot={privateSeq,sharedSeq,snapshotDigest:snapshot.snapshotDigest};
    this.memorySnapshotDigest=digest(this.memorySnapshot);
    this.prefix=VERSION+':'+digest([identity.actorId,identity.sessionId,this.memorySnapshotDigest])+':';
    this.adapter=new RecallAdapter({...identity,privatePath,sharedPath,maxResponseBytes,snapshots:{private:privateSeq,shared:sharedSeq}});
    try{
      const publicationRow=this.adapter.store('shared').at('round-publication',String(snapshot.sharedEpoch),sharedSeq);
      const publication=publicationRow?.data;
      need(publicationRow?.seq===sharedSeq&&publication&&key(publication,['sharedEpoch','sharedRefsDigest'])&&publication.sharedEpoch===snapshot.sharedEpoch&&publication.sharedRefsDigest===digest(snapshot.sharedRefs),'PUBLISHED_SHARED_SNAPSHOT_REQUIRED');
      this.memorySnapshot={...this.memorySnapshot,privateTailDigest:digest(this.adapter.store('private').db.prepare('SELECT * FROM events WHERE seq=?').get(privateSeq)),sharedTailDigest:digest(publicationRow)};
      need(this.adapter.store('private').db.prepare('SELECT 1 FROM events WHERE seq=?').get(privateSeq),'PRIVATE_SNAPSHOT_EVENT_REQUIRED');
      this.memorySnapshot=freeze(this.memorySnapshot);
    }catch(e){this.adapter.close();throw e;}
  }
  close(){if(!this.#closed){this.adapter.close();this.#closed=true;}}
  assertDispatch(dispatchId,message){need(!this.#closed,'ROUND_RECALL_CLOSED');need(message.source.ticketId===dispatchId&&message.source.roundId===this.snapshot.roundId&&message.source.snapshotDigest===this.snapshot.snapshotDigest&&message.source.memorySnapshotDigest===this.memorySnapshotDigest&&message.source.actorId===this.identity.actorId&&message.source.sessionId===this.identity.sessionId,'ROUND_DISPATCH_BINDING');}
  wrap(v){return v?this.prefix+v:v;}
  unwrap(v){if(v===undefined)return v;need(typeof v==='string'&&v.startsWith(this.prefix),'CROSS_ROUND_OR_IDENTITY_HANDLE');return v.slice(this.prefix.length);}
  sharedOrigin(id,origin){need(this.refs.has(id)&&origin?.revision===this.refs.get(id)&&origin.provenance?.sourceKind==='explicit-shared-text'&&origin.provenance.originalParagraphId===id,'UNPUBLISHED_SHARED_ORIGIN');}
  dispatch({tool,input}){
    need(!this.#closed,'ROUND_RECALL_CLOSED');const args=copy(input);
    for(const k of ['hitHandle','indexHandle','readHandle','cursor'])if(args[k]!==undefined&&args[k]!==null)args[k]=this.unwrap(args[k]);
    const result=this.adapter.dispatch({tool,input:args});
    if(result.scope==='shared'){
      for(const hit of result.hits??[])this.sharedOrigin(hit.paragraphId,hit.provenance);
      for(const ref of result.refs??[])if(ref.kind==='paragraph'&&ref.status==='available')this.sharedOrigin(ref.id,this.adapter.store('shared').at('paragraph-origin',ref.id,result.snapshotSeq)?.data);
      for(const f of result.fragments??[])this.sharedOrigin(f.paragraphId,f.provenance);
      if(result.paragraphId)need(this.refs.has(result.paragraphId),'UNPUBLISHED_SHARED_PREVIEW');
    }
    const page=copy(result);for(const h of page.hits??[])if(h.hitHandle)h.hitHandle=this.wrap(h.hitHandle);
    for(const r of page.refs??[])if(r.handle)r.handle=this.wrap(r.handle);
    for(const k of ['previewHandle','readHandle','nextCursor'])if(page[k])page[k]=this.wrap(page[k]);
    page.roundBinding={version:VERSION,actorId:this.identity.actorId,sessionId:this.identity.sessionId,roundId:this.snapshot.roundId,snapshotDigest:this.snapshot.snapshotDigest,sharedEpoch:this.snapshot.sharedEpoch,memorySnapshotDigest:this.memorySnapshotDigest,autonomousRecord:false};
    need(Buffer.byteLength(JSON.stringify(page))<=this.maxResponseBytes,'ROUND_RECALL_RESPONSE_RESOURCE_HELD');
    this.#pages.set(page,digest(page));return page;
  }
  isIssued(page){return this.#pages.get(page)===digest(page);}
  extension(){return{owns:name=>Object.hasOwn(OPERATION,name),validate:validateArguments,read:(name,input)=>this.dispatch({tool:OPERATION[name],input}),assertDispatch:(id,m)=>this.assertDispatch(id,m)};}
}
export function bindRoundNative({bridge,broker,config,onCut,maxResultBytes=32768}){
  need(['actorId','sessionId','policyEpoch','policyDigest'].every(k=>bridge.identity[k]===broker.identity[k]),'SAME_NATIVE_RECALL_IDENTITY');
  bridge.healthy();
  const key=digest([broker.identity.actorId,broker.identity.sessionId,broker.snapshot.roundId,broker.snapshot.snapshotDigest]);
  const binding={...broker.memorySnapshot,actorId:broker.identity.actorId,sessionId:broker.identity.sessionId,memorySnapshotDigest:broker.memorySnapshotDigest};
  need(!bridge.one('round-memory-pin',key)||digest(bridge.one('round-memory-pin',key))===digest(binding),'ROUND_MEMORY_PIN_CHANGED');
  const core=new RollingHistoryNativeAdapter({bridge,expectedSchemas:SCHEMAS,config,onCut,maxResultBytes,extension:broker.extension()});
  bridge.put('round-memory-pin',key,binding);issuedCores.set(core,broker);return core;
}
// This reads the actual candidate binding's retained result lineage. It is not
// a standalone model-submitted receipt, a meeting contribution or an intent.
export function retrievalEvidence({core,broker,callId}){
  need(issuedCores.get(core)===broker,'ISSUED_NATIVE_BINDING_REQUIRED');
  core.assertObserved(callId);const e=core.evidence(callId),page=core.resultFor(callId);
  need(e.call.name==='hcx_memory_read_original'&&page.scope==='shared'&&page.stage==='original'&&page.nextCursor===null,'COMPLETE_SHARED_ORIGINAL_REQUIRED');
  need(page.roundBinding?.snapshotDigest===broker.snapshot.snapshotDigest&&page.roundBinding.actorId===core.identity.actorId,'EVIDENCE_ROUND_MISMATCH');
  const fragments=page.fragments.filter(f=>f.matched);need(fragments.length===1&&fragments[0].paragraphComplete,'SINGLE_COMPLETE_ORIGINAL_PAGE_REQUIRED');
  const f=fragments[0];broker.sharedOrigin(f.paragraphId,f.provenance);
  return {kind:'retrieval-delivery',actorId:core.identity.actorId,sessionId:core.identity.sessionId,roundId:broker.snapshot.roundId,snapshotDigest:broker.snapshot.snapshotDigest,sharedId:f.paragraphId,sharedRecordDigest:broker.refs.get(f.paragraphId),paragraphId:f.paragraphId,originalTextDigest:digest(f.text),sourceToolResult:{callId,eventSeq:e.source.eventSeq,eventDigest:e.source.eventDigest},autonomousRecord:false,sourceApiLineageChecked:true,cryptographicAuthentication:false};
}
