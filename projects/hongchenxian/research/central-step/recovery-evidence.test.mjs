// All faults target NEW synthetic state. Append-only storage guards remain intact.
// Changed/missing evidence uses explicit read-view faults; extra records are actual
// durable appends. No sealed/original database or constraint is changed.
import test from 'node:test';import assert from 'node:assert/strict';
import {mkdtempSync} from 'node:fs';import {tmpdir} from 'node:os';import {join} from 'node:path';
import {openReferenceState,VERSION} from './reference-state.mjs';
import {runCentralPlugin} from './plugin-runtime.mjs';import {fakeRuntime} from './sdk-runtime-double.mjs';
import {DeepSeekAdapterDouble,scenarioForward} from './provider-double.mjs';import {createProtectedWire} from './protected-wire.mjs';
const registry=()=>({version:VERSION,poolId:'recovery-proof-synthetic',policy:{epoch:'reference-v1',digest:'e'.repeat(64)},members:Array.from({length:10},(_,i)=>({actorId:'proof-actor-'+i,sessionId:'proof-session-'+i}))});
function harness(cut='after-capture',{sleep=false}={}){
 const modelConfig={provider:'deepseek-official',model:'deepseek-flash',maxTokens:512,reasoningEffort:'off'};
 const config={root:mkdtempSync(join(tmpdir(),'hcx-recovery-proof-')),registry:registry(),phase:'first',memberIndex:0,modelConfig,systemMessages:[{role:'system',content:[{type:'text',text:'Synthetic recovery proof policy.'}]}],protectedHeaders:{accept:'text/event-stream','anthropic-version':'2023-06-01','content-type':'application/json','user-agent':'synthetic-agent','x-api-key':'synthetic-not-a-credential','x-deepseek-harness-user-id':'synthetic-user'}};
 let armed=true;const overlays=[];const scenario=scenarioForward();
 const deps={openReferenceState(args){const state=openReferenceState(args);if(args.phase==='reopen')for(const fn of overlays)fn(state);const bind=state.bindAgent;state.bindAgent=options=>{const result=bind(options);if(args.phase==='first')result.adapter.onCut=point=>{if(armed&&point===cut){armed=false;throw Object.assign(Error('SYNTHETIC_RECOVERY_CUT'),{syntheticCrash:true});}};return result;};return state;},createProtectedWire,forwardOffline:async(...args)=>{const response=await scenario.forward(...args);if(!sleep)return response;const chunks=await response.json();for(const chunk of chunks)if(chunk.block?.type==='text'){const choice=JSON.parse(chunk.block.text);choice.action='sleep';choice.wake_at=1;chunk.block.text=JSON.stringify(choice);}return new Response(JSON.stringify(chunks));},providerOptions:get=>({fetch:(...args)=>get().fetch(...args),headers:config.protectedHeaders})};
 const first=fakeRuntime({modelConfig}),sdk={DeepSeekAdapter:DeepSeekAdapterDouble};
 return{config,deps,scenario,first,sdk,corrupt(fn){overlays.push(fn);},inspect(fn){const s=openReferenceState({root:config.root,registry:config.registry,phase:'reopen'});try{for(const overlay of overlays)overlay(s);return fn(s);}finally{s.close();}},async start(){const report=await runCentralPlugin(first.ctx,config,sdk,deps);assert.equal(report.status,'error');assert.equal(scenario.calls,4);return report;},async reopen(){const runtime=fakeRuntime({modelConfig,states:first.states});const report=await runCentralPlugin(runtime.ctx,{...config,phase:'reopen'},sdk,deps);assert.equal(runtime.stats.followups,0);assert.equal(runtime.stats.bodies,0);assert.equal(scenario.calls,4);return report;}};
}
function row(body,kind){return body.rows(kind)[0];}
function change(body,kind,mutate){const r=row(body,kind);assert.ok(r);const data=structuredClone(r.data);mutate(data);const one=body.one.bind(body),rows=body.rows.bind(body);body.one=(k,id)=>k===kind&&id===r.subject?structuredClone(data):one(k,id);body.rows=k=>rows(k).map(x=>k===kind&&x.subject===r.subject?{...x,data:structuredClone(data)}:x);}
function remove(body,kind){const r=row(body,kind);assert.ok(r);const one=body.one.bind(body),rows=body.rows.bind(body);body.one=(k,id)=>k===kind&&id===r.subject?null:one(k,id);body.rows=k=>rows(k).filter(x=>!(k===kind&&x.subject===r.subject));}
const cases=[
 ['capture raw changed','after-capture',s=>change(s.members[0].body,'native-captured-completion',d=>{d.raw+=' ';})],
 ['spent digest changed','after-capture',s=>change(s.poolBody,'step-http-spent',d=>{d.admissionDigest='0'.repeat(64);})],
 ['wire binding missing','after-capture',s=>remove(s.poolBody,'protected-step-wire')],
 ['response witness missing','after-capture',s=>remove(s.poolBody,'step-http-response')],
 ['one step admission missing','after-capture',s=>remove(s.members[0].body,'native-step-admission')],
 ['known settlement digest changed','after-capture',s=>change(s.poolBody,'step-http-settlement',d=>{d.spentDigest='0'.repeat(64);})],
 ['extra settlement subject','after-capture',s=>s.poolBody.tx(()=>s.poolBody.put('step-http-settlement','unrelated',{unknown:true}))],
 ['extra wire settlement subject','after-capture',s=>s.poolBody.tx(()=>s.poolBody.put('protected-wire-settlement','unrelated',{unknown:true}))],
 ['extra recovery intent','after-capture',s=>s.members[0].body.tx(()=>s.members[0].body.put('native-recovery-intent','unrelated',{unknown:true}))],
 ['accepted source without capture','after-accept',s=>remove(s.members[0].body,'native-captured-completion')],
 ['thought metadata disagrees with accepted source','after-accept',s=>{const b=s.members[0].body,r=b.memory.events('paragraph')[0],one=b.memory.one.bind(b.memory);b.memory.one=(kind,id)=>kind==='paragraph'&&id===r.subject?{...r,data:{...r.data,chain:'unrelated-chain'}}:one(kind,id);} ],
 ['unknown terminal never upgraded','after-capture',s=>change(s.poolBody,'step-http-terminal',d=>{d.reason='upstream-abort';})],
];
for(const[name,cut,corrupt]of cases)test(name+' rejects repair before receipt, without any redispatch',async()=>{
 const h=harness(cut);await h.start();h.corrupt(corrupt);const before=h.inspect(s=>({sources:s.members[0].body.rows('source'),receipts:s.members[0].body.rows('native-lifecycle-receipt'),processed:s.members[0].body.rows('processed')}));const report=await h.reopen();assert.notEqual(report.status,'passed');assert.equal(report.sourceVerified,false);h.inspect(s=>{const b=s.members[0].body;assert.deepEqual(b.rows('source'),before.sources);assert.deepEqual(b.rows('processed'),before.processed);assert.deepEqual(b.rows('native-lifecycle-receipt'),before.receipts);assert.equal(b.rows('native-recovery-commit').length,0);assert.equal(s.poolBody.rows('assembly-staged').length,0);});
});
test('a later legitimate wake after accepted sleep is held, never overwritten or re-decided',async()=>{const h=harness('after-accept',{sleep:true});await h.start();const state=h.inspect(s=>{const b=s.members[0].body;assert.equal(b.state().mode,'sleeping');assert.equal(b.wake(2,b.state().source),true);return b.state();});const report=await h.reopen();assert.notEqual(report.status,'passed');h.inspect(s=>{const b=s.members[0].body;assert.deepEqual(b.state(),state);assert.equal(b.rows('native-lifecycle-receipt').length,0);assert.equal(b.rows('native-recovery-intent').length,0);assert.equal(b.rows('native-recovery-commit').length,0);});});
