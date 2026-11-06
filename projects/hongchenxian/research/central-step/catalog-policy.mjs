// Local fail-closed candidate policy, informed by floating public master source.
// This does not import official modules, implement the full upstream schema,
// attest installed rc.5 metadata, or authorize model/provider execution.
export const PREPARATION_LOCK=true;
export const INSTALLED_METADATA_VERIFIED=false;
const need=(v,c)=>{if(!v)throw Error(c);};
function dataObject(value,allowed){
 need(value!==null&&typeof value==='object'&&!Array.isArray(value)&&[Object.prototype,null].includes(Object.getPrototypeOf(value)),'METADATA_OBJECT_REQUIRED');
 const properties=Object.getOwnPropertyDescriptors(value);need(Reflect.ownKeys(properties).every(k=>typeof k==='string'&&(!allowed||allowed.includes(k))&&'value' in properties[k]),'METADATA_FIELDS_REQUIRED');
 return value;
}
function dataArray(value,max){
 need(Array.isArray(value)&&value.length>0&&value.length<=max,'CATALOG_ARRAY_REQUIRED');
 const descriptors=Object.getOwnPropertyDescriptors(value);
 need(Reflect.ownKeys(descriptors).every(k=>typeof k==='string'&&'value' in descriptors[k]&&(k==='length'||/^(0|[1-9][0-9]*)$/.test(k)&&Number(k)<value.length)),'CATALOG_ARRAY_FIELDS_INVALID');
 need(Object.keys(descriptors).length===value.length+1,'CATALOG_ARRAY_SPARSE');
}
const positive=v=>Number.isSafeInteger(v)&&v>0;
const identifier=v=>typeof v==='string'&&v.trim()===v&&v.length>0&&Buffer.byteLength(v)<=128;
const fields=['id','name','description','contextWindow','maxTokens','inputModalities','imagePixelBudget','imageMaxBytes','systemPromptUpdate','toolUpdate'];
export function validateCatalog(models){
 dataArray(models,64);const seen=new Set();
 for(const entry of models){
  dataObject(entry,fields);need(Object.hasOwn(entry,'id')&&identifier(entry.id),'CATALOG_ID_REQUIRED');need(!seen.has(entry.id),'DUPLICATE_CATALOG_ID');seen.add(entry.id);
  for(const k of ['name','description'])if(entry[k]!==undefined)need(typeof entry[k]==='string','CATALOG_LABEL_INVALID');
  for(const k of ['contextWindow','maxTokens','imageMaxBytes'])if(entry[k]!==undefined)need(positive(entry[k]),'CATALOG_LIMIT_INVALID');
  if(entry.imagePixelBudget!==undefined)need(entry.imagePixelBudget==='low'||positive(entry.imagePixelBudget),'CATALOG_IMAGE_BUDGET_INVALID');
  if(entry.inputModalities!==undefined){dataArray(entry.inputModalities,2);need(Array.isArray(entry.inputModalities)&&entry.inputModalities.length>0&&entry.inputModalities.every(x=>x==='text'||x==='image')&&new Set(entry.inputModalities).size===entry.inputModalities.length,'CATALOG_MODALITIES_INVALID');}
  if(entry.systemPromptUpdate!==undefined)need(entry.systemPromptUpdate==='in-history','CATALOG_SYSTEM_CAPABILITY_INVALID');
  if(entry.toolUpdate!==undefined)need(['addition-only','in-history'].includes(entry.toolUpdate),'CATALOG_TOOL_CAPABILITY_INVALID');
 }
 return true;
}
export function validateDeclaredOptions(options){
 const required=['baseURL','models','thinking','reasoningEffort','maxTokens','streamIdleTimeoutMs','retryPolicy'];dataObject(options,required);need(required.every(k=>Object.hasOwn(options,k)),'DECLARED_FIELDS_REQUIRED');
 need(options.baseURL==='https://api.deepseek.com/anthropic','PINNED_ENDPOINT_REQUIRED');
 validateCatalog(options.models);need(options.models.length===1&&options.models[0].id==='deepseek-flash','PINNED_CATALOG_REQUIRED');
 const entry=options.models[0];need(Object.keys(entry).sort().join(',')==='id,inputModalities,maxTokens'&&entry.maxTokens===512&&JSON.stringify(entry.inputModalities)==='["text"]','PINNED_TEXT_MODEL_REQUIRED');
 need(options.thinking==='disabled'&&options.reasoningEffort==='off'&&options.maxTokens===512&&options.streamIdleTimeoutMs===15000,'PINNED_GENERATION_POLICY_REQUIRED');
 dataObject(options.retryPolicy,['mode','maxRetries']);need(Object.hasOwn(options.retryPolicy,'mode')&&Object.hasOwn(options.retryPolicy,'maxRetries'),'RETRY_FIELDS_REQUIRED');need(options.retryPolicy.mode==='normal'&&options.retryPolicy.maxRetries===0,'NO_RETRY_REQUIRED');
 return true;
}
export function validateResolvedCatalog(connection,requestedId='deepseek-flash'){
 // This checks relevant resolved metadata, NOT every connection field.
 dataObject(connection);need(['models','maxTokens','defaultContextWindow','defaults'].every(k=>Object.hasOwn(connection,k)),'CONNECTION_FIELDS_REQUIRED');validateCatalog(connection.models);need(identifier(requestedId),'REQUESTED_ID_REQUIRED');
 const matches=connection.models.filter(entry=>entry.id===requestedId);need(matches.length===1,'REQUESTED_MODEL_NOT_DECLARED');
 need(positive(connection.maxTokens)&&positive(connection.defaultContextWindow),'CONNECTION_LIMIT_INVALID');
 dataObject(connection.defaults,['thinking','reasoningEffort']);need(Object.hasOwn(connection.defaults,'thinking')&&Object.hasOwn(connection.defaults,'reasoningEffort'),'DEFAULT_FIELDS_REQUIRED');need(connection.defaults.thinking==='disabled'&&connection.defaults.reasoningEffort==='off','RESOLVED_REASONING_POLICY_REQUIRED');
 const entry=matches[0],maxTokens=entry.maxTokens??connection.maxTokens,contextWindow=entry.contextWindow??connection.defaultContextWindow;
 need(requestedId==='deepseek-flash'&&maxTokens===512,'RESOLVED_OUTPUT_POLICY_REQUIRED');
 need(JSON.stringify(entry.inputModalities??['text'])==='["text"]'&&entry.systemPromptUpdate===undefined&&entry.toolUpdate===undefined&&entry.imagePixelBudget===undefined&&entry.imageMaxBytes===undefined,'UNSUPPORTED_RESOLVED_CAPABILITY');
 // An immutable observation; never changes caller arrays or treats readonly as
 // a runtime provenance/security guarantee. Missing IDs do not use fallback.
 return Object.freeze({id:entry.id,name:entry.name??entry.id,inputModalities:Object.freeze(['text']),contextWindow,defaultMaxTokens:maxTokens,reasoningEffort:'off',installedMetadataVerified:INSTALLED_METADATA_VERIFIED});
}
export function validateSdkExports(exports){
 need(exports!==null&&(typeof exports==='object'||typeof exports==='function'),'PUBLIC_EXPORT_OBJECT_REQUIRED');
 for(const name of ['DeepSeekAdapter','resolveAdapterOptions']){const descriptor=Object.getOwnPropertyDescriptor(exports,name);need(descriptor&&'value' in descriptor&&typeof descriptor.value==='function','PUBLIC_EXPORT_REQUIRED');}
 return Object.freeze({requiredExportsPresent:true,installedMetadataVerified:INSTALLED_METADATA_VERIFIED});
}
