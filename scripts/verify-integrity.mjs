import {readFileSync,readdirSync,lstatSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,relative,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const files=[];
function walk(dir){for(const name of readdirSync(dir).sort()){
 if(name==='.git')continue;
 const path=resolve(dir,name),stat=lstatSync(path);
 if(stat.isSymbolicLink())throw Error('SYMLINK_FORBIDDEN');
 if(stat.isDirectory())walk(path);else if(stat.isFile())files.push(relative(root,path).split(sep).join('/'));else throw Error('NONREGULAR_FILE_FORBIDDEN');
}}
walk(root);
const lines=readFileSync(resolve(root,'SHA256SUMS'),'utf8').trim().split('\n');
const expected=new Set();
for(const line of lines){
 const match=/^([a-f0-9]{64})  (.+)$/.exec(line);if(!match)throw Error('INVALID_MANIFEST');
 const [,hash,path]=match;
 if(path==='SHA256SUMS'||path.startsWith('/')||path.split('/').some(x=>x==='..'||x==='.'||!x)||expected.has(path))throw Error('INVALID_MANIFEST_PATH');
 expected.add(path);
 if(createHash('sha256').update(readFileSync(resolve(root,path))).digest('hex')!==hash)throw Error('HASH_MISMATCH: '+path);
}
if(JSON.stringify([...expected].sort())!==JSON.stringify(files.filter(x=>x!=='SHA256SUMS').sort()))throw Error('EXACT_FILE_SET_MISMATCH');
console.log(JSON.stringify({status:'passed',verifiedContentFiles:expected.size,totalFiles:files.length,symlinks:0}));
