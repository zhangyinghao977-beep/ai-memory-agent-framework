// Finite deterministic synthetic responses, no model inference or network.
import assert from 'node:assert/strict';
export function chunks(action){const block=action.name?{type:'tool-call',id:action.id,name:action.name,arguments:JSON.stringify(action.args)}:{type:'text',text:action.text};return[{type:'block-start',index:0,blockType:block.type},{type:'block-end',index:0,block},{type:'usage',usage:{inputTokens:10,outputTokens:10,totalTokens:20}},{type:'finish',reason:{kind:action.name?'tool-calls':'stop'}}];}
export function scenarioForward(){let calls=0;return{get calls(){return calls;},async forward(url,init,{target}){
 const payload=JSON.parse(init.body),input=payload.messages.flatMap(m=>m.content).find(b=>b.type==='text'&&b.text.includes('hcx-body-input'));assert.ok(input);const ticket=JSON.parse(input.text);
 const results=payload.messages.flatMap(m=>m.content).filter(b=>b.type==='tool_result');let action;
 const parse=r=>{const text=r.content.filter(x=>x.type==='text').map(x=>x.text).join('');return JSON.parse(text).result;};
 if(results.length===0)action={name:'hcx_memory_lookup',args:ticket.sourceRef.lookup};
 else if(results.length===1)action={name:'hcx_memory_preview',args:{hitHandle:parse(results[0]).hits[0].hitHandle}};
 else if(results.length===2)action={name:'hcx_memory_read_original',args:{readHandle:parse(results[1]).readHandle,relevance:'Read exact private source.',pageChars:64000}};
 else{assert.equal(results.length,3);action={text:JSON.stringify({action:'stop',thought:'Synthetic private thought.',reason:'Synthetic source read complete.',wake_at:null,meeting:{kind:'contribute',text:JSON.stringify({kind:'position',...ticket.sharedContext.assemblyRef,position:'oppose',text:'Synthetic opinion',reason:null}),refs:[],epoch:null},read_ids:[]})};}
 calls++;return new Response(JSON.stringify(chunks({...action,id:target.ticketId+':'+results.length})),{status:200});
 }};}
export function scenarioSSEForward(){const source=scenarioForward();return async(...args)=>{const response=await source.forward(...args),native=await response.json(),block=native.find(c=>c.type==='block-end').block,isTool=block.type==='tool-call';const events=[
 {type:'message_start',message:{id:'synthetic-'+source.calls,type:'message',role:'assistant',model:'deepseek-flash',content:[],usage:{input_tokens:10,output_tokens:0}}},
 {type:'content_block_start',index:0,content_block:isTool?{type:'tool_use',id:block.id,name:block.name,input:{}}:{type:'text',text:''}},
 {type:'content_block_delta',index:0,delta:isTool?{type:'input_json_delta',partial_json:block.arguments}:{type:'text_delta',text:block.text}},
 {type:'content_block_stop',index:0},{type:'message_delta',delta:{stop_reason:isTool?'tool_use':'end_turn',stop_sequence:null},usage:{output_tokens:10}},{type:'message_stop'}];return new Response(events.map(e=>'event: '+e.type+'\ndata: '+JSON.stringify(e)+'\n\n').join(''),{status:200,headers:{'content-type':'text/event-stream'}});};}
