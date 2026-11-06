import {createHash} from 'node:crypto';
import {verifyReferencedTicket} from './memory-reference.mjs';
import {validateCompleted} from './source-completion.mjs';
export const PREPARATION_LOCK=true;
export const VERSION='hcx-native-lifecycle/v2';
export const digest=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
const copy=x=>JSON.parse(JSON.stringify(x));
const need=(ok,code)=>{if(!ok)throw Error(code);};
const scopeKeys=['actorId','sessionId','policyEpoch','policyDigest'];
// Independent protocol, not a relaxation of the sealed single-turn/no-tools gate.
// This class deliberately has no send, pump, tool-execution, resume or timer API.
export class NativeLifecycleAdapter {
 constructor({body,bridge,nativeCore,identity,systemMessages,broker,onFailure=()=>{},onCut=()=>{}}){
  need(Array.isArray(systemMessages)&&systemMessages.every(m=>m.role==='system'&&Array.isArray(m.content)),'EXPLICIT_SYSTEM_POLICY_REQUIRED');
  need(body&&bridge&&nativeCore&&nativeCore.bridge===bridge,'EXACT_NATIVE_BRIDGE_REQUIRED');
  for(const k of scopeKeys)need(typeof identity?.[k]==='string'&&identity[k]&&identity[k]===bridge.identity[k]&&identity[k]===nativeCore.identity[k],'IDENTITY_POLICY_MISMATCH');
  need(body.actorId===identity.actorId&&body.sessionId===identity.sessionId,'BODY_IDENTITY_MISMATCH');
  Object.assign(this,{body,bridge,nativeCore,broker,identity:Object.freeze(copy(identity)),onFailure,onCut});
  this.error=null;this.failureNotificationError=null;this.busy=false;this.tail=Promise.resolve();
  this.config={version:VERSION,identity:copy(identity),config:copy(nativeCore.config),schemas:copy(nativeCore.expectedSchemas),systemMessages:systemMessages.map(m=>({role:m.role,content:copy(m.content)}))};
  body.tx(()=>body.put('native-lifecycle-config','policy',this.config));
 }
 healthy(){
  need(!this.error&&!this.body.rows('native-lifecycle-hold').length,'NATIVE_LIFECYCLE_HELD');
  for(const k of scopeKeys)need(this.identity[k]===this.bridge.identity[k]&&this.identity[k]===this.nativeCore.identity[k],'IDENTITY_POLICY_CHANGED');
  need(this.body.actorId===this.identity.actorId&&this.body.sessionId===this.identity.sessionId,'BODY_IDENTITY_CHANGED');
  need(digest(this.body.one('native-lifecycle-config','policy'))===digest(this.config)&&digest(this.nativeCore.config)===digest(this.config.config)&&digest(this.nativeCore.expectedSchemas)===digest(this.config.schemas),'CONFIG_CHANGED');
  this.nativeCore.healthy();
 }
 guarded(stage,ticketId,fn){
  const operation=this.tail.then(()=>this.runGuarded(stage,ticketId,fn));
  this.tail=operation.catch(()=>{}); // Serialize signals; the caller still receives the original rejection.
  return operation;
 }
 async runGuarded(stage,ticketId,fn){
  this.busy=true;
  try{this.healthy();return await fn();}
  catch(error){
   if(error?.syntheticCrash===true)throw error;
   this.error??=error;
   let failure={version:VERSION,stage,ticketId:typeof ticketId==='string'?ticketId:null,code:'NATIVE_LIFECYCLE_FAILED'};
   // Preserve first cause separately. Notification failure is not silently swallowed.
   try{this.body.tx(()=>{const first=this.body.one('native-lifecycle-hold','first');if(first)failure=first;else this.body.put('native-lifecycle-hold','first',failure);});}
   catch(persistenceError){this.persistenceError=persistenceError;}
   if(!this.notified){this.notified=true;try{await this.onFailure(copy(failure));}catch(notificationError){this.failureNotificationError=notificationError;throw notificationError;}}
   throw this.persistenceError??error;
  }finally{this.busy=false;}
 }
 async bind(ticket,{messageId,sourceExtras={}}={}){
  return this.guarded('BIND',ticket?.id,async()=>{
   verifyReferencedTicket({body:this.body,broker:this.broker,ticket});
   need(ticket?.actorId===this.body.actorId&&ticket?.sessionId===this.body.sessionId,'TICKET_IDENTITY');
   need(typeof messageId==='string'&&messageId,'MESSAGE_ID_REQUIRED');
   need(Object.keys(sourceExtras).every(k=>['roundId','snapshotDigest','memorySnapshotDigest'].includes(k)),'UNSUPPORTED_SOURCE_EXTRAS');
   need(!this.body.binding(ticket.id)&&!this.bridge.one('native-dispatch',ticket.id),'CONSUMED_TICKET_NO_RESEND');
   need(this.body.rows('binding').every(r=>this.body.one('processed',r.subject)),'PENDING_TICKET_HELD');
   const message={id:messageId,role:'user',content:[{type:'text',text:JSON.stringify({kind:'hcx-body-input',...ticket})}],source:{kind:'hcx-index-native-abi',...this.identity,ticketId:ticket.id,...copy(sourceExtras)}};
   const binding={ticketId:ticket.id,actorId:ticket.actorId,sessionId:ticket.sessionId,messageId,content:message.content,source:message.source};
   this.body.bind(ticket,binding);
   this.body.tx(()=>this.body.put('native-lifecycle-binding',ticket.id,{version:VERSION,identity:this.identity,message}));
   this.onCut('after-body-binding');
   await this.nativeCore.reserve(ticket.id,message);this.onCut('after-native-reserve');
   return copy(message);
  });
 }
 async admitStream(options){
  return this.guarded('ADMISSION',null,async()=>{
   const pending=this.body.rows('binding').filter(r=>!this.body.one('processed',r.subject));need(pending.length===1,'ONE_PENDING_TICKET_REQUIRED');
   const ticketId=pending[0].subject;
   need(this.body.one('native-lifecycle-binding',ticketId),'VERSIONED_BINDING_REQUIRED');
   need(this.body.state().mode==='awake','NONAWAKE_STREAM');
   need(options.system===undefined&&Array.isArray(options.messages)&&digest(options.messages.filter(m=>m.role==='system').map(m=>({role:m.role,content:m.content})))===digest(this.config.systemMessages),'SYSTEM_POLICY_MISMATCH');
   await this.nativeCore.beforeRequest(options);
   const step=this.bridge.findEvents({type:'step/start',latest:true}).at(-1);
   const header=this.bridge.findEvents({type:'request/header',latest:true}).at(-1);
   need(step&&header,'SOURCE_STEP_HEADER_REQUIRED');
   const start=this.bridge.findEvents({type:'turn/start',latest:true}).at(-1);
   need(start&&start.data.turn===step.data.turn&&start.seq<step.seq,'ACTIVE_TURN_STEP_REQUIRED');
   need(!this.bridge.findEvents({type:'turn/end',turn:step.data.turn}).length,'TURN_ALREADY_ENDED');
   need(!this.bridge.findEvents({type:'assistant/message',turn:step.data.turn,after:step.seq}).length,'STEP_ALREADY_HAS_RESPONSE');
   // Input may be appended after step/start, but must be in the flushed request prefix.
   const input=this.bridge.findEvents({type:'user/message',latest:true}).at(-1);
   const native=this.bridge.one('native-dispatch',ticketId);
   need(native&&input&&input.seq>start.seq&&digest(input.data)===digest(native.message),'EXACT_DISPATCH_INPUT_REQUIRED');
   const key=ticketId+':'+step.seq;need(!this.body.one('native-step-admission',key),'STEP_ALREADY_ADMITTED_NO_RETRY');
   this.body.tx(()=>{
    this.body.put('native-step-admission',key,{ticketId,stepSeq:step.seq,turn:step.data.turn,step:step.data.step,headerSeq:header.seq,headerDigest:digest(header),requestDigest:digest(options),identity:this.identity});
    if(!this.body.one('stream',ticketId))this.body.put('stream',ticketId,{sessionId:this.body.sessionId,protocol:VERSION});
   });
   this.onCut('after-step-admission');return {ticketId,stepSeq:step.seq};
  });
 }
 async complete({ticketId,endSeq}){
  return this.guarded('COMPLETION',ticketId,async()=>{
   const binding=this.body.binding(ticketId);need(binding&&this.body.one('native-lifecycle-binding',ticketId),'BOUND_NATIVE_TICKET_REQUIRED');
   const proof=await validateCompleted({bridge:this.bridge,nativeCore:this.nativeCore,ticketId,endSeq,identity:this.identity,binding:this.body.one('native-lifecycle-binding',ticketId)});
   need(Array.isArray(proof.stepSeqs)&&proof.stepSeqs.length>0,'STEP_PROVENANCE_REQUIRED');
   for(const seq of proof.stepSeqs){
    const admission=this.body.one('native-step-admission',ticketId+':'+seq),step=this.bridge.event(seq);
    need(admission&&admission.ticketId===ticketId&&admission.stepSeq===seq&&admission.turn===proof.turn&&admission.step===step.data.step&&digest(admission.identity)===digest(this.identity),'UNADMITTED_STEP');
    const observed=proof.stepHeaders?.find(h=>h.stepSeq===seq);
    need(observed&&['stepSeq','turn','step','headerSeq','headerDigest'].every(k=>observed[k]===admission[k]),'ADMISSION_SOURCE_HEADER_MISMATCH');
    need(digest(this.bridge.event(admission.headerSeq))===admission.headerDigest,'ADMITTED_HEADER_CHANGED');
   }
   const admissions=this.body.rows('native-step-admission').filter(r=>r.data.ticketId===ticketId);
   need(admissions.length===proof.stepSeqs.length,'ADMISSION_COVERAGE_MISMATCH');
   const sourceId='completed:'+digest([this.body.sessionId,proof.assistantSeq]);
   const capture={version:VERSION,ticketId,sourceId,identity:this.identity,raw:proof.raw,proof:copy(proof)};
   this.body.tx(()=>this.body.put('native-captured-completion',ticketId,capture));this.onCut('after-capture');
   this.body.acknowledge(ticketId); // Authoritative exact persisted input proves enqueue, not its timing.
   const {raw,stepSeqs,callIds,...provenance}=proof;
   this.body.accept(ticketId,sourceId,raw,{...provenance,sessionId:this.body.sessionId});this.onCut('after-accept');
   const receipt={version:VERSION,sourceId,ticketId,endSeq,rawDigest:digest(raw),proofDigest:digest(proof)};
   this.body.tx(()=>this.body.put('native-lifecycle-receipt',ticketId,receipt));this.onCut('after-receipt');
   return copy(receipt);
  });
 }
}
