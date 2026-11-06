import {recoverCompleted} from './recovery-evidence.mjs';
import {createHash} from 'node:crypto';
// Research-preview composition derived from the sealed local candidate.
// Official loading/deployment is deliberately absent from this distribution.
// No official module imports or network access occur at module load.
export const PREPARATION_LOCK=true;
export const name='hcx-central-step-abi-candidate';
export const inject=['llm','agents','sessions','sessionPersistence','systemPrompt','tools'];
const officialSdks=new WeakSet();
export async function loadOfficialSdk(){throw Error('PREPARATION_LOCKED');}
const need=(v,c)=>{if(!v)throw Error(c);};
export async function runCentralPlugin(ctx,config,sdk,deps){
 const report={schemaVersion:1,status:'error',syntheticOnly:true,officialRuntimeExecuted:officialSdks.has(sdk),handlesClosed:false,streams:0,failureCode:'NONE',phase:config.phase,memberIndex:config.memberIndex,sourceVerified:false,sourceHoldVerified:false,closedAdmissionRejected:false,wire:null,caseId:config.caseId??'roundtrip',sessionId:config.registry.members[config.memberIndex].sessionId,registryHash:createHash('sha256').update(JSON.stringify(config.registry)).digest('hex')};
 let state,binding,wire,handle,providerDisposer,hookDisposer,sectionDisposer,accepting=false,violation=null,cleanupFailed=false;const active=new Set();let previousTarget=null,lastOptions=null;
 const reject=code=>{violation??=code;throw Error(code);};
 const check=()=>{if(!accepting||violation)reject('ADMISSION_CLOSED');};
 try{
  need(sdk&&typeof sdk.DeepSeekAdapter==='function','SDK_ADAPTER_REQUIRED');
  state=await deps.openReferenceState({root:config.root,registry:config.registry,phase:config.phase});
  const member=state.members[config.memberIndex];need(member,'MEMBER_REQUIRED');
  hookDisposer=ctx.on('llm/stream',async function*(options,next){
   check();if(options.sessionId!==member.identity.sessionId)reject('FOREIGN_SESSION');
   if(active.size)reject('CONCURRENT_MEMBER_STREAM');
   let done;const drained=new Promise(r=>{done=r;});active.add(drained);let iterator;
   try{
    if(previousTarget)await wire.waitAndSettleStep(previousTarget);check();
    const permit=await binding.adapter.admitStream(options);check();
    const target={actorId:member.identity.actorId,sessionId:member.identity.sessionId,ticketId:permit.ticketId,stepSeq:permit.stepSeq};
    iterator=wire.scopeIterator({target,options},()=>next())[Symbol.asyncIterator]();
    while(true){check();const item=await iterator.next();check();const health=wire.snapshot();if(health.fatalHeld||health.wireHeld)reject('STREAM_FAILURE');if(item.done)break;yield item.value;}
    previousTarget=target;lastOptions=options;report.streams++;
   }catch{violation??='STREAM_FAILURE';throw Error(violation);}
   finally{try{await iterator?.return?.();}catch{cleanupFailed=true;violation??='CLEANUP_FAILURE';}finally{active.delete(drained);done();}}
  });
  need(ctx.tools.schemas().length===0,'GLOBAL_TOOLS_NOT_EMPTY');
  // Provider deps are fixed offline connection + intercepted fetch, never credentials.
  const provider=new sdk.DeepSeekAdapter(deps.providerOptions(()=>wire));
  providerDisposer=ctx.llm.registerAdapter([config.modelConfig.provider],provider);
  const setup=(agentCtx,agent)=>{
   need(agentCtx===agent.ctx&&agent.id===member.identity.sessionId&&agent.session.id===member.identity.sessionId,'EXACT_SCOPED_AGENT_REQUIRED');
   need(config.systemMessages?.length===1&&config.systemMessages[0].role==='system'&&config.systemMessages[0].content?.length===1&&config.systemMessages[0].content[0].type==='text','EXACT_SYSTEM_REQUIRED');
   sectionDisposer=agentCtx.systemPrompt.section({name:'hcx-central-system',order:0,text:config.systemMessages[0].content[0].text,complete:true,interpolate:false});
   binding=state.bindAgent({agentCtx,agent,persistenceCtx:ctx,memberIndex:config.memberIndex,config:config.modelConfig,systemMessages:config.systemMessages,onCut:deps.onCut});
   wire=deps.createProtectedWire({poolBody:state.poolBody,members:[{body:member.body,bridge:binding.bridge,nativeCore:binding.nativeCore}],protectedHeaders:config.protectedHeaders,forwardOffline:deps.forwardOffline});
   return{commit(){need(!accepting&&!violation,'STARTUP_VIOLATION');}};
  };
  handle=await(config.phase==='first'?ctx.agents.create({sessionId:member.identity.sessionId,agentOptions:config.modelConfig,setup}):ctx.agents.resume({resumeSessionId:member.identity.sessionId,agentOptions:config.modelConfig,setup}));
  need(binding&&wire&&handle.agent===binding.bridge.agent,'PUBLISHED_AGENT_CHANGED');if(violation)throw Error(violation);await binding.bridge.sync();if(violation)throw Error(violation);
  if(config.phase==='reopen'){
   const recovery=await recoverCompleted({body:member.body,bridge:binding.bridge,nativeCore:binding.nativeCore,adapter:binding.adapter,wire,poolBody:state.poolBody,verifyTicket:ticket=>state.verifyTicket(config.memberIndex,ticket)});
   if(recovery.status==='passed'){
    need(recovery.receipt,'RECOVERY_RECEIPT_REQUIRED');state.accept(config.memberIndex,recovery.receipt);report.sourceVerified=true;report.status='passed';
   }else if(recovery.status==='held'){report.status='held';report.failureCode='UNRESOLVED_NO_REPLAY';}
   else throw Error('RECOVERY_EVIDENCE_REJECTED');
  }else{
   const ticket=state.claim(config.memberIndex),message=await binding.adapter.bind(ticket,{messageId:'central-input:'+ticket.id,sourceExtras:ticket.sharedContext.assemblyRef});
   accepting=true;handle.agent.followup(message);await handle.agent.whenIdle();check();
   await binding.nativeCore.reconcile();const end=binding.bridge.findEvents({type:'turn/end',latest:true})[0];need(end?.data.reason?.kind==='completed','COMPLETED_SOURCE_REQUIRED');
   const receipt=await binding.adapter.complete({ticketId:ticket.id,endSeq:end.seq});
   // Prior tool steps settle at the next hook after official native results exist; final after receipt.
   for(const row of member.body.rows('native-step-admission').filter(r=>r.data.ticketId===ticket.id))await wire.waitAndSettleStep({actorId:member.identity.actorId,sessionId:member.identity.sessionId,ticketId:ticket.id,stepSeq:row.data.stepSeq});
   wire.settleTicket({actorId:member.identity.actorId,sessionId:member.identity.sessionId,ticketId:ticket.id});need(receipt,'RECEIPT_REQUIRED');state.accept(config.memberIndex,receipt);report.sourceVerified=true;report.status='passed';
  }
 }catch{
  report.status='error';report.failureCode=violation??'COMPOSITION_OR_SOURCE_FAILURE';
  // Classify only a durable guard plus existing spent evidence, never exception text.
  if(config.caseId==='unknown-forward'&&config.phase==='reopen'&&!violation){
   try{const w=wire.snapshot(),body=state.members[config.memberIndex].body,hold=binding.bridge.one('hold','permanent');
    const admissions=body.rows('native-step-admission'),spent=state.poolBody.rows('step-http-spent');need(admissions.length===1&&spent.length===1,'UNKNOWN_HOLD_EVIDENCE_REQUIRED');
    const admission=admissions[0].data,sourceStep=binding.bridge.event(admission.stepSeq),sourceHeader=binding.bridge.event(admission.headerSeq),target=spent[0].data.target;
    need(target.actorId===body.actorId&&target.sessionId===body.sessionId&&target.ticketId===admission.ticketId&&target.stepSeq===admission.stepSeq&&spent[0].data.requestDigest===admission.requestDigest,'UNKNOWN_HOLD_BINDING_REQUIRED');
    need(sourceStep.type==='step/start'&&sourceStep.data.turn===admission.turn&&sourceStep.data.step===admission.step&&createHash('sha256').update(JSON.stringify(sourceHeader)).digest('hex')===admission.headerDigest,'UNKNOWN_HOLD_SOURCE_REQUIRED');
    need(binding.bridge.findEvents({type:'assistant/message',turn:admission.turn,after:admission.stepSeq}).length===0&&binding.bridge.findEvents({type:'turn/end',turn:admission.turn}).length===0&&body.rows('native-captured-completion').length===0,'UNKNOWN_HOLD_NO_COMPLETION_REQUIRED');
    if(JSON.stringify(hold)===JSON.stringify({code:'ROLLING_INTEGRITY_HOLD'})&&w.globalPrepared===1&&w.globalSpent===1&&w.globalSettled===0&&w.wireBindings===1&&w.fatalHeld===true&&w.currentWorker.forwardInvocations===0&&w.currentWorker.inFlight===0&&w.activeScopes===0&&body.rows('native-lifecycle-receipt').length===0&&body.rows('native-step-admission').length===1){report.status='held';report.failureCode='SOURCE_INTEGRITY_HOLD';report.sourceHoldVerified=true;}
   }catch{}
  }
 }
 finally{
  accepting=false;
  if(config.caseId==='closed-admission'&&config.phase==='first'&&report.status==='passed'){
   try{for await(const ignored of ctx.llm.stream({...lastOptions,signal:new AbortController().signal}))void ignored;}catch{}
   report.closedAdmissionRejected=violation==='ADMISSION_CLOSED';
   if(!report.closedAdmissionRejected)violation??='CLOSED_PROBE_NOT_REJECTED';
  }
  // Keep the hook installed while disposing the official agent and draining callbacks.
  const attempt=async fn=>{try{await fn?.();}catch{cleanupFailed=true;}};
  await attempt(()=>handle?.dispose());await Promise.all([...active]);
  await attempt(hookDisposer);await attempt(sectionDisposer);await attempt(providerDisposer);await attempt(deps.disposeWire);await attempt(()=>binding?.dispose());
  try{report.wire=wire?.snapshot()??null;const w=report.wire;if(report.status==='passed'&&(!w||w.fatalHeld||w.wireHeld||w.activeScopes!==0||w.currentWorker.inFlight!==0||w.awaitingOfficialCompletion!==0))violation??='CLEANUP_WIRE_UNSAFE';}catch{cleanupFailed=true;}
  await attempt(()=>state?.close());
  report.handlesClosed=!cleanupFailed;
  if(violation||cleanupFailed){report.status='error';report.failureCode=violation??'CLEANUP_FAILURE';}
 }
 return report;
}
