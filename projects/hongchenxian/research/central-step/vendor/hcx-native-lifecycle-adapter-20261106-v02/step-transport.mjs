// Local ledger/Response bridge. No fetch capture, endpoint, auth or serializer.
import {createHash} from 'node:crypto';
import {validateCompleted} from './source-completion.mjs';
export const PREPARATION_LOCK=true;
export const VERSION='hcx-step-transport/v2';
export const digest=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
const need=(v,c)=>{if(!v)throw Error(c);};
const clone=x=>JSON.parse(JSON.stringify(x));
const keyOf=t=>digest([t.actorId,t.sessionId,t.ticketId,t.stepSeq]);
const eligible=t=>t&&t.status>=200&&t.status<300&&['eof','consumer-cancel'].includes(t.reason);
export class StepTransport {
 constructor({poolBody,members,forward,maxAttempts=40,maxInflight=3,timeoutMs=30000}){
  need(poolBody.actorId==='pool-controller'&&Array.isArray(members)&&members.length>0&&typeof forward==='function','STEP_DEPENDENCIES_REQUIRED');
  need(Number.isSafeInteger(maxAttempts)&&maxAttempts>0&&maxAttempts<=40&&Number.isSafeInteger(maxInflight)&&maxInflight>0&&maxInflight<=3,'STEP_LIMITS');
  need(Number.isSafeInteger(timeoutMs)&&timeoutMs>0&&timeoutMs<=60000,'STEP_TIMEOUT');
  this.body=poolBody;this.members=new Map();this.forward=forward;this.timeoutMs=timeoutMs;this.active=new Map();this.waiters=new Map();this.fatal=null;this.invocations=0;this.highWater=0;
  for(const m of members){need(m.body&&m.bridge&&m.nativeCore&&m.nativeCore.bridge===m.bridge,'MEMBER_REQUIRED');const id=m.body.actorId;need(!this.members.has(id)&&m.body.sessionId===m.bridge.identity.sessionId&&id===m.bridge.identity.actorId,'MEMBER_IDENTITY');this.members.set(id,m);}
  this.config={version:VERSION,maxAttempts,maxInflight,members:[...this.members].map(([actorId,m])=>({actorId,sessionId:m.body.sessionId,identity:clone(m.bridge.identity)})).sort((a,b)=>a.actorId.localeCompare(b.actorId))};
  poolBody.tx(()=>poolBody.put('step-http-config','policy',this.config));
 }
 member(t){const m=this.members.get(t?.actorId);need(m&&m.body.sessionId===t.sessionId&&typeof t.ticketId==='string'&&Number.isSafeInteger(t.stepSeq)&&t.stepSeq>=0,'UNKNOWN_STEP_IDENTITY');need(digest(m.bridge.identity)===digest(this.config.members.find(x=>x.actorId===t.actorId)?.identity),'MEMBER_POLICY_CHANGED');return m;}
 snapshot(){const spent=this.body.rows('step-http-spent'),unsettled=spent.filter(r=>!this.body.one('step-http-settlement',r.subject));return{globalPrepared:this.body.rows('step-http-prepared').length,globalSpent:spent.length,globalSettled:this.body.rows('step-http-settlement').length,awaitingOfficialCompletion:unsettled.filter(r=>eligible(this.body.one('step-http-terminal',r.subject))).length,fatalHeld:Boolean(this.fatal)||this.body.rows('step-http-fault').length>0||this.body.rows('step-http-prepared').some(r=>!this.body.one('step-http-spent',r.subject))||unsettled.some(r=>{const t=this.body.one('step-http-terminal',r.subject);return t?!eligible(t):!this.active.has(r.subject);}),currentWorker:{forwardInvocations:this.invocations,forwardHighWater:this.highWater,inFlight:this.active.size}};}
 prepare(t,options){
  const m=this.member(t),key=keyOf(t);need(!this.snapshot().fatalHeld,'GLOBAL_STEP_UNCERTAIN_HELD');
  need(!this.body.one('step-http-prepared',key),'CONSUMED_STEP_NO_RETRY');
  need(!this.body.rows('step-http-spent').some(r=>r.data.target.actorId===t.actorId&&!this.body.one('step-http-settlement',r.subject)),'PREVIOUS_STEP_UNSETTLED');
  const admission=m.body.one('native-step-admission',t.ticketId+':'+t.stepSeq),binding=m.body.one('native-lifecycle-binding',t.ticketId);
  need(admission&&binding&&admission.ticketId===t.ticketId&&admission.stepSeq===t.stepSeq&&digest(options)===admission.requestDigest,'EXACT_ADMITTED_REQUEST_REQUIRED');
  need(Buffer.byteLength(JSON.stringify(options))<=32768,'STEP_REQUEST_WORK_LIMIT');
  const record={version:VERSION,target:clone(t),admissionDigest:digest(admission),bindingDigest:digest(binding),requestDigest:digest(options)};
  need(this.body.rows('step-http-spent').length<this.config.maxAttempts,'GLOBAL_HTTP_BUDGET');need(this.active.size<this.config.maxInflight,'GLOBAL_HTTP_INFLIGHT');
  // No await between checks and transaction; controller Body owns the single writer.
  this.body.tx(()=>this.body.put('step-http-prepared',key,record));
  return{key,record};
 }
 async forwardStep(t,options,{signal}={}){
  need(!signal?.aborted,'UPSTREAM_ALREADY_ABORTED');
  const {key,record}=this.prepare(t,options);
  this.body.tx(()=>this.body.put('step-http-spent',key,record));
  let reader,status,timer,closed=false,cancelling=false,abortListener;const controller=new AbortController();
  const finish=reason=>{
   if(closed)return;closed=true;clearTimeout(timer);signal?.removeEventListener('abort',abortListener);
   try{this.body.tx(()=>this.body.put('step-http-terminal',key,{version:VERSION,reason,...status===undefined?{}:{status}}));}
   catch(e){this.fatal='TERMINAL_WRITE_UNKNOWN';throw e;}
   finally{if(!['timeout','upstream-abort'].includes(reason))this.active.delete(key);for(const fn of [...(this.waiters.get(key)??[])])fn();}
  };
  this.active.set(key,{target:clone(t)});this.invocations++;this.highWater=Math.max(this.highWater,this.active.size);
  const abort=reason=>{try{finish(reason);}catch{}controller.abort();if(reader)reader.cancel().catch(()=>{}).finally(()=>{this.active.delete(key);for(const fn of [...(this.waiters.get(key)??[])])fn();});};
  abortListener=()=>abort('upstream-abort');signal?.addEventListener('abort',abortListener,{once:true});
  timer=setTimeout(()=>abort('timeout'),this.timeoutMs);
  try{
   // Spent already durable. Synchronous throw also counts an invocation.
   const response=await this.forward(clone(options),{signal:controller.signal,target:clone(t)});
   need(!closed,'STEP_DEADLINE_EXPIRED');need(response instanceof Response,'RESPONSE_REQUIRED');status=response.status;
   this.body.tx(()=>this.body.put('step-http-response',key,{status}));
   if(status<200||status>=300){await response.body?.cancel();finish('non2xx');throw Error('NON2XX_STEP_HELD');}
   need(response.body,'RESPONSE_BODY_REQUIRED');reader=response.body.getReader();
   const stream=new ReadableStream({
    pull:async out=>{try{const item=await reader.read();if(item.done){if(!cancelling){finish('eof');out.close();}}else out.enqueue(item.value);}catch(e){try{finish('read-error');}finally{out.error(e);}}},
    cancel:async reason=>{cancelling=true;try{await reader.cancel(reason);finish('consumer-cancel');}catch(e){finish('read-error');throw e;}}
   });
   return new Response(stream,{status}); // Never copies or logs auth/response headers.
  }catch(e){if(!closed)finish(controller.signal.aborted?'upstream-abort':'forward-error');else this.active.delete(key);throw e;}
 }
 async *scopeIterator(t,iterator){
  const key=keyOf(t);this.member(t);need(this.body.one('step-http-spent',key),'UNSPENT_SEMANTIC_STREAM');let usageIndex=this.body.rows('step-http-usage').filter(r=>r.data.key===key).length;
  try{for await(const chunk of iterator){
   if(chunk?.type==='usage'){
    const u=chunk.usage;if(!(u&&['inputTokens','outputTokens','totalTokens'].every(k=>Number.isSafeInteger(u[k])&&u[k]>=0)&&u.totalTokens===u.inputTokens+u.outputTokens)){this.fatal='INVALID_STEP_USAGE';this.body.tx(()=>this.body.put('step-http-fault',key,{code:'INVALID_STEP_USAGE'}));throw Error('INVALID_STEP_USAGE');}
    this.body.tx(()=>this.body.put('step-http-usage',key+':'+usageIndex++,{key,usage:{inputTokens:u.inputTokens,outputTokens:u.outputTokens,totalTokens:u.totalTokens},basis:'observed-provider-chunk-not-billing'}));
   }
   yield chunk;
  }}catch(error){this.fatal='SEMANTIC_STREAM_FAILED';if(!this.body.one('step-http-fault',key))this.body.tx(()=>this.body.put('step-http-fault',key,{code:'SEMANTIC_STREAM_FAILED'}));throw error;}
 }
 async settleStep(t){
  const m=this.member(t),key=keyOf(t),spent=this.body.one('step-http-spent',key),terminal=this.body.one('step-http-terminal',key);
  need(!this.fatal&&!this.body.one('step-http-fault',key)&&spent&&!this.active.has(key)&&eligible(terminal),'STEP_TERMINAL_NOT_SETTLEABLE');
  need(digest(spent)===digest(this.body.one('step-http-prepared',key)),'PREPARED_SPENT_CONFLICT');
  const admission=m.body.one('native-step-admission',t.ticketId+':'+t.stepSeq),binding=m.body.one('native-lifecycle-binding',t.ticketId);
  need(digest(admission)===spent.admissionDigest&&digest(binding)===spent.bindingDigest,'STEP_ADMISSION_CHANGED');
  await m.nativeCore.reconcile();
  const step=m.bridge.event(t.stepSeq);need(step.type==='step/start'&&step.data.turn===admission.turn&&step.data.step===admission.step,'STEP_SOURCE_CHANGED');
  const ends=m.bridge.findEvents({type:'step/end',turn:admission.turn,after:step.seq}).filter(e=>e.data.step===admission.step);
  need(ends.length===1,'STEP_END_REQUIRED');const end=ends[0];
  const assistants=m.bridge.findEvents({type:'assistant/message',turn:admission.turn,after:step.seq,before:end.seq});need(assistants.length===1,'STEP_ASSISTANT_REQUIRED');
  const a=assistants[0],header=m.bridge.findEvents({type:'request/header',before:a.seq,latest:true}).at(-1);
  need(a.data.step===admission.step&&a.data.interrupted!==true&&header?.seq===admission.headerSeq&&digest(header)===admission.headerDigest,'STEP_SOURCE_POLICY');
  const message=a.data.message,blocks=message?.content;need(message?.role==='assistant'&&message.source?.kind==='model'&&message.source.provider===m.nativeCore.config.provider&&message.source.model===m.nativeCore.config.model&&blocks?.length===1,'STEP_MODEL_PROVENANCE');
  let evidence;
  if(blocks[0].type==='tool-call'){
   const call=m.nativeCore.evidence(blocks[0].id);m.nativeCore.assertObserved(blocks[0].id);
   need(call.call.dispatchId===t.ticketId&&call.call.assistantSeq===a.seq&&call.call.turn===step.data.turn&&call.call.step===step.data.step&&call.complete,'STEP_NATIVE_RESULT_REQUIRED');
   evidence={kind:'native-tool-step',assistantDigest:digest(a),resultDigest:call.source.eventDigest,callId:blocks[0].id};
  }else{
   need(blocks[0].type==='text','STEP_FINAL_TEXT_REQUIRED');
   const receipt=m.body.one('native-lifecycle-receipt',t.ticketId),capture=m.body.one('native-captured-completion',t.ticketId),processed=m.body.one('processed',t.ticketId);
   need(receipt&&capture&&processed?.sourceId===receipt.sourceId&&capture.proof.assistantSeq===a.seq&&capture.proof.stepSeqs.includes(step.seq),'FINAL_LIFECYCLE_RECEIPT_REQUIRED');
   const proof=await validateCompleted({bridge:m.bridge,nativeCore:m.nativeCore,ticketId:t.ticketId,endSeq:receipt.endSeq,identity:m.bridge.identity,binding});
   const source=m.body.one('source',receipt.sourceId);
   need(source?.kind==='completed'&&source.ticketId===t.ticketId&&source.provenance.assistantSeq===a.seq&&receipt.proofDigest===digest(proof)&&digest(capture.proof)===digest(proof),'FINAL_RECEIPT_SOURCE_PROOF_MISMATCH');
   need(receipt.rawDigest===digest(blocks[0].text)&&capture.raw===blocks[0].text&&digest(source.raw)===receipt.rawDigest,'FINAL_SOURCE_RAW_MISMATCH');
   evidence={kind:'final-decision-step',assistantDigest:digest(a),receiptDigest:digest(receipt),sourceId:receipt.sourceId};
  }
  const settlement={version:VERSION,target:clone(t),spentDigest:digest(spent),terminalDigest:digest(terminal),stepEndDigest:digest(end),evidence};
  this.body.tx(()=>this.body.put('step-http-settlement',key,settlement));return clone(settlement);
 }
 async waitAndSettleStep(t,{timeoutMs=5000}={}){
  need(Number.isSafeInteger(timeoutMs)&&timeoutMs>0&&timeoutMs<=60000,'SETTLEMENT_WAIT_BOUND');const key=keyOf(t);
  if(this.body.one('step-http-terminal',key))return this.settleStep(t);
  await new Promise((resolve,reject)=>{let timer;const done=()=>{if(!this.body.one('step-http-terminal',key)&&this.active.has(key))return;clearTimeout(timer);this.waiters.get(key)?.delete(done);resolve();};if(!this.waiters.has(key))this.waiters.set(key,new Set());this.waiters.get(key).add(done);timer=setTimeout(()=>{this.waiters.get(key)?.delete(done);reject(Error('SETTLEMENT_DEADLINE_HELD'));},timeoutMs);done();});
  return this.settleStep(t);
 }
 settleTicket({actorId,sessionId,ticketId}){
  const m=this.members.get(actorId);need(m&&m.body.sessionId===sessionId,'TICKET_IDENTITY');const receipt=m.body.one('native-lifecycle-receipt',ticketId);need(receipt,'TICKET_RECEIPT_REQUIRED');
  const admissions=m.body.rows('native-step-admission').filter(r=>r.data.ticketId===ticketId);need(admissions.length>0,'TICKET_STEPS_REQUIRED');
  const steps=admissions.map(r=>{const key=keyOf({actorId,sessionId,ticketId,stepSeq:r.data.stepSeq});const settlement=this.body.one('step-http-settlement',key);need(settlement,'UNSETTLED_TICKET_STEP');return{key,digest:digest(settlement)};});
  const result={version:VERSION,actorId,sessionId,ticketId,receiptDigest:digest(receipt),steps};this.body.tx(()=>this.body.put('step-http-ticket-settlement',digest([actorId,sessionId,ticketId]),result));return result;
 }
}
