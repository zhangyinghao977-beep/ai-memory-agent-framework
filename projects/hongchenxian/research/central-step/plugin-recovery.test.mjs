import test from 'node:test';import assert from 'node:assert/strict';
import {mkdtempSync,readFileSync,renameSync,copyFileSync} from 'node:fs';import {tmpdir} from 'node:os';import {join} from 'node:path';
import {openReferenceState,validateRegistry,VERSION} from './reference-state.mjs';
const registry=()=>({version:VERSION,poolId:'new-synthetic-central-pool',policy:{epoch:'central-reference-v1',digest:'d'.repeat(64)},members:Array.from({length:10},(_,i)=>({actorId:'central-test-'+i,sessionId:'central-session-'+i}))});
const root=()=>mkdtempSync(join(tmpdir(),'hcx-plugin-state-'));

test('actual reference state opens ten pinned identities, reads private original and reopens without auto-claim or pin advancement',()=>{
 const path=root(),reg=registry();let state=openReferenceState({root:path,registry:reg,phase:'first'});try{
  const pins=state.pins,b=state.brokers[0],ticket=state.claim(0);assert.equal(state.members.length,10);assert.equal(state.brokers.length,10);
  const hits=b.dispatch({tool:'memory.lookup',input:ticket.sourceRef.lookup}),preview=b.dispatch({tool:'memory.preview',input:{hitHandle:hits.hits[0].hitHandle}}),original=b.dispatch({tool:'memory.read_original',input:{readHandle:preview.readHandle,relevance:'Read exact synthetic original invitation.'}});
  assert.equal(JSON.parse(original.fragments[0].text).kind,'initial');assert.equal(state.members[0].body.rows('claim').length,1);assert.ok(!JSON.stringify(ticket).includes('Synthetic invitation'));
  const originalClaim=JSON.stringify(state.members[0].body.one('claim',ticket.source));state.close();state=openReferenceState({root:path,registry:reg,phase:'reopen'});
  assert.deepEqual(state.pins,pins);assert.equal(JSON.stringify(state.members[0].body.one('claim',ticket.source)),originalClaim);assert.throws(()=>state.claim(0),/TICKET_ALREADY_CLAIMED|EXISTING_CLAIM/);state.verifyTicket(0,ticket);
  assert.equal(state.members[1].body.rows('claim').length,0);assert.equal(state.members[0].body.memories().length,0);
 }finally{state.close();}
});

test('first phase cannot silently replace a saved reference state and changed registry fails before stores open',()=>{
 const path=root(),reg=registry(),state=openReferenceState({root:path,registry:reg,phase:'first'});state.close();const journal=readFileSync(join(path,'reference-state','controller.sqlite.write-journal'),'utf8');
 assert.throws(()=>openReferenceState({root:path,registry:reg,phase:'first'}),/NEW_REFERENCE_STATE_REQUIRED/);
 const changed=structuredClone(reg);changed.members[0].sessionId+='-new';assert.throws(()=>openReferenceState({root:path,registry:changed,phase:'reopen'}),/EXACT_SAVED_REFERENCE_REGISTRY_REQUIRED/);
 assert.equal(readFileSync(join(path,'reference-state','controller.sqlite.write-journal'),'utf8'),journal);
});

test('reopen rejects a replaced store inode even when the replacement bytes are identical, without writing it',()=>{
 const path=root(),reg=registry(),state=openReferenceState({root:path,registry:reg,phase:'first'});state.close();const store=join(path,'reference-state','private-0.sqlite'),old=store+'.retained-original';renameSync(store,old);copyFileSync(old,store);const before=readFileSync(store);
 assert.throws(()=>openReferenceState({root:path,registry:reg,phase:'reopen'}),/REFERENCE_STORE_REPLACED_OR_MISSING/);assert.deepEqual(readFileSync(store),before);
});

test('registry and agent setup require the exact ten identities and root/scoped separation',()=>{
 const reg=registry(),dup=structuredClone(reg);dup.members[9]=dup.members[0];assert.throws(()=>validateRegistry(dup),/UNIQUE_REFERENCE_IDENTITIES_REQUIRED/);
 const state=openReferenceState({root:root(),registry:reg,phase:'first'});try{const agentCtx={},agent={ctx:agentCtx,id:reg.members[0].sessionId,session:{id:reg.members[1].sessionId}};assert.throws(()=>state.bindAgent({agentCtx,agent,persistenceCtx:{},memberIndex:0,config:{},systemMessages:[]}),/EXACT_REGISTERED_AGENT_SETUP_REQUIRED/);assert.equal(state.members[0].body.rows('native-lifecycle-config').length,0);}finally{state.close();}
});

import {runCentralPlugin} from './plugin-runtime.mjs';
import {fakeRuntime} from './sdk-runtime-double.mjs';
import {DeepSeekAdapterDouble,scenarioForward} from './provider-double.mjs';
import {createProtectedWire} from './protected-wire.mjs';
function harness({onBinding}={}){
 const modelConfig={provider:'deepseek-official',model:'deepseek-flash',maxTokens:512,reasoningEffort:'off'};
 const config={root:root(),registry:registry(),phase:'first',memberIndex:0,modelConfig,systemMessages:[{role:'system',content:[{type:'text',text:'Synthetic bounded native retrieval.'}]}],protectedHeaders:{accept:'text/event-stream','anthropic-version':'2023-06-01','content-type':'application/json','user-agent':'synthetic-agent','x-api-key':'synthetic-not-a-credential','x-deepseek-harness-user-id':'synthetic-user'}};
 const scenario=scenarioForward(),dependencies={openReferenceState(args){const state=openReferenceState(args);if(onBinding){const bind=state.bindAgent;state.bindAgent=options=>{const result=bind(options);onBinding(result,args.phase);return result;};}return state;},createProtectedWire,forwardOffline:scenario.forward,providerOptions:getWire=>({fetch:(...args)=>getWire().fetch(...args),headers:config.protectedHeaders})};
 return{config,dependencies,scenario,sdk:{DeepSeekAdapter:DeepSeekAdapterDouble},runtime:options=>fakeRuntime({modelConfig,...options})};
}
function inspect(h,fn){const s=openReferenceState({root:h.config.root,registry:h.config.registry,phase:'reopen'});try{return fn(s);}finally{s.close();}}

test('same actual plugin drives followup/native/wire/final/shortref and reopens the same session with zero new dispatch',async()=>{
 const h=harness(),runtime=h.runtime(),first=await runCentralPlugin(runtime.ctx,h.config,h.sdk,h.dependencies);
 assert.equal(first.status,'passed');assert.equal(first.streams,4);assert.equal(first.officialRuntimeExecuted,false);assert.equal(first.handlesClosed,true);assert.equal(runtime.stats.followups,1);assert.equal(runtime.stats.bodies,3);assert.equal(h.scenario.calls,4);assert.equal(runtime.stats.scopedServiceReads,0);assert.equal(runtime.stats.opens,runtime.stats.closes);
 const sessionId=h.config.registry.members[0].sessionId,prefix=structuredClone(runtime.states.get(sessionId).durable);
 const saved=inspect(h,state=>{const body=state.members[0].body;assert.equal(body.memories().length,1);assert.equal(body.state().mode,'stopped');assert.equal(state.poolBody.rows('assembly-staged').length,1);assert.equal(state.router.publicView(state.roundId).opinions.length,0);assert.equal(state.poolBody.rows('step-http-spent').length,4);assert.equal(state.poolBody.rows('protected-wire-settlement').length,4);assert.ok(!JSON.stringify(state.poolBody.memory.events()).includes('synthetic-not-a-credential'));assert.ok(!JSON.stringify(body.rows('claim')).includes('Synthetic invitation'));return{source:body.rows('source').at(-1),receipt:body.rows('native-lifecycle-receipt')[0],pins:state.pins};});
 const resumed=h.runtime({states:runtime.states}),second=await runCentralPlugin(resumed.ctx,{...h.config,phase:'reopen'},h.sdk,h.dependencies);
 assert.equal(second.status,'passed');assert.equal(second.streams,0);assert.equal(resumed.stats.followups,0);assert.equal(resumed.stats.bodies,0);assert.equal(h.scenario.calls,4);assert.equal(resumed.stats.scopedServiceReads,0);assert.equal(resumed.stats.opens,resumed.stats.closes);
 assert.deepEqual(resumed.states.get(sessionId).durable.slice(0,prefix.length),prefix);
 inspect(h,state=>{assert.deepEqual(state.pins,saved.pins);assert.deepEqual(state.members[0].body.rows('native-lifecycle-receipt')[0],saved.receipt);assert.deepEqual(state.members[0].body.rows('source').at(-1),saved.source);assert.equal(state.poolBody.rows('assembly-staged').length,1);});
});

test('same plugin latches an SDK-swallowed premature stream and performs no native/tool/forward work',async()=>{
 const h=harness(),runtime=h.runtime({faults:{startupAttempt:true}}),report=await runCentralPlugin(runtime.ctx,h.config,h.sdk,h.dependencies);
 assert.equal(report.status,'error');assert.equal(report.failureCode,'ADMISSION_CLOSED');assert.equal(report.streams,0);assert.equal(h.scenario.calls,0);assert.equal(runtime.stats.followups,0);assert.equal(runtime.stats.bodies,0);assert.equal(runtime.stats.probes[0].rejected,true);
 inspect(h,state=>{assert.equal(state.members[0].body.rows('claim').length,0);assert.equal(state.members[0].body.memories().length,0);assert.equal(state.poolBody.rows('step-http-spent').length,0);});
});

for(const fault of ['unknown-result','missing-result'])test('same plugin '+fault+' stays unresolved after reopen without repeating the native read or HTTP step',async()=>{
 const h=harness(),runtime=h.runtime({faults:{materializeEvent(event){if(event.type==='tool/result'){if(fault==='missing-result')throw Error('SYNTHETIC_MISSING_RESULT_CUT');event.data.error={code:'TOOL_OUTCOME_UNKNOWN'};}return event;}}});
 const first=await runCentralPlugin(runtime.ctx,h.config,h.sdk,h.dependencies);assert.equal(first.status,'error');assert.equal(runtime.stats.bodies,1);assert.equal(h.scenario.calls,1);
 inspect(h,state=>{assert.equal(state.members[0].body.memories().length,0);assert.equal(state.members[0].body.rows('native-lifecycle-receipt').length,0);assert.equal(state.poolBody.rows('assembly-staged').length,0);});
 const resumed=h.runtime({states:runtime.states}),second=await runCentralPlugin(resumed.ctx,{...h.config,phase:'reopen'},h.sdk,h.dependencies);
 assert.notEqual(second.status,'passed');assert.equal(second.streams,0);assert.equal(resumed.stats.followups,0);assert.equal(resumed.stats.bodies,0);assert.equal(h.scenario.calls,1);
});

for(const cut of ['after-capture','after-accept'])test('same plugin '+cut+' without receipt reopens from complete source with no automatic redispatch',async()=>{
 let armed=true;const h=harness({onBinding(binding,phase){if(phase==='first')binding.adapter.onCut=point=>{if(armed&&point===cut){armed=false;const error=Error('SYNTHETIC_CAPTURE_WINDOW');error.syntheticCrash=true;throw error;}};}}),runtime=h.runtime();
 const first=await runCentralPlugin(runtime.ctx,h.config,h.sdk,h.dependencies);assert.equal(first.status,'error');assert.equal(first.streams,4);assert.equal(h.scenario.calls,4);assert.equal(runtime.stats.bodies,3);
 const saved=inspect(h,state=>{const body=state.members[0].body;assert.equal(body.rows('native-captured-completion').length,1);assert.equal(body.rows('native-lifecycle-receipt').length,0);assert.equal(body.memories().length,cut==='after-accept'?1:0);assert.equal(state.poolBody.rows('assembly-staged').length,0);return{sources:body.rows('source'),capture:body.rows('native-captured-completion')[0]};});
 const resumed=h.runtime({states:runtime.states}),second=await runCentralPlugin(resumed.ctx,{...h.config,phase:'reopen'},h.sdk,h.dependencies);
 assert.equal(second.status,'passed');assert.equal(second.failureCode,'NONE');assert.equal(second.sourceVerified,true);assert.equal(second.streams,0);assert.equal(h.scenario.calls,4);assert.equal(resumed.stats.bodies,0);assert.equal(resumed.stats.followups,0);
 inspect(h,state=>{assert.deepEqual(state.members[0].body.rows('source').slice(0,saved.sources.length),saved.sources);assert.deepEqual(state.members[0].body.rows('native-captured-completion')[0],saved.capture);assert.equal(state.members[0].body.rows('native-lifecycle-receipt').length,1);assert.equal(state.members[0].body.memories().length,1);assert.equal(state.poolBody.rows('assembly-staged').length,1);});
});

test('same plugin surfaces cleanup failure without exposing raw exception text as safe diagnostics',async()=>{
 const h=harness({onBinding(binding){const original=binding.dispose;binding.dispose=()=>{original();throw Error('SYNTHETIC_PRIVATE_RAW_CLEANUP_DETAIL');};}}),runtime=h.runtime(),report=await runCentralPlugin(runtime.ctx,h.config,h.sdk,h.dependencies);
 assert.equal(report.status,'error');assert.equal(report.handlesClosed,false);assert.equal(report.failureCode,'CLEANUP_FAILURE');assert.ok(!JSON.stringify(report).includes('SYNTHETIC_PRIVATE_RAW_CLEANUP_DETAIL'));assert.equal(h.scenario.calls,4);
});

for(const cut of ['after-capture','after-accept','after-receipt'])test('same plugin '+cut+' recovery is idempotent across three reopens with no new model or tool execution',async()=>{
 let armed=true;const h=harness({onBinding(binding,phase){if(phase==='first')binding.adapter.onCut=point=>{if(armed&&point===cut){armed=false;const e=Error('SYNTHETIC_COMMIT_WINDOW');e.syntheticCrash=true;throw e;}};}}),runtime=h.runtime();
 const first=await runCentralPlugin(runtime.ctx,h.config,h.sdk,h.dependencies);assert.equal(first.status,'error');assert.equal(h.scenario.calls,4);
 const id=h.config.registry.members[0].sessionId,prefix=structuredClone(runtime.states.get(id).durable);
 let stable;
 for(let i=0;i<3;i++){
  const resumed=h.runtime({states:runtime.states}),report=await runCentralPlugin(resumed.ctx,{...h.config,phase:'reopen'},h.sdk,h.dependencies);
  assert.equal(report.status,'passed');assert.equal(report.sourceVerified,true);assert.equal(report.streams,0);assert.equal(report.handlesClosed,true);
  assert.equal(resumed.stats.followups,0);assert.equal(resumed.stats.bodies,0);assert.equal(h.scenario.calls,4);
  assert.deepEqual(runtime.states.get(id).durable.slice(0,prefix.length),prefix);
  const current=inspect(h,s=>{const b=s.members[0].body;assert.equal(b.memories().length,1);assert.equal(b.rows('native-lifecycle-receipt').length,1);assert.equal(b.rows('native-recovery-intent').length,1);assert.equal(b.rows('native-recovery-commit').length,1);assert.equal(s.poolBody.rows('protected-wire-settlement').length,4);assert.equal(s.poolBody.rows('assembly-staged').length,1);return{receipt:b.rows('native-lifecycle-receipt'),intent:b.rows('native-recovery-intent'),commit:b.rows('native-recovery-commit'),sources:b.rows('source'),settled:s.poolBody.rows('protected-wire-settlement'),spent:s.poolBody.rows('step-http-spent')};});
  if(stable)assert.deepEqual(current,stable);stable=current;
 }
});

test('same plugin refuses changed persisted official source on reopen without another forward',async()=>{
 const h=harness(),runtime=h.runtime();assert.equal((await runCentralPlugin(runtime.ctx,h.config,h.sdk,h.dependencies)).status,'passed');
 const source=runtime.states.get(h.config.registry.members[0].sessionId);source.durable.find(e=>e.type==='assistant/message').data.message.content=[{type:'text',text:'Synthetic wrong source'}];
 for(let i=0;i<2;i++){const resumed=h.runtime({states:runtime.states}),r=await runCentralPlugin(resumed.ctx,{...h.config,phase:'reopen'},h.sdk,h.dependencies);assert.notEqual(r.status,'passed');assert.equal(r.sourceVerified,false);assert.equal(r.streams,0);assert.equal(resumed.stats.followups,0);assert.equal(h.scenario.calls,4);}
});

test('same plugin refuses a counterfeit receipt view without rewriting the original receipt or dispatching',async()=>{
 const h=harness(),runtime=h.runtime();assert.equal((await runCentralPlugin(runtime.ctx,h.config,h.sdk,h.dependencies)).status,'passed');
 const saved=inspect(h,s=>s.members[0].body.rows('native-lifecycle-receipt'));
 const deps={...h.dependencies,openReferenceState(args){const s=h.dependencies.openReferenceState(args),body=s.members[0].body,one=body.one.bind(body),rows=body.rows.bind(body);const change=x=>({...x,rawDigest:'0'.repeat(64)});body.one=(kind,id)=>{const value=one(kind,id);return kind==='native-lifecycle-receipt'&&value?change(value):value;};body.rows=kind=>{const values=rows(kind);return kind==='native-lifecycle-receipt'?values.map(r=>({...r,data:change(r.data)})):values;};return s;}};
 const resumed=h.runtime({states:runtime.states}),r=await runCentralPlugin(resumed.ctx,{...h.config,phase:'reopen'},h.sdk,deps);assert.notEqual(r.status,'passed');assert.equal(r.sourceVerified,false);assert.equal(r.streams,0);assert.equal(h.scenario.calls,4);assert.equal(resumed.stats.followups,0);inspect(h,s=>assert.deepEqual(s.members[0].body.rows('native-lifecycle-receipt'),saved));
});

test('same plugin rejects an extra durable foreign receipt and preserves it for audit without redispatch',async()=>{
 const h=harness(),runtime=h.runtime();assert.equal((await runCentralPlugin(runtime.ctx,h.config,h.sdk,h.dependencies)).status,'passed');
 const before=inspect(h,s=>{const b=s.members[0].body,original=b.rows('native-lifecycle-receipt')[0].data;b.tx(()=>b.put('native-lifecycle-receipt','synthetic-foreign-ticket',{...original,ticketId:'synthetic-foreign-ticket'}));return b.rows('native-lifecycle-receipt');});
 for(let i=0;i<2;i++){const resumed=h.runtime({states:runtime.states}),r=await runCentralPlugin(resumed.ctx,{...h.config,phase:'reopen'},h.sdk,h.dependencies);assert.notEqual(r.status,'passed');assert.equal(r.sourceVerified,false);assert.equal(r.streams,0);assert.equal(resumed.stats.followups,0);assert.equal(h.scenario.calls,4);inspect(h,s=>{assert.deepEqual(s.members[0].body.rows('native-lifecycle-receipt'),before);assert.equal(s.members[0].body.rows('native-recovery-intent').length,0);});}
});

test('same plugin retries only local staging after recovery settlement committed and staging was interrupted',async()=>{
 let armed=true;const h=harness({onBinding(binding,phase){if(phase==='first')binding.adapter.onCut=point=>{if(armed&&point==='after-accept'){armed=false;const e=Error('SYNTHETIC_ACCEPT_WINDOW');e.syntheticCrash=true;throw e;}};}}),runtime=h.runtime();
 assert.equal((await runCentralPlugin(runtime.ctx,h.config,h.sdk,h.dependencies)).status,'error');
 const interrupted={...h.dependencies,openReferenceState(args){const s=h.dependencies.openReferenceState(args);s.accept=()=>{throw Error('SYNTHETIC_STAGING_CUT');};return s;}};
 const r=await runCentralPlugin(h.runtime({states:runtime.states}).ctx,{...h.config,phase:'reopen'},h.sdk,interrupted);assert.equal(r.status,'error');assert.equal(r.sourceVerified,false);assert.equal(h.scenario.calls,4);
 inspect(h,s=>{assert.equal(s.members[0].body.rows('native-recovery-commit').length,1);assert.equal(s.poolBody.rows('protected-wire-settlement').length,4);assert.equal(s.poolBody.rows('assembly-staged').length,0);});
 const resumed=h.runtime({states:runtime.states}),success=await runCentralPlugin(resumed.ctx,{...h.config,phase:'reopen'},h.sdk,h.dependencies);assert.equal(success.status,'passed');assert.equal(success.streams,0);assert.equal(resumed.stats.followups,0);assert.equal(resumed.stats.bodies,0);assert.equal(h.scenario.calls,4);
 inspect(h,s=>{assert.equal(s.members[0].body.memories().length,1);assert.equal(s.members[0].body.rows('native-recovery-commit').length,1);assert.equal(s.poolBody.rows('assembly-staged').length,1);});
});
