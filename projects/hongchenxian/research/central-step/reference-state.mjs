// Persistent NEW synthetic state factory. It never creates an SDK, calls followup,
// sends HTTP, loads an official module, or opens the original ten sessions.
import {mkdirSync,realpathSync,lstatSync,existsSync,readFileSync,openSync,writeFileSync,fsyncSync,closeSync} from 'node:fs';
import {join,resolve} from 'node:path';import {isDeepStrictEqual as equal} from 'node:util';
import {Body,hash} from './vendor/hcx-fish-pool-20261106-v01/body.mjs';
import {ProtectedDuty} from './vendor/hcx-protected-duty-20261106-v01/duty.mjs';import {ContinuityRouter} from './vendor/hcx-continuity-round-router-20261106-v01/router.mjs';
import {ParagraphMemory} from './vendor/hcx-round-recall-bridge-20261106-v01/vendor/paragraph/paragraph-memory.mjs';
import {RoundRecallBroker,bindRoundNative,installScopedHistoryTools} from './vendor/hcx-round-recall-bridge-20261106-v01/round-recall.mjs';
import {RollingHistoryBridge} from './vendor/hcx-round-recall-bridge-20261106-v01/vendor/rolling/rolling-bridge.mjs';
import {AssemblyShortref} from './vendor/hcx-assembly-shortref-20261106-v02/shortref.mjs';
import {syncBodyPrivateMemory,claimReferenced,acceptReferencedOpinion,verifyReferencedTicket} from './vendor/hcx-native-lifecycle-adapter-20261106-v02/memory-reference.mjs';
import {NativeLifecycleAdapter} from './vendor/hcx-native-lifecycle-adapter-20261106-v02/native-lifecycle.mjs';
export const VERSION='hcx-reference-state/v1';
const need=(v,c)=>{if(!v)throw Error(c);},copy=x=>structuredClone(x),exact=(x,keys)=>x&&typeof x==='object'&&!Array.isArray(x)&&Object.keys(x).sort().join(',')===[...keys].sort().join(',');
const id=x=>typeof x==='string'&&/^[A-Za-z0-9:_-]{1,128}$/.test(x);
export function validateRegistry(registry){
 need(exact(registry,['version','poolId','policy','members'])&&registry.version===VERSION&&id(registry.poolId),'REFERENCE_REGISTRY_SHAPE');
 need(exact(registry.policy,['epoch','digest'])&&id(registry.policy.epoch)&&/^[a-f0-9]{64}$/.test(registry.policy.digest),'REFERENCE_POLICY_REQUIRED');
 need(Array.isArray(registry.members)&&registry.members.length===10&&registry.members.every(m=>exact(m,['actorId','sessionId'])&&id(m.actorId)&&id(m.sessionId)),'TEN_REGISTERED_IDENTITIES_REQUIRED');
 need(new Set(registry.members.map(m=>m.actorId)).size===10&&new Set(registry.members.map(m=>m.sessionId)).size===10&&!registry.members.some(m=>m.actorId==='pool-controller'),'UNIQUE_REFERENCE_IDENTITIES_REQUIRED');
 return copy(registry);
}
function fileIdentity(path){const s=lstatSync(path,{bigint:true});need(s.isFile()&&!s.isSymbolicLink()&&s.nlink===1n,'REFERENCE_STORE_FILE_IDENTITY');return{device:String(s.dev),inode:String(s.ino)};}
function read(path){need(lstatSync(path).isFile()&&!lstatSync(path).isSymbolicLink(),'REFERENCE_FILE_TYPE_REQUIRED');return JSON.parse(readFileSync(path,'utf8'));}
function write(path,value,directory){const fd=openSync(path,'wx',0o600);try{writeFileSync(fd,JSON.stringify(value)+'\n');fsyncSync(fd);}finally{closeSync(fd);}const parent=openSync(directory,'r');try{fsyncSync(parent);}finally{closeSync(parent);}}
export function openReferenceState({root,registry,phase}){
 registry=validateRegistry(registry);need(['first','reopen'].includes(phase),'REFERENCE_PHASE_REQUIRED');
 need(typeof root==='string'&&realpathSync(root)===resolve(root)&&lstatSync(root).isDirectory()&&!lstatSync(root).isSymbolicLink(),'ISOLATED_REFERENCE_ROOT_REQUIRED');
 const dir=join(root,'reference-state'),registryPath=join(dir,'registry.json'),pinsPath=join(dir,'frozen-pins.json');
 const roundId='synthetic-round-1',sharedRefs=[],sharedEpoch=1,sharedPath=join(dir,'shared.sqlite'),controllerPath=join(dir,'controller.sqlite');
 const fileNames=['shared.sqlite','controller.sqlite','controller.sqlite.write-journal',...registry.members.flatMap((_,i)=>['body-'+i+'.sqlite','body-'+i+'.sqlite.write-journal','private-'+i+'.sqlite'])];
 let pins,poolBody,shared,router,wrapper,closed=false;const members=[],brokers=[],bindings=new Map();
 if(phase==='first'){need(!existsSync(dir),'NEW_REFERENCE_STATE_REQUIRED');mkdirSync(dir,{mode:0o700});write(registryPath,registry,dir);}
 else{
  need(existsSync(dir)&&lstatSync(dir).isDirectory()&&!lstatSync(dir).isSymbolicLink()&&equal(read(registryPath),registry),'EXACT_SAVED_REFERENCE_REGISTRY_REQUIRED');
  pins=read(pinsPath);need(exact(pins,['version','registryDigest','roundId','sharedEpoch','sharedSeq','privateSeqs','snapshotDigest','files'])&&pins.version===VERSION&&pins.registryDigest===hash(registry)&&pins.roundId===roundId&&pins.sharedEpoch===sharedEpoch&&Array.isArray(pins.privateSeqs)&&pins.privateSeqs.length===10&&[pins.sharedSeq,...pins.privateSeqs].every(n=>Number.isSafeInteger(n)&&n>0)&&/^[0-9a-f]{64}$/.test(pins.snapshotDigest),'EXACT_SAVED_REFERENCE_PINS_REQUIRED');
  need(exact(pins.files,fileNames),'EXACT_REFERENCE_FILE_DIRECTORY_REQUIRED');for(const name of fileNames)need(existsSync(join(dir,name))&&equal(fileIdentity(join(dir,name)),pins.files[name]),'REFERENCE_STORE_REPLACED_OR_MISSING');
 }
 const close=()=>{
  if(closed)return;closed=true;let failure;
  for(const b of [...bindings.values()])try{b.dispose();}catch(e){failure??=e;}
  for(const b of brokers)try{b.close();}catch(e){failure??=e;}
  for(const m of members){try{m.privateMemory.close();}catch(e){failure??=e;}try{m.body.close();}catch(e){failure??=e;}}
  try{shared?.close();}catch(e){failure??=e;}try{poolBody?.close();}catch(e){failure??=e;}
  if(failure)throw failure;
 };
 try{
  poolBody=new Body(controllerPath,{actorId:'pool-controller',sessionId:'controller:'+hash(registry).slice(0,24),allowance:0});
  shared=new ParagraphMemory(sharedPath);if(phase==='first'){shared.append('recall-store-scope','scope',{type:'shared',poolId:registry.poolId});shared.append('round-publication',String(sharedEpoch),{sharedEpoch,sharedRefsDigest:hash(sharedRefs)});}
  const privateSeqs=[];
  for(let i=0;i<10;i++){
   const m=registry.members[i],body=new Body(join(dir,'body-'+i+'.sqlite'),{...m,allowance:2}),privateMemory=new ParagraphMemory(join(dir,'private-'+i+'.sqlite'));
   const identity={...m,poolId:registry.poolId,policyEpoch:registry.policy.epoch,policyDigest:registry.policy.digest};members.push({...m,body,privateMemory,identity});
   if(phase==='first'){
    privateMemory.append('recall-store-scope','scope',{type:'private',...m});
    body.start('initial','Synthetic invitation for '+m.actorId+'. Read your exact original private source through the registered index, preview and original tools before the explicit final decision. No tool delivery is a decision.');
    let imported;do{imported=syncBodyPrivateMemory({body,privateMemory,budgetRows:64});}while(!imported.complete);privateSeqs.push(imported.privateSeq);
   }
  }
  const duty=new ProtectedDuty({ledger:poolBody,members:registry.members,rotationPolicy:{version:1,reviewReference:'new-synthetic-reference-state-only'}});
  router=new ContinuityRouter({ledger:poolBody,duty,members});const snapshot=phase==='first'?router.freeze({roundId,sharedEpoch,sharedRefs,topic:'Synthetic native reference integration'}):router.snapshot(roundId);
  if(phase==='first')pins={version:VERSION,registryDigest:hash(registry),roundId,sharedEpoch,sharedSeq:shared.db.prepare('SELECT MAX(seq) AS n FROM events').get().n,privateSeqs,snapshotDigest:snapshot.snapshotDigest,files:Object.fromEntries(fileNames.map(name=>[name,fileIdentity(join(dir,name))]))};
  else need(snapshot.snapshotDigest===pins.snapshotDigest&&equal(snapshot.roster,registry.members)&&equal(snapshot.sharedRefs,sharedRefs),'SAVED_SNAPSHOT_IDENTITY_CHANGED');
  for(let i=0;i<10;i++)brokers.push(new RoundRecallBroker({identity:members[i].identity,snapshot,privatePath:members[i].privateMemory.db.location(),sharedPath,privateSeq:pins.privateSeqs[i],sharedSeq:pins.sharedSeq}));
  wrapper=new AssemblyShortref({router,brokers});if(phase==='first')write(pinsPath,pins,dir);
 }catch(e){try{close();}catch{}throw e;}
 const member=index=>{need(!closed&&Number.isSafeInteger(index)&&index>=0&&index<10,'OPEN_REGISTERED_MEMBER_REQUIRED');return members[index];};
 function bindAgent({agentCtx,agent,persistenceCtx,memberIndex,config,systemMessages,onFailure,onCut}){
  const m=member(memberIndex);need(!bindings.has(memberIndex)&&agent?.ctx===agentCtx&&agent.id===m.sessionId&&agent.session?.id===m.sessionId,'EXACT_REGISTERED_AGENT_SETUP_REQUIRED');
  const path=join(dir,'native-'+memberIndex+'.sqlite');let bridge,remove;
  try{
   bridge=new RollingHistoryBridge({path,persistenceCtx,agent,identity:m.identity,pageSize:64,workEvents:2048});
   const nativeCore=bindRoundNative({bridge,broker:brokers[memberIndex],config});
   const adapter=new NativeLifecycleAdapter({body:m.body,bridge,nativeCore,identity:m.identity,systemMessages,broker:brokers[memberIndex],onFailure,onCut});
   remove=installScopedHistoryTools({agentCtx,agent,core:nativeCore});let disposed=false;
   const binding={bridge,nativeCore,adapter,dispose(){if(disposed)return;disposed=true;let failure;try{remove();}catch(e){failure=e;}try{bridge.close();}catch(e){failure??=e;}bindings.delete(memberIndex);if(failure)throw failure;}};
   bindings.set(memberIndex,binding);return binding;
  }catch(e){try{remove?.();}catch{}try{bridge?.close();}catch{}throw e;}
 }
 return{root,dir,registry:copy(registry),members,brokers,wrapper,poolBody,router,roundId,pins:copy(pins),bindAgent,close,
  claim(memberIndex){const m=member(memberIndex);return claimReferenced({body:m.body,broker:brokers[memberIndex],sharedContext:wrapper.context(m.actorId,roundId)});},
  accept(memberIndex,receipt){const m=member(memberIndex),sourceRef={actorId:m.actorId,sessionId:m.sessionId,sourceId:receipt.sourceId,ticketId:receipt.ticketId,rawDigest:receipt.rawDigest};return acceptReferencedOpinion({wrapper,body:m.body,broker:brokers[memberIndex],sourceRef});},
  verifyTicket(memberIndex,ticket){const m=member(memberIndex);return verifyReferencedTicket({body:m.body,broker:brokers[memberIndex],ticket});}
 };
}
