// No tools, model-authored actor fields, or implicit lifecycle actions.
export function validatePoolChoice(c) {
 const fail=m=>{throw new Error('pool choice: '+m);};
 const exact=(o,keys)=>o&&typeof o==='object'&&!Array.isArray(o)&&Object.keys(o).sort().join(',')===keys.sort().join(',');
 if(!exact(c,['action','thought','reason','wake_at','meeting','read_ids']))fail('strict envelope');
 if(!['continue','sleep','stop'].includes(c.action))fail('action');
 if(!['thought','reason'].every(k=>typeof c[k]==='string'&&c[k].trim()))fail('thought/reason');
 if(c.action==='sleep'?!(typeof c.wake_at==='number'&&Number.isFinite(c.wake_at)&&c.wake_at>=0):c.wake_at!==null)fail('wake deadline');
 const ids=a=>Array.isArray(a)&&a.every(x=>typeof x==='string'&&x.trim())&&new Set(a).size===a.length;
 if(!ids(c.read_ids))fail('read_ids');
 const m=c.meeting;
 if(!exact(m,['kind','text','refs','epoch'])||!['none','contribute','decline','minutes'].includes(m.kind)||typeof m.text!=='string'||!ids(m.refs))fail('meeting');
 if(m.kind==='minutes'?!(Number.isSafeInteger(m.epoch)&&m.epoch>0):m.epoch!==null)fail('meeting epoch');
 if(m.kind==='none'&&(m.text!==''||m.refs.length))fail('none must be empty');
 if(m.kind==='decline'&&m.refs.length)fail('decline refs must be empty');
 if(['contribute','minutes'].includes(m.kind)&&!m.text.trim())fail('meeting text');
 return c;
}
export const parsePoolChoice=raw=>validatePoolChoice(JSON.parse(raw));
