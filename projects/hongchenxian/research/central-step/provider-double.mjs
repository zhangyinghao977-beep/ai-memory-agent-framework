// Explicit local serializer/decoder double, NOT executed official serialize.ts.
// Independently shaped finite text/tool vocabulary; rejects unsupported content.
import assert from 'node:assert/strict';
export class DeepSeekAdapterDouble{
 constructor(deps){this.deps=deps;}
 async *stream(options){
  const messages=[];let system;
  for(const message of options.messages){
   if(message.role==='system'){system=message.content.map(x=>x.text).join('');continue;}
   let role=message.role,content;
   if(role==='tool'){role='user';content=[{type:'tool_result',tool_use_id:message.toolCallId,content:message.content,...message.isError===undefined?{}:{is_error:message.isError}}];}
   else content=message.content.map(b=>b.type==='tool-call'?{type:'tool_use',id:b.id,name:b.name,input:JSON.parse(b.arguments)}:b);
   if(messages.at(-1)?.role===role)messages.at(-1).content.push(...content);else messages.push({role,content});
  }
  const body={model:options.model,stream:true,messages,max_tokens:options.maxTokens,thinking:{type:'disabled'},system,tools:options.tools.map(t=>({name:t.name,description:t.description,input_schema:t.parameters}))};
  const headers=new Headers(this.deps.headers);headers.set('x-deepseek-harness-session-id',options.sessionId);
  const response=await this.deps.fetch('https://api.deepseek.com/anthropic/v1/messages',{method:'POST',redirect:'error',headers,body:JSON.stringify(body),signal:options.signal});
  // Synthetic test transport encodes native chunks as JSON, not provider SSE.
  for(const chunk of await response.json())yield chunk;
 }
}
export {scenarioForward,chunks} from './synthetic-scenario.mjs';
