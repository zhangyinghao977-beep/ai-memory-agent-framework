// Read-only completion verifier over the actual candidate source/native ledger.
// It never executes tools, sends messages, invents source proofs or replays work.
import {isDeepStrictEqual as equal} from 'node:util';
import {RollingHistoryBridge,hash} from '../hcx-round-recall-bridge-20261106-v01/vendor/rolling/rolling-bridge.mjs';
import {RollingHistoryNativeAdapter,schemaDigest} from '../hcx-round-recall-bridge-20261106-v01/vendor/rolling/native-history.mjs';
const need=(ok,code)=>{if(!ok)throw Error(code);};
const scope=['actorId','sessionId','policyEpoch','policyDigest'];
const sourceOf=e=>e.data?.message?.source;
export async function validateCompleted({bridge,nativeCore,ticketId,endSeq,identity,binding}){
 need(bridge instanceof RollingHistoryBridge&&nativeCore instanceof RollingHistoryNativeAdapter&&nativeCore.bridge===bridge,'ACTUAL_SOURCE_NATIVE_BRIDGE_REQUIRED');
 for(const key of scope)need(identity?.[key]===bridge.identity[key]&&identity[key]===nativeCore.identity[key]&&binding?.identity?.[key]===identity[key],'COMPLETION_IDENTITY_POLICY_MISMATCH');
 need(typeof ticketId==='string'&&ticketId&&Number.isSafeInteger(endSeq)&&endSeq>=0,'COMPLETION_TARGET_REQUIRED');
 bridge.assertOwner(nativeCore.agent);await nativeCore.reconcile();bridge.healthy();
 const checkpoint=bridge.checkpoint();need(endSeq<checkpoint.boundary,'COMPLETION_SOURCE_BOUNDARY');
 const ending=bridge.event(endSeq);need(ending.type==='turn/end'&&ending.data.reason?.kind==='completed','COMPLETED_TURN_END_REQUIRED');
 const turn=ending.data.turn,starts=bridge.findEvents({type:'turn/start',turn,before:endSeq});
 need(starts.length===1&&bridge.findEvents({type:'turn/end',turn}).length===1,'EXACT_COMPLETED_TURN_REQUIRED');
 const start=starts[0];need(endSeq-start.seq+1<=bridge.workEvents,'COMPLETION_TURN_WORK_BUDGET_HOLD');
 const native=bridge.one('native-dispatch',ticketId),message=binding?.message;
 need(native&&equal(native.message,message)&&native.dispatchId===ticketId,'COMPLETION_NATIVE_DISPATCH_MISMATCH');
 for(const key of scope)need(native[key]===identity[key]&&message?.source?.[key]===identity[key],'COMPLETION_DISPATCH_POLICY_MISMATCH');
 need(message?.role==='user'&&message.source?.kind==='hcx-index-native-abi'&&message.source.ticketId===ticketId&&start.seq>=native.checkpoint.boundary,'COMPLETION_HOST_MESSAGE_MISMATCH');
 nativeCore.assertCheckpoint(native.checkpoint);nativeCore.extension?.assertDispatch(ticketId,message);
 const users=bridge.findEvents({type:'user/message',after:start.seq,before:endSeq});
 need(users.length===1&&equal(users[0].data,message)&&users[0].surfaceOp==='append'&&users[0].sourceEventSeqs===undefined,'COMPLETION_EXACT_INPUT_REQUIRED');
 const steps=bridge.findEvents({type:'step/start',turn,after:start.seq,before:endSeq});
 const ends=bridge.findEvents({type:'step/end',turn,after:start.seq,before:endSeq});
 need(steps.length>0&&steps.length===ends.length,'COMPLETION_STEP_COVERAGE');
 const assistants=bridge.findEvents({type:'assistant/message',turn,after:start.seq,before:endSeq});
 need(assistants.length===steps.length,'ONE_ASSISTANT_PER_STEP_REQUIRED');
 const calls=bridge.findEvents({type:'tool/call',turn,after:start.seq,before:endSeq});
 const results=bridge.findEvents({type:'tool/result',turn,after:start.seq,before:endSeq});
 const callIds=[],stepHeaders=[];let final=null;
 for(let i=0;i<steps.length;i++){
  const step=steps[i],end=ends[i],assistant=assistants[i];
  need(Number.isSafeInteger(step.data.step)&&step.data.step>=0&&(i===0||step.data.step>steps[i-1].data.step)&&end.data.step===step.data.step&&step.seq<assistant.seq&&assistant.seq<end.seq&&(i===0||ends[i-1].seq<step.seq),'COMPLETION_STEP_ORDER');
  need(assistant.data.step===step.data.step&&assistant.surfaceOp==='append'&&assistant.sourceEventSeqs===undefined&&assistant.data.interrupted!==true,'COMPLETION_ASSISTANT_STEP');
  need(sourceOf(assistant)?.kind==='model'&&sourceOf(assistant).provider===nativeCore.config.provider&&sourceOf(assistant).model===nativeCore.config.model&&assistant.data.message.role==='assistant','COMPLETION_ASSISTANT_POLICY');
  const header=bridge.findEvents({type:'request/header',before:assistant.seq,latest:true}).at(-1);
  need(header&&schemaDigest(header.data.header.tools??[])===schemaDigest(nativeCore.expectedSchemas),'COMPLETION_STEP_SCHEMA');
  // This candidate supports an exact explicitly configured request policy.
  // Unknown config shapes fail closed; official compatibility is not claimed.
  for(const key of ['provider','model','maxTokens','reasoningEffort'])need(header.data.header.config[key]===nativeCore.config[key],'COMPLETION_STEP_POLICY');
  stepHeaders.push({stepSeq:step.seq,turn,step:step.data.step,headerSeq:header.seq,headerDigest:hash(header)});
  const content=assistant.data.message.content;
  need(Array.isArray(content)&&content.length===1,'COMPLETION_SINGLE_BLOCK_REQUIRED');
  if(content[0].type==='text'){
   need(i===steps.length-1&&typeof content[0].text==='string'&&content[0].text.length>0&&!final,'UNIQUE_FINAL_TEXT_ASSISTANT_REQUIRED');
   need(!calls.some(e=>e.data.step===step.data.step)&&!results.some(e=>e.data.step===step.data.step),'FINAL_STEP_HAS_TOOL_SOURCE');
   final={raw:content[0].text,assistantSeq:assistant.seq};continue;
  }
  need(!final&&i<steps.length-1&&content[0].type==='tool-call','NONFINAL_NATIVE_TOOL_STEP_REQUIRED');
  const block=content[0],stepCalls=calls.filter(e=>e.data.step===step.data.step),stepResults=results.filter(e=>e.data.step===step.data.step);
  need(stepCalls.length===1&&stepResults.length===1&&!callIds.includes(block.id),'EXACT_SINGLE_NATIVE_PAIR_REQUIRED');
  const call=stepCalls[0],result=stepResults[0],evidence=nativeCore.evidence(block.id);
  need(call.seq>assistant.seq&&result.seq>call.seq&&result.seq<end.seq&&call.data.callId===block.id&&call.data.name===block.name&&call.data.arguments===block.arguments,'COMPLETION_NATIVE_PAIR_ORDER');
  need(evidence.call.dispatchId===ticketId&&evidence.call.callId===block.id&&evidence.call.assistantSeq===assistant.seq&&evidence.call.assistantDigest===hash(assistant)&&evidence.call.toolCallSeq===call.seq&&evidence.call.toolCallDigest===hash(call),'COMPLETION_NATIVE_CALL_ANCHOR');
  for(const key of scope)need(evidence.call[key]===identity[key],'COMPLETION_NATIVE_CALL_POLICY');
  const observed=nativeCore.verifyResult(evidence.call,evidence.final);
  need(evidence.complete&&evidence.source&&evidence.source.eventSeq===result.seq&&evidence.source.eventDigest===hash(result)&&observed.eventSeq===result.seq&&observed.eventDigest===hash(result)&&equal(result.sourceEventSeqs,[call.seq]),'COMPLETION_NATIVE_RESULT_ANCHOR');
  need(evidence.complete.eventSeq===result.seq&&evidence.complete.eventDigest===hash(result)&&evidence.complete.isError===observed.isError&&evidence.source.isError===observed.isError,'COMPLETION_NATIVE_TERMINAL_MISMATCH');
  // This candidate accepts successful observed reads only. A known tool error
  // is retained but requires a separate reviewed policy, not an inferred choice.
  need(observed.isError===false,'COMPLETION_NATIVE_ERROR_HELD');
  nativeCore.assertObserved(block.id);
  callIds.push(block.id);
 }
 need(final&&calls.length===callIds.length&&results.length===callIds.length,'FINAL_DECISION_WITH_COMPLETE_NATIVE_COVERAGE_REQUIRED');
 // The retained chain is incremental and anchored at this exact turn end.
 // It is NOT the sealed single-turn adapter's hash(JSON.stringify(fullPrefix)).
 const tail=bridge.db.prepare('SELECT digest,chain FROM originals WHERE seq=?').get(endSeq);
 need(tail?.digest===hash(ending)&&/^[0-9a-f]{64}$/.test(tail.chain),'COMPLETION_CHAIN_ANCHOR_REQUIRED');
 return{...final,sessionId:identity.sessionId,endSeq,boundary:endSeq+1,prefixHash:tail.chain,prefixHashVersion:'hcx-rolling-history-chain/v1',sourceHeaderDigest:checkpoint.headerDigest,turn,callIds,stepSeqs:steps.map(s=>s.seq),stepHeaders};
}
