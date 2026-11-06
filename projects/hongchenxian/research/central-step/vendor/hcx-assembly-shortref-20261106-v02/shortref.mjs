import {RoundRecallBroker,digest} from '../hcx-round-recall-bridge-20261106-v01/round-recall.mjs';
import {isDeepStrictEqual as equal} from 'node:util';
import {realpathSync,statSync} from 'node:fs';
const need=(v,m)=>{if(!v)throw Error(m);},clone=v=>JSON.parse(JSON.stringify(v));
const exact=(v,keys)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).sort().join(',')===[...keys].sort().join(',');
export const PREPARATION_LOCK=true;
export class AssemblyShortref {
 constructor({router,brokers}){
  need(router&&Array.isArray(brokers)&&brokers.length===10&&brokers.every(b=>b instanceof RoundRecallBroker),'TEN_ACTUAL_RECALL_BROKERS_REQUIRED');
  this.router=router;this.ledger=router.ledger;this.roundId=brokers[0].snapshot.roundId;this.brokers=new Map();
  const snapshot=router.snapshot(this.roundId);need(snapshot.roster.length===10,'TEN_ROSTER_REQUIRED');
  need(new Set(brokers.map(b=>b.identity.actorId)).size===10&&new Set(brokers.map(b=>b.identity.sessionId)).size===10,'UNIQUE_BROKER_IDENTITIES');
  const pins=[];let commonShared=null;
  for(const b of brokers){
   const actorId=b.identity.actorId,sessionId=b.identity.sessionId;
   need(snapshot.roster.some(m=>m.actorId===actorId&&m.sessionId===sessionId)&&equal(b.snapshot,snapshot),'BROKER_ROUND_IDENTITY_MISMATCH');
   const memory=clone(b.memorySnapshot),short={roundId:this.roundId,snapshotDigest:snapshot.snapshotDigest,memorySnapshotDigest:b.memorySnapshotDigest};
   need(b.memorySnapshotDigest===digest({privateSeq:memory.privateSeq,sharedSeq:memory.sharedSeq,snapshotDigest:snapshot.snapshotDigest}),'MEMORY_SNAPSHOT_DIGEST_MISMATCH');
   need(['privateSeq','sharedSeq'].every(k=>Number.isSafeInteger(memory[k])&&memory[k]>=1)&&['privateTailDigest','sharedTailDigest'].every(k=>/^[a-f0-9]{64}$/.test(memory[k])),'MEMORY_SNAPSHOT_PIN_REQUIRED');
   // Re-read the actual admitted fixed shared partition, not a caller's boolean.
   const store=b.adapter.store('shared'),path=realpathSync(store.path),location=realpathSync(store.db.location());
   const stat=statSync(path,{bigint:true});need(stat.isFile()&&path===location,'SHARED_STORE_IDENTITY_REQUIRED');
   need(store.snapshotSeq===memory.sharedSeq&&store.max===memory.sharedSeq&&store.db.prepare('SELECT MAX(seq) AS seq FROM events').get().seq===memory.sharedSeq,'SHARED_VIEW_SEQUENCE_MISMATCH');
   const scope=store.at('recall-store-scope','scope',memory.sharedSeq),publication=store.at('round-publication',String(snapshot.sharedEpoch),memory.sharedSeq);
   need(scope&&equal(scope.data,{type:'shared',poolId:b.identity.poolId})&&equal(store.scope,scope.data),'SHARED_POOL_SCOPE_MISMATCH');
   need(publication?.seq===memory.sharedSeq&&equal(publication.data,{sharedEpoch:snapshot.sharedEpoch,sharedRefsDigest:digest(snapshot.sharedRefs)})&&digest(publication)===memory.sharedTailDigest,'SHARED_PUBLICATION_EVIDENCE_MISMATCH');
   const sharedView={poolId:b.identity.poolId,store:{canonicalPath:path,device:String(stat.dev),inode:String(stat.ino)},scope:clone(scope),sharedSeq:memory.sharedSeq,sharedTailDigest:memory.sharedTailDigest,publication:clone(publication)};
   if(commonShared===null)commonShared=sharedView;else need(equal(commonShared,sharedView),'COMMON_SHARED_VIEW_REQUIRED');
   const pin={actorId,sessionId,snapshot,memorySnapshot:memory,short,policyIdentity:clone(b.identity),sharedViewDigest:digest(sharedView)};
   pins.push({actorId,broker:b,id:digest([this.roundId,actorId]),pin});
  }
  // All ten views and all existing pins are checked BEFORE the first write.
  const sharedId=digest([this.roundId,'common-shared-view']);
  const oldShared=this.ledger.one('assembly-shared-view-pin',sharedId);
  need(!oldShared||equal(oldShared,commonShared),'IMMUTABLE_SHORTREF_CONFLICT');
  for(const p of pins){const old=this.ledger.one('assembly-shortref-pin',p.id);need(!old||equal(old,p.pin),'IMMUTABLE_SHORTREF_CONFLICT');}
  this.ledger.tx(()=>{if(!oldShared)this.ledger.put('assembly-shared-view-pin',sharedId,commonShared);for(const p of pins)if(!this.ledger.one('assembly-shortref-pin',p.id))this.ledger.put('assembly-shortref-pin',p.id,p.pin);});
  for(const p of pins)this.brokers.set(p.actorId,p.broker);
 }
 persist(kind,id,value){const old=this.ledger.one(kind,id);need(!old||equal(old,value),'IMMUTABLE_SHORTREF_CONFLICT');if(!old)this.ledger.tx(()=>this.ledger.put(kind,id,value));return clone(value);}
 pin(actorId,roundId=this.roundId){need(roundId===this.roundId,'WRONG_ROUND');const pin=this.ledger.one('assembly-shortref-pin',digest([roundId,actorId]));need(pin&&this.brokers.has(actorId),'UNKNOWN_PINNED_MEMBER');need(equal(pin.snapshot,this.router.snapshot(roundId)),'HOST_SNAPSHOT_CHANGED');const shared=this.ledger.one('assembly-shared-view-pin',digest([roundId,'common-shared-view']));need(shared&&digest(shared)===pin.sharedViewDigest,'HOST_SHARED_VIEW_CHANGED');return clone(pin);}
 context(actorId,roundId=this.roundId){const pin=this.pin(actorId,roundId);need(equal(this.router.input(actorId,roundId),pin.snapshot),'ROUND_NOT_OPEN');const member=this.router.members.get(actorId);need(member&&member.sessionId===pin.sessionId,'BODY_IDENTITY_CHANGED');const state=member.body.state();need(state.mode==='awake','MEMBER_NOT_AWAKE');need(!member.body.one('claim',state.source),'TICKET_ALREADY_CLAIMED_RECONCILE_REQUIRED');const ticketId='dispatch:'+state.source;
  const offer={actorId,sessionId:pin.sessionId,ticketId,source:state.source,roundId,short:pin.short,pinDigest:digest(pin)};
  this.persist('assembly-shortref-offer',digest([actorId,ticketId]),offer);
  return{assemblyRef:clone(pin.short)};
 }
 accept(sourceRef){
  const own=this.router.own(sourceRef),r=own.record;
  need(exact(r,['kind','roundId','snapshotDigest','memorySnapshotDigest','position','text','reason'])&&r.kind==='position','EXPLICIT_PUBLIC_POSITION_REQUIRED');
  need(['support','oppose','silent','undecided','conditional','decline'].includes(r.position)&&typeof r.text==='string'&&r.text.trim()&&(r.reason===null||typeof r.reason==='string'&&r.reason.trim()),'EXPLICIT_POSITION_FIELDS');
  const pin=this.pin(sourceRef.actorId,r.roundId);const ref={roundId:r.roundId,snapshotDigest:r.snapshotDigest,memorySnapshotDigest:r.memorySnapshotDigest};need(equal(ref,pin.short),'POSITION_SHORTREF_MISMATCH');
  const offer=this.ledger.one('assembly-shortref-offer',digest([sourceRef.actorId,sourceRef.ticketId]));need(offer&&offer.sessionId===sourceRef.sessionId&&offer.roundId===r.roundId&&equal(offer.short,ref)&&offer.pinDigest===digest(pin),'ISSUED_TICKET_OFFER_REQUIRED');
  const body=this.router.members.get(sourceRef.actorId).body;
  const ticket=body.one('claim',offer.source);need(ticket&&ticket.id===sourceRef.ticketId&&ticket.actorId===sourceRef.actorId&&ticket.sessionId===sourceRef.sessionId&&ticket.source===offer.source,'EXACT_TICKET_REQUIRED');
  need(exact(ticket.sharedContext,['assemblyRef'])&&equal(ticket.sharedContext.assemblyRef,ref),'EXACT_SHORTREF_INPUT_REQUIRED');
  const binding=body.binding(sourceRef.ticketId);need(binding?.ticketId===ticket.id&&equal(binding.content,[{type:'text',text:JSON.stringify({kind:'hcx-body-input',...ticket})}]),'EXACT_BOUND_INPUT_REQUIRED');
  const id=digest([r.roundId,sourceRef.actorId,sourceRef.sourceId]);
  const staged={roundId:r.roundId,actorId:sourceRef.actorId,sessionId:sourceRef.sessionId,record:r,source:own.ref,publicText:own.publicText,provenance:own.provenance};
  const receipt={stageId:id,source:own.ref,roundId:r.roundId,short:ref,ticketDigest:digest(ticket),offerDigest:digest(offer),classification:'source-bound-public-opinion-not-retrieval'};
  const old=this.ledger.one('assembly-shortref-accepted',id);
  if(old){need(equal(old,receipt)&&equal(this.ledger.one('assembly-staged',id),staged),'SHORTREF_REPLAY_CONFLICT');return clone(old);}
  need(!this.router.state(r.roundId).terminal,'ROUND_NOT_OPEN');
  const existing=this.ledger.one('assembly-staged',id);need(!existing||equal(existing,staged),'STAGED_SOURCE_CONFLICT');
  this.ledger.tx(()=>{this.ledger.put('assembly-staged',id,staged);this.ledger.put('assembly-shortref-accepted',id,receipt);});return clone(receipt);
 }
 publish(roundId,options){need(roundId===this.roundId,'WRONG_ROUND');return this.router.publish(roundId,options);}
}
