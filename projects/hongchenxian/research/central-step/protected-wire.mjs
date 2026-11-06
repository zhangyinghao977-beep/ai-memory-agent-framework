import {AsyncLocalStorage} from 'node:async_hooks';
import {createHash} from 'node:crypto';
import {isDeepStrictEqual as equal} from 'node:util';
import {StepTransport} from './vendor/hcx-native-lifecycle-adapter-20261106-v02/step-transport.mjs';
import {SCHEMAS} from './vendor/hcx-round-recall-bridge-20261106-v01/round-recall.mjs';
export const PREPARATION_LOCK=true;
export const ENDPOINT='https://api.deepseek.com/anthropic/v1/messages';
export const VERSION='hcx-protected-step-wire/v1';
const hash=x=>createHash('sha256').update(typeof x==='string'?x:JSON.stringify(x)).digest('hex');
const need=(ok,code)=>{if(!ok)throw Error(code);};
const copy=x=>JSON.parse(JSON.stringify(x));
const exactKeys=(o,keys)=>need(o&&typeof o==='object'&&!Array.isArray(o)&&Object.keys(o).every(k=>keys.includes(k)),'UNSUPPORTED_WIRE_FIELDS');
const text=blocks=>{need(Array.isArray(blocks),'TEXT_BLOCKS_REQUIRED');return blocks.flatMap(b=>{exactKeys(b,['type','text']);need(b.type==='text'&&typeof b.text==='string','TEXT_ONLY_REQUIRED');return b.text?[{type:'text',text:b.text}]:[];});};
// Semantic validation specification from saved public rc.5 serialize.ts. It is
// NOT used to dispatch a replacement body, nor represented as executed SDK code.
export function expectedWire(options){
 need(options?.provider==='deepseek-official'&&options.model==='deepseek-flash'&&options.maxTokens===512&&options.reasoningEffort==='off','PINNED_PROVIDER_CONFIG_REQUIRED');
 for(const key of ['system','temperature','stop','purpose'])need(options[key]===undefined,'UNSUPPORTED_REQUEST_POLICY');
 need(equal(options.tools,SCHEMAS),'EXACT_NATIVE_SCHEMAS_REQUIRED');
 need(Array.isArray(options.messages),'REQUEST_MESSAGES_REQUIRED');
 let system;const messages=[];
 for(const m of options.messages){
  need(['system','user','assistant','tool'].includes(m.role),'UNSUPPORTED_MESSAGE_ROLE');
  if(m.role==='system'){need(system===undefined&&messages.length===0,'EXACT_HEAD_SYSTEM_REQUIRED');system=text(m.content).map(b=>b.text).join('');continue;}
  let content,role=m.role;
  if(role==='assistant')content=m.content.flatMap(b=>{
   if(b.type==='text')return text([b]);
   exactKeys(b,['type','id','name','arguments']);need(b.type==='tool-call'&&typeof b.id==='string'&&b.id&&SCHEMAS.some(s=>s.name===b.name)&&typeof b.arguments==='string','UNSUPPORTED_ASSISTANT_BLOCK');
   let input;try{input=JSON.parse(b.arguments);}catch{throw Error('INVALID_TOOL_ARGUMENT_HISTORY');}
   need(input&&typeof input==='object'&&!Array.isArray(input),'OBJECT_TOOL_ARGUMENT_HISTORY_REQUIRED');
   return[{type:'tool_use',id:b.id,name:b.name,input}];
  });
  else if(role==='tool'){
   need(typeof m.toolCallId==='string'&&m.toolCallId&&(m.isError===undefined||typeof m.isError==='boolean'),'TOOL_RESULT_ID_REQUIRED');role='user';content=[{type:'tool_result',tool_use_id:m.toolCallId,content:text(m.content),...m.isError===undefined?{}:{is_error:m.isError}}];
  }else content=text(m.content);
  if(!content.length)continue;
  if(messages.at(-1)?.role===role)messages.at(-1).content.push(...content);else messages.push({role,content});
 }
 need(typeof system==='string'&&system.length>0&&messages.length>0&&messages[0].role==='user','SYSTEM_AND_USER_REQUIRED');
 let pending=new Set();
 for(const m of messages){if(m.role==='assistant'){const calls=m.content.filter(b=>b.type==='tool_use');pending=new Set(calls.map(b=>b.id));need(pending.size===calls.length,'DUPLICATE_TOOL_CALL');}else{const results=m.content.filter(b=>b.type==='tool_result');for(const r of results)need(pending.delete(r.tool_use_id),'UNBOUND_TOOL_RESULT');need(pending.size===0,'UNRESOLVED_TOOL_HISTORY');m.content=[...results,...m.content.filter(b=>b.type!=='tool_result')];}}
 need(pending.size===0,'UNRESOLVED_TOOL_HISTORY');
 return{model:options.model,stream:true,messages,max_tokens:512,thinking:{type:'disabled'},system,tools:options.tools.map(t=>({name:t.name,description:t.description,input_schema:t.parameters}))};
}
function protectedSet(input){const h=new Headers(input);const names=['accept','anthropic-version','content-type','user-agent','x-api-key','x-deepseek-harness-user-id'].sort();need(equal([...h.keys()].sort(),names),'PROTECTED_HEADER_SET');need(h.get('accept')==='text/event-stream'&&h.get('content-type')==='application/json'&&h.get('anthropic-version')==='2023-06-01'&&names.every(n=>h.get(n)),'PROTECTED_HEADER_POLICY');return h;}
export function createProtectedWire({poolBody,members,protectedHeaders,forwardOffline,timeoutMs=30000}){
 need(typeof forwardOffline==='function','SYNTHETIC_FORWARD_REQUIRED');
 const headers=protectedSet(protectedHeaders),scope=new AsyncLocalStorage();let activeScopes=0,processFatal=false;
 poolBody.tx(()=>poolBody.put('protected-wire-policy','policy',{version:VERSION,endpoint:ENDPOINT,schemaDigest:hash(SCHEMAS),headerNames:[...headers.keys()]}));
 const hold=(c,code)=>{processFatal=true;const key=c?.key??'unscoped';if(!poolBody.one('protected-wire-hold',key))poolBody.tx(()=>poolBody.put('protected-wire-hold',key,{code,...c?{target:c.target}:{}}));};
 const gate=new StepTransport({poolBody,members,timeoutMs,forward:async(options,{signal,target})=>{
  need(!processFatal&&poolBody.rows('protected-wire-hold').length===0,'PROTECTED_WIRE_HELD');
  const c=scope.getStore();need(c?.wire&&c.spending&&equal(c.target,target)&&hash(options)===c.optionsDigest,'NO_PROTECTED_NATIVE_SCOPE');
  const record=poolBody.one('protected-step-wire',c.key);need(record?.wireDigest===hash(c.wire.body)&&record.optionsDigest===hash(options),'DURABLE_WIRE_BINDING_REQUIRED');
  const outgoing=new Headers(headers);outgoing.set('x-deepseek-harness-session-id',target.sessionId);
  const fused=AbortSignal.any([signal,c.wire.signal]);
  // Exact SDK-provided body is forwarded unchanged. Header values remain closure-private.
  return forwardOffline(ENDPOINT,{method:'POST',redirect:'error',headers:outgoing,body:c.wire.body,signal:fused},{target:copy(target)});
 }});
 const fetch=async(input,init)=>{
  const c=scope.getStore();if(processFatal||poolBody.rows('protected-wire-hold').length){throw Error('PROTECTED_WIRE_HELD');}if(!c||c.used||c.closing){hold(c,'UNSCOPED_OR_REUSED_FETCH');throw Error('UNSCOPED_OR_REUSED_FETCH');}c.used=true;
  try{
   need((typeof input==='string'?input:input instanceof URL?input.href:null)===ENDPOINT,'EXACT_ENDPOINT_REQUIRED');
   exactKeys(init,['method','headers','body','signal','redirect']);
   need(init.method==='POST'&&init.redirect==='error'&&typeof init.body==='string'&&init.signal instanceof AbortSignal,'EXACT_FETCH_SHAPE_REQUIRED');
   need(Buffer.byteLength(init.body)<=32768,'WIRE_WORK_LIMIT');
   const actualHeaders=new Headers(init.headers),expectedHeaders=new Headers(headers);expectedHeaders.set('x-deepseek-harness-session-id',c.target.sessionId);
   need(equal([...actualHeaders],[...expectedHeaders]),'FETCH_HEADER_MISMATCH');
   let wire;try{wire=JSON.parse(init.body);}catch{throw Error('INVALID_WIRE_JSON');}
   need(init.body===JSON.stringify(wire),'NONCANONICAL_OR_DUPLICATE_JSON_KEYS');
   need(equal(wire,expectedWire(c.options)),'SERIALIZED_BODY_MISMATCH');
   c.wire={body:init.body,signal:init.signal};
   const binding={version:VERSION,target:c.target,optionsDigest:c.optionsDigest,wireDigest:hash(init.body),wireBytes:Buffer.byteLength(init.body),endpoint:ENDPOINT,method:'POST'};
   poolBody.tx(()=>poolBody.put('protected-step-wire',c.key,binding));
   need(!processFatal&&poolBody.rows('protected-wire-hold').length===0,'PROTECTED_WIRE_HELD');
   c.spending=true;return await gate.forwardStep(c.target,c.options,{signal:c.options.signal});
  }catch(error){
   // Keep failure diagnostics fixed and exclude exception/header/body contents.
   hold(c,'PROTECTED_WIRE_REJECTED');
   throw Error('PROTECTED_WIRE_REJECTED',{cause:undefined});
  }
 };
 async function*scopeIterator({target,options},makeIterator){
  need(!processFatal&&poolBody.rows('protected-wire-hold').length===0,'PROTECTED_WIRE_HELD');
  const c={target:copy(target),options:{...copy(options),...options.signal?{signal:options.signal}:{}},optionsDigest:hash(options),key:hash([target.actorId,target.sessionId,target.ticketId,target.stepSeq]),used:false,spending:false};
  let it;try{expectedWire(c.options);it=scope.run(c,()=>makeIterator()[Symbol.asyncIterator]());}catch(error){hold(c,'PROTECTED_SCOPE_PREPARATION_FAILED');throw Error('PROTECTED_SCOPE_FAILED');}let done=false;activeScopes++;
  try{
   let item=await scope.run(c,()=>it.next());
   while(!item.done){
    if(item.value?.type==='usage')for await(const chunk of gate.scopeIterator(target,(async function*(){yield item.value;})())){}
    try{yield item.value;}catch(error){if(!it.throw)throw error;c.closing=true;item=await scope.run(c,()=>it.throw(error));continue;}
    item=await scope.run(c,()=>it.next());
   }done=true;
   need(c.used,'MISSING_SERIALIZED_FETCH');
  }catch(error){hold(c,'PROTECTED_SCOPE_FAILED');throw Error('PROTECTED_SCOPE_FAILED');}
  finally{try{if(!done&&it.return){c.closing=true;await scope.run(c,()=>it.return());}}catch(error){hold(c,'PROTECTED_SCOPE_CLEANUP_FAILED');throw Error('PROTECTED_SCOPE_CLEANUP_FAILED');}finally{activeScopes--;}}
 }
 const settleStep=async target=>{
  const key=hash([target.actorId,target.sessionId,target.ticketId,target.stepSeq]),binding=poolBody.one('protected-step-wire',key);need(binding&&!poolBody.one('protected-wire-hold',key),'WIRE_SETTLEMENT_BINDING_REQUIRED');
  const result=await gate.settleStep(target);poolBody.tx(()=>poolBody.put('protected-wire-settlement',key,{bindingDigest:hash(binding),stepSettlementDigest:hash(result)}));return result;
 };
 return Object.freeze({fetch,scopeIterator,settleStep,waitAndSettleStep:async(target,opts)=>{await gate.waitAndSettleStep(target,opts);return settleStep(target);},settleTicket:target=>{const member=members.find(m=>m.body.actorId===target.actorId&&m.body.sessionId===target.sessionId);need(member,'WIRE_TICKET_MEMBER');for(const row of member.body.rows('native-step-admission').filter(r=>r.data.ticketId===target.ticketId)){const key=hash([target.actorId,target.sessionId,target.ticketId,row.data.stepSeq]),bound=poolBody.one('protected-step-wire',key),settled=poolBody.one('protected-wire-settlement',key),step=poolBody.one('step-http-settlement',key);need(bound&&settled&&step&&settled.bindingDigest===hash(bound)&&settled.stepSettlementDigest===hash(step),'WIRE_TICKET_COVERAGE_REQUIRED');}return gate.settleTicket(target);},snapshot:()=>({...gate.snapshot(),fatalHeld:gate.snapshot().fatalHeld||processFatal||poolBody.rows('protected-wire-hold').length>0,activeScopes,wireHeld:processFatal||poolBody.rows('protected-wire-hold').length>0,wireBindings:poolBody.rows('protected-step-wire').length,wireSettled:poolBody.rows('protected-wire-settlement').length,headerValuesLogged:false,realNativeFetchAvailable:false})});
}

// Explicit offline installer; importing this module never captures ambient fetch.
// The caller owns an isolated process. No real-phase selector or fallback exists.
const installedGlobals=new WeakSet();
export function installOfflineFetch(wire,{globalObject=globalThis}={}){
 need(wire&&typeof wire.fetch==='function'&&wire.snapshot().realNativeFetchAvailable===false,'OFFLINE_WIRE_REQUIRED');
 need(!installedGlobals.has(globalObject),'DUPLICATE_FETCH_INSTALL');
 const descriptor=Object.getOwnPropertyDescriptor(globalObject,'fetch');
 need(!descriptor||descriptor.configurable,'FETCH_NOT_CONFIGURABLE');
 Object.defineProperty(globalObject,'fetch',{value:wire.fetch,configurable:true,writable:false});
 installedGlobals.add(globalObject);let restored=false;return()=>{need(!restored&&wire.snapshot().activeScopes===0&&wire.snapshot().currentWorker.inFlight===0,'FETCH_RESTORE_NOT_IDLE');need(globalObject.fetch===wire.fetch,'FETCH_INSTALL_REPLACED');restored=true;installedGlobals.delete(globalObject);if(descriptor)Object.defineProperty(globalObject,'fetch',descriptor);else delete globalObject.fetch;};
}
