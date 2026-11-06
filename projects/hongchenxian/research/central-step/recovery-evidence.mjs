// Recovery of one already-consumed local candidate ticket. No send, claim,
// model, tool body execution, registry migration or terminal rewriting exists.
import {createHash} from 'node:crypto';
import {isDeepStrictEqual as equal} from 'node:util';
import {validateCompleted} from './vendor/hcx-native-lifecycle-adapter-20261106-v02/source-completion.mjs';
import {VERSION as ADAPTER_VERSION} from './vendor/hcx-native-lifecycle-adapter-20261106-v02/native-lifecycle.mjs';
import {parsePoolChoice} from './vendor/hcx-fish-pool-20261106-v01/pool-choice.mjs';
import {ENDPOINT} from './protected-wire.mjs';
const hash=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
const need=x=>{if(!x)throw Error('RECOVERY_EVIDENCE_REJECTED');};
const copy=x=>JSON.parse(JSON.stringify(x));
const keyOf=t=>hash([t.actorId,t.sessionId,t.ticketId,t.stepSeq]);
const hex=x=>typeof x==='string'&&/^[0-9a-f]{64}$/.test(x);
const existing=(body,kind,id,expected)=>{const value=body.one(kind,id);if(value)need(equal(value,expected));return value;};
const held=()=>({status:'held',code:'RECOVERY_HELD'});
export async function recoverCompleted({body,bridge,nativeCore,adapter,wire,poolBody,verifyTicket}){
 let plan,receipt,targets;
 try{
  need(body&&poolBody&&bridge&&nativeCore&&adapter&&wire&&typeof verifyTicket==='function');
  need(adapter.body===body&&adapter.bridge===bridge&&adapter.nativeCore===nativeCore&&nativeCore.bridge===bridge);
  const identity=adapter.identity;need(identity.actorId===body.actorId&&identity.sessionId===body.sessionId&&equal(identity,bridge.identity));
  const health=wire.snapshot();
  // Existing uncertainty is not upgraded by the presence of a plausible final.
  if(health.fatalHeld||health.wireHeld||health.activeScopes||health.currentWorker.inFlight||body.rows('native-lifecycle-hold').length||body.writePaused||poolBody.writePaused)return held();
  const bindings=body.rows('native-lifecycle-binding');if(bindings.length===0)return held();need(bindings.length===1&&body.rows('binding').length===1&&body.rows('claim').length===1);
  const row=bindings[0],ticketId=row.subject,versioned=row.data,binding=body.binding(ticketId),ticket=body.rows('claim')[0].data;
  need(ticket.id===ticketId&&ticket.actorId===body.actorId&&ticket.sessionId===body.sessionId&&equal(versioned.identity,identity)&&versioned.version===ADAPTER_VERSION);
  await verifyTicket(copy(ticket));
  need(equal(binding,{ticketId,actorId:body.actorId,sessionId:body.sessionId,messageId:versioned.message.id,content:versioned.message.content,source:versioned.message.source}));
  need(equal(versioned.message.content,[{type:'text',text:JSON.stringify({kind:'hcx-body-input',...ticket})}]));
  need(equal(body.one('stream',ticketId),{sessionId:body.sessionId,protocol:ADAPTER_VERSION}));
  const ack=body.one('ack',ticketId);need((!ack||equal(ack,{queued:true}))&&body.rows('ack').length===(ack?1:0));
  const policy=body.one('native-lifecycle-config','policy');need(policy?.version===ADAPTER_VERSION&&equal(policy.identity,identity)&&equal(policy,adapter.config));
  await bridge.sync();
  const inputs=bridge.findEvents({type:'user/message'}).filter(e=>e.data.id===versioned.message.id);need(inputs.length===1&&equal(inputs[0].data,versioned.message));
  const starts=bridge.findEvents({type:'turn/start',before:inputs[0].seq});need(starts.length>0);const start=starts.at(-1);
  const ends=bridge.findEvents({type:'turn/end',turn:start.data.turn});if(ends.length===0)return held();need(ends.length===1);if(ends[0].data.reason?.kind!=='completed')return held();
  const proof=await validateCompleted({bridge,nativeCore,ticketId,endSeq:ends[0].seq,identity,binding:versioned});
  const sourceId='completed:'+hash([body.sessionId,proof.assistantSeq]);
  const capture={version:ADAPTER_VERSION,ticketId,sourceId,identity,raw:proof.raw,proof};
  receipt={version:ADAPTER_VERSION,sourceId,ticketId,endSeq:proof.endSeq,rawDigest:hash(proof.raw),proofDigest:hash(proof)};
  const captureExists=existing(body,'native-captured-completion',ticketId,capture);
  const receiptExists=existing(body,'native-lifecycle-receipt',ticketId,receipt);
  need(body.rows('native-captured-completion').length===(captureExists?1:0)&&body.rows('native-lifecycle-receipt').length===(receiptExists?1:0));
  const {raw,stepSeqs,callIds,...provenance}=proof,choice=parsePoolChoice(raw);
  const expectedSource={kind:'completed',ticketId,raw,choice,provenance:{...provenance,sessionId:body.sessionId}};
  const source=existing(body,'source',sourceId,expectedSource),processed=body.one('processed',ticketId);
  const paragraph=body.memory.one('paragraph','thought:'+sourceId);
  const completed=body.rows('source').filter(r=>r.data.kind==='completed');need(completed.length===(source?1:0)&&body.rows('processed').length===(source?1:0));
  if(source){
   need(captureExists&&equal(processed,{sourceId})&&paragraph?.kind==='paragraph'&&paragraph.subject==='thought:'+sourceId&&paragraph.id==='paragraph:thought:'+sourceId&&equal(paragraph.data,{text:choice.thought,chain:null,predecessor:null})&&body.one('ack',ticketId)?.queued===true);
   need(equal(body.state(),{mode:choice.action==='continue'?'awake':choice.action==='sleep'?'sleeping':'stopped',source:sourceId,wakeAt:choice.wake_at}));
  }else{need(!processed&&!paragraph&&!receiptExists);need(body.state().mode==='awake'&&body.state().source===ticket.source);}
  const admissions=body.rows('native-step-admission');need(admissions.length===proof.stepSeqs.length);
  targets=[];const stepEvidence=[];
  for(const seq of proof.stepSeqs){
   const admission=body.one('native-step-admission',ticketId+':'+seq),header=proof.stepHeaders.find(h=>h.stepSeq===seq);
   need(admission&&header&&admission.ticketId===ticketId&&equal(admission.identity,identity)&&['stepSeq','turn','step','headerSeq','headerDigest'].every(k=>admission[k]===header[k])&&hex(admission.requestDigest));
   const target={actorId:body.actorId,sessionId:body.sessionId,ticketId,stepSeq:seq},key=keyOf(target);
   const spent=poolBody.one('step-http-spent',key),prepared=poolBody.one('step-http-prepared',key),terminal=poolBody.one('step-http-terminal',key),response=poolBody.one('step-http-response',key),wireBinding=poolBody.one('protected-step-wire',key);
   need(equal(prepared,spent)&&spent?.version==='hcx-step-transport/v2'&&equal(spent.target,target)&&spent.admissionDigest===hash(admission)&&spent.bindingDigest===hash(versioned)&&spent.requestDigest===admission.requestDigest);
   need(terminal?.version==='hcx-step-transport/v2'&&['eof','consumer-cancel'].includes(terminal.reason)&&Number.isInteger(terminal.status)&&terminal.status>=200&&terminal.status<300&&equal(response,{status:terminal.status}));
   need(wireBinding?.version==='hcx-protected-step-wire/v1'&&equal(wireBinding.target,target)&&wireBinding.optionsDigest===admission.requestDigest&&hex(wireBinding.wireDigest)&&Number.isSafeInteger(wireBinding.wireBytes)&&wireBinding.wireBytes>0&&wireBinding.wireBytes<=32768&&wireBinding.endpoint===ENDPOINT&&wireBinding.method==='POST');
   need(!poolBody.one('step-http-fault',key)&&!poolBody.one('protected-wire-hold',key));
   const step=bridge.event(seq),stepEnds=bridge.findEvents({type:'step/end',turn:proof.turn,after:seq}).filter(e=>e.data.step===step.data.step);need(stepEnds.length===1);const end=stepEnds[0];
   const assistants=bridge.findEvents({type:'assistant/message',turn:proof.turn,after:seq,before:end.seq});need(assistants.length===1);const assistant=assistants[0],block=assistant.data.message.content[0];
   let evidence;
   if(block.type==='tool-call'){nativeCore.assertObserved(block.id);const observed=nativeCore.evidence(block.id);need(observed.call.dispatchId===ticketId&&observed.call.assistantSeq===assistant.seq);evidence={kind:'native-tool-step',assistantDigest:hash(assistant),resultDigest:observed.source.eventDigest,callId:block.id};}
   else{need(assistant.seq===proof.assistantSeq);evidence={kind:'final-decision-step',assistantDigest:hash(assistant),receiptDigest:hash(receipt),sourceId};}
   const settlement={version:'hcx-step-transport/v2',target,spentDigest:hash(spent),terminalDigest:hash(terminal),stepEndDigest:hash(end),evidence};
   const stepExists=existing(poolBody,'step-http-settlement',key,settlement);
   const wireSettlement={bindingDigest:hash(wireBinding),stepSettlementDigest:hash(settlement)};
   const wireExists=existing(poolBody,'protected-wire-settlement',key,wireSettlement);need(!wireExists||stepExists);if(block.type!=='tool-call'&&stepExists)need(receiptExists);
   targets.push(target);stepEvidence.push({key,spentDigest:hash(spent),wireDigest:hash(wireBinding),settlementDigest:hash(settlement),wireSettlementDigest:hash(wireSettlement)});
  }
  // This finite recovery entry is deliberately one ticket / one configured member.
  for(const kind of ['step-http-prepared','step-http-spent','step-http-response','step-http-terminal','protected-step-wire'])need(poolBody.rows(kind).length===targets.length);
  const knownKeys=new Set(stepEvidence.map(e=>e.key));for(const kind of ['step-http-settlement','protected-wire-settlement'])need(poolBody.rows(kind).every(r=>knownKeys.has(r.subject)));
  const expectedTicketSettlement={version:'hcx-step-transport/v2',actorId:body.actorId,sessionId:body.sessionId,ticketId,receiptDigest:hash(receipt),steps:admissions.map(r=>{const key=keyOf({actorId:body.actorId,sessionId:body.sessionId,ticketId,stepSeq:r.data.stepSeq});return{key,digest:stepEvidence.find(e=>e.key===key).settlementDigest};})};
  const ticketKey=hash([body.actorId,body.sessionId,ticketId]);const ticketExists=existing(poolBody,'step-http-ticket-settlement',ticketKey,expectedTicketSettlement);if(ticketExists)need(receiptExists&&targets.every(t=>poolBody.one('protected-wire-settlement',keyOf(t))));
  plan={version:'hcx-completed-recovery/v1',actorId:body.actorId,sessionId:body.sessionId,ticketId,sourceId,proofDigest:hash(proof),captureDigest:hash(capture),receiptDigest:hash(receipt),sourceDigest:hash(expectedSource),steps:stepEvidence,ticketSettlementDigest:hash(expectedTicketSettlement)};
  const intentExists=existing(body,'native-recovery-intent',ticketId,plan);need(body.rows('native-recovery-intent').length===(intentExists?1:0));
  need(poolBody.rows('step-http-ticket-settlement').length===(ticketExists?1:0));
  const commit={version:plan.version,intentDigest:hash(plan),receiptDigest:hash(receipt),ticketSettlementDigest:plan.ticketSettlementDigest};
  const committed=existing(body,'native-recovery-commit',ticketId,commit);need(body.rows('native-recovery-commit').length===(committed?1:0));if(committed)need(ticketExists&&receiptExists&&intentExists);
 }catch{throw Error('RECOVERY_EVIDENCE_REJECTED');}
 try{
  body.tx(()=>body.put('native-recovery-intent',plan.ticketId,plan));
  const result=await adapter.complete({ticketId:plan.ticketId,endSeq:receipt.endSeq});need(equal(result,receipt));
  for(const target of targets)await wire.waitAndSettleStep(target);
  const settled=wire.settleTicket({actorId:body.actorId,sessionId:body.sessionId,ticketId:plan.ticketId});need(hash(settled)===plan.ticketSettlementDigest);
  body.tx(()=>body.put('native-recovery-commit',plan.ticketId,{version:plan.version,intentDigest:hash(plan),receiptDigest:hash(receipt),ticketSettlementDigest:plan.ticketSettlementDigest}));
  return{status:'passed',code:'RECOVERY_VERIFIED',receipt:copy(receipt)};
 }catch{throw Error('RECOVERY_COMMIT_INDETERMINATE');}
}
