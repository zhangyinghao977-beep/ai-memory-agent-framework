import {DatabaseSync} from 'node:sqlite';
import {createHash,randomUUID} from 'node:crypto';
import {resolve,dirname,basename,join} from 'node:path';
import {realpathSync,existsSync,lstatSync,openSync,closeSync,writeFileSync,readFileSync,fsyncSync} from 'node:fs';
import {Memory} from './memory.mjs';
import {parsePoolChoice} from './pool-choice.mjs';
export const hash=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
export class ValidationError extends Error {}
export const check=(ok,message)=>{if(!ok)throw new ValidationError(message);};
const clone=x=>JSON.parse(JSON.stringify(x));

// Append-only lifecycle controller. The separate SQLite owner connection holds a
// lifetime exclusive transaction; OS teardown releases it after process death.
export class Body {
 constructor(path,{actorId,sessionId,allowance}) {
  check(typeof actorId==='string'&&actorId&&typeof sessionId==='string'&&sessionId,'identity required');
  check(Number.isSafeInteger(allowance)&&allowance>=0,'explicit request allowance');
  const abs=resolve(path);const wasExisting=existsSync(abs);check(!wasExisting||!lstatSync(abs).isSymbolicLink(),'DB symlink unsupported');
  this.path=join(realpathSync(dirname(abs)),basename(abs));
  this.intentPath=this.path+'.write-journal';
  // Reject known migrations before opening a writable database or owner file.
  check(!existsSync(this.path+'.write-intent'),'legacy write-intent requires explicit reviewed migration');
  check(!wasExisting||existsSync(this.intentPath),'existing database without journal requires explicit reviewed migration');
  check(wasExisting||!existsSync(this.intentPath),'journal without database requires explicit reviewed recovery');
  const lock=this.path+'.owner.sqlite';check(!existsSync(lock)||!lstatSync(lock).isSymbolicLink(),'owner symlink unsupported');
  try{
   this.owner=new DatabaseSync(lock);this.owner.exec('PRAGMA busy_timeout=0; BEGIN EXCLUSIVE;');
   this.writePaused=false;this.lastIntentId=null;
   if(wasExisting){
    check(!lstatSync(this.intentPath).isSymbolicLink(),'write journal symlink unsupported');
    const raw=readFileSync(this.intentPath,'utf8');check(raw.length>0&&raw.endsWith('\n'),'incomplete write intent journal requires explicit reviewed recovery');
    const inspection=new DatabaseSync(this.path,{readOnly:true});
    try{
     const outcomes=inspection.prepare('SELECT id,outcome FROM body_tx_outcomes').all();const byID=new Map(outcomes.map(row=>[row.id,row.outcome]));const seen=new Set();
     for(const line of raw.slice(0,-1).split('\n')){
      const intent=JSON.parse(line);check(Object.keys(intent).sort().join(',')==='id,previous'&&typeof intent.id==='string'&&/^[0-9a-f-]{36}$/.test(intent.id)&&intent.previous===this.lastIntentId&&!seen.has(intent.id),'write journal chain mismatch');
      check(['committed','aborted'].includes(byID.get(intent.id)),'uncommitted write intent in journal requires explicit reviewed recovery');seen.add(intent.id);this.lastIntentId=intent.id;
     }
     check(seen.size===outcomes.length,'journal/outcome coverage mismatch requires explicit reviewed recovery');
     const configRow=inspection.prepare("SELECT data FROM events WHERE id='body:config:body'").get();
     check(configRow&&hash(JSON.parse(configRow.data))===hash({actorId,sessionId,allowance}),'body configuration mismatch; explicit migration required');
     check(inspection.prepare("SELECT COUNT(*) AS n FROM events WHERE kind='body-resource-pause'").get().n===0,'persisted resource pause requires explicit reviewed recovery');
    }finally{inspection.close();}
   }
   this.memory=new Memory(this.path);
   this.memory.db.exec("CREATE TABLE IF NOT EXISTS body_tx_outcomes(id TEXT PRIMARY KEY, outcome TEXT NOT NULL CHECK(outcome IN ('committed','aborted')))");
   this.tx(()=>this.put('config','body',{actorId,sessionId,allowance}));
   Object.assign(this,{actorId,sessionId});
  }catch(e){this.memory?.close();this.owner?.close();throw e;}
 }
 close(){this.memory.close();this.owner.close();}
 appendIntent(id){
  const fd=openSync(this.intentPath,'a',0o600);try{writeFileSync(fd,JSON.stringify({id,previous:this.lastIntentId})+'\n');fsyncSync(fd);}finally{closeSync(fd);}
  const dirfd=openSync(dirname(this.intentPath),'r');try{fsyncSync(dirfd);}finally{closeSync(dirfd);}
  this.lastIntentId=id;
 }
 holdWriteFailure(intentDurable){
  this.writePaused=true;this.pauseBarrierDurable=false;
  if(intentDurable){try{this.appendIntent(randomUUID());this.pauseBarrierDurable=true;}catch{}}
 }
 tx(fn){
  check(!this.writePaused,'STORAGE_RESOURCE_HELD');const id=randomUUID();let intentDurable=false;
  try{
   // Append-only: no unlink or directory fsync after COMMIT. A durable intent
   // is resolved only by a committed/aborted outcome in the database.
   this.appendIntent(id);intentDurable=true;
   this.memory.db.exec('BEGIN IMMEDIATE');const result=fn();
   this.memory.db.prepare("INSERT INTO body_tx_outcomes(id,outcome) VALUES(?,'committed')").run(id);
   this.memory.db.exec('COMMIT');return result;
  }catch(e){
   let rollbackSafe=true;try{if(this.memory.db.isTransaction)this.memory.db.exec('ROLLBACK');}catch{rollbackSafe=false;}
   const semantic=e instanceof ValidationError;
   if(!semantic||!intentDurable||!rollbackSafe){
    // A committed result may coexist with an operational failure. Retain a
    // separate unresolved barrier; no same-DB diagnostic or automatic release.
    this.holdWriteFailure(intentDurable);
   }
   else{
    // A semantic validation rejection has no committed business effects. Record
    // only its aborted bookkeeping outcome; failure to do so holds reopening.
    try{this.memory.db.prepare("INSERT OR IGNORE INTO body_tx_outcomes(id,outcome) VALUES(?,'aborted')").run(id);}catch(bookkeepingError){this.holdWriteFailure(intentDurable);throw bookkeepingError;}
   }
   throw e;
  }
 }
 pauseResources(reason){check(['SCAN_WORK_BUDGET','SQLITE_RESOURCE_OR_IO_FAILURE'].includes(reason),'fixed resource reason');this.tx(()=>this.put('resource-pause','resource',{reason}));this.writePaused=true;}
 put(kind,id,data){return this.memory.append('body-'+kind,id,data,`body:${kind}:${id}`);}
 one(kind,id){return this.memory.one('body-'+kind,id)?.data??null;}
 rows(kind){return this.memory.events('body-'+kind);}
 state(){return this.rows('state').at(-1)?.data??{mode:'new',source:null,wakeAt:null};}
 stateTo(id,data){this.put('state',id,data);}
 memories(){return this.memory.events('paragraph').map(r=>({id:r.subject,text:r.data.text}));}
 start(id,text){
  check(typeof text==='string'&&text.trim(),'initial text required');
  this.tx(()=>{
   if(this.one('source',id)){check(this.one('source',id).text===text,'initial conflict');return;}
   check(this.state().mode==='new','already started');
   this.put('source',id,{kind:'initial',text});this._ready(id);
  });
 }
 _ready(source){
  check(this.memory.db.isTransaction,'lifecycle transaction required');
  const event=this.one('source',source),s=this.state();
  check(event&&((event.kind==='initial'&&s.mode==='new')||
   (event.kind==='completed'&&event.choice.action==='continue'&&s.mode==='awake')||
   (event.kind==='wake'&&s.mode==='sleeping'&&event.sleepSource===s.source)),'source/state cannot enqueue');
  this.put('ready',source,{source});this.stateTo('ready:'+source,{mode:'awake',source,wakeAt:null});
 }
 claim(sharedContext){return this.tx(()=>{
  const s=this.state();if(s.mode!=='awake')return null;
  const ready=this.rows('ready').find(r=>!this.one('claim',r.subject));if(!ready)return null;
  const config=this.one('config','body'),grants=this.rows('grant').reduce((n,r)=>n+r.data.extra,0);
  if(this.rows('claim').length>=config.allowance+grants){this.stateTo('held:'+ready.subject,{mode:'resource-held',source:ready.subject,wakeAt:null});return null;}
  const source=ready.subject,id='dispatch:'+source;
  const payload={id,actorId:this.actorId,sessionId:this.sessionId,source,sourceEvent:this.one('source',source),memories:this.memories()};
  if(sharedContext!==undefined)payload.sharedContext=clone(sharedContext);
  if(payload.sourceEvent.kind==='wake')payload.causalParent=this.one('source',payload.sourceEvent.sleepSource);
  this.put('claim',source,payload);return clone(payload);
 });}
 bind(ticket,binding){this.tx(()=>{const c=this.one('claim',ticket.source);check(c&&hash(c)===hash(ticket),'exact claim');this.put('binding',ticket.id,binding);});}
 binding(ticketId){return this.one('binding',ticketId);}
 acknowledge(ticketId){this.tx(()=>{check(this.binding(ticketId),'binding required');this.put('ack',ticketId,{queued:true});});}
 diagnostic(ticketId){this.tx(()=>this.put('diagnostic',ticketId,{code:'TRANSPORT_OUTCOME_RECONCILE_REQUIRED'}));}
 reserveStream(sessionId){return this.tx(()=>{
  check(sessionId===this.sessionId,'stream wrong session');
  const pending=this.rows('binding').filter(r=>!this.one('processed',r.subject));check(pending.length===1,'exactly one bound pending ticket');
  const b=pending[0];check(!this.one('stream',b.subject),'duplicate/unadmitted stream');
  check(this.state().mode==='awake','stream while not awake');this.put('stream',b.subject,{sessionId});return clone(b.data);
 });}
 accept(ticketId,sourceId,raw,provenance){
  const choice=parsePoolChoice(raw);
  this.tx(()=>{
   const data={kind:'completed',ticketId,raw,choice,provenance};
   if(this.one('source',sourceId)){check(hash(this.one('source',sourceId))===hash(data),'source conflict');return;}
   check(this.binding(ticketId)&&this.one('ack',ticketId),'acknowledged ticket required');
   check(!this.one('processed',ticketId)&&this.state().mode==='awake','processed or nonawake ticket');
   this.put('source',sourceId,data);this.memory.paragraph(choice.thought,{id:'thought:'+sourceId});
   this.put('processed',ticketId,{sourceId});
   if(choice.action==='continue')this._ready(sourceId);
   else this.stateTo(sourceId,{mode:choice.action==='sleep'?'sleeping':'stopped',source:sourceId,wakeAt:choice.wake_at});
  });
 }
 wake(now,source){check(typeof now==='number'&&Number.isFinite(now),'finite now');return this.tx(()=>{
  const s=this.state();if(s.mode!=='sleeping'||source!==s.source||now<s.wakeAt)return false;
  const id='wake:'+source;this.put('source',id,{kind:'wake',sleepSource:source,deadline:s.wakeAt});this._ready(id);return true;
 });}
 grant(id,extra){check(Number.isSafeInteger(extra)&&extra>0,'positive allowance');this.tx(()=>{
  this.put('grant',id,{extra});const s=this.state();if(s.mode==='resource-held')this.stateTo('grant:'+id,{...s,mode:'awake'});
 });}
 snapshot(){return{state:this.state(),memories:this.memories(),claims:this.rows('claim').length,processed:this.rows('processed').length,
  unresolved:this.rows('claim').filter(r=>!this.one('processed',r.data.id)).map(r=>r.data)};}
}
