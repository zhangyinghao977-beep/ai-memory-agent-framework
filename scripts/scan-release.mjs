// Heuristic candidate-only scan. Reports location/category, never matching values.
import {readFileSync,readdirSync,lstatSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,relative,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url)),findings=[],files=[];
const report=(path,line,category)=>findings.push({path,line,category});
function walk(dir){for(const name of readdirSync(dir).sort()){
 if(name==='.git')continue;
 const path=resolve(dir,name),rel=relative(root,path).split(sep).join('/'),stat=lstatSync(path);
 if(stat.isSymbolicLink()){report(rel,0,'symlink');continue;}
 if(stat.isDirectory()){if(['node_modules','.aws','.codex','downloads'].includes(name))report(rel,0,'excluded-directory');else walk(path);}
 else if(stat.isFile())files.push(rel);else report(rel,0,'nonregular-file');
}}
walk(root);
const rules=[
 ['private-key',/-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----/g],
 ['provider-token',/\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}|AKIA[A-Z0-9]{16})\b/g],
 ['jwt-shaped-value',/\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/g],
 ['credential-in-url',/https?:\/\/[^\s\/@]+:[^\s\/@]+@/g],
 ['email-address',/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g],
 ['private-host-path',/\/(?:workspace|home|Users|opt|var\/lib)\/[A-Za-z0-9_./-]+/g],
 ['windows-private-path',/[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/][^\s\])]+/g],
 ['private-message-id',/\bSentinel_[a-f0-9]{16,}\b/g],
 ['private-library-id',/\blibfile_[a-f0-9]{16,}\b/g],
 ['cloud-instance-id',/\b(?:lhins|ins)-[a-z0-9]{6,}\b/g],
 ['ipv4-address',/\b(?:\d{1,3}\.){3}\d{1,3}\b/g],
 ['credential-assignment',/(?:api[_-]?key|client[_-]?secret|password|access[_-]?token|refresh[_-]?token)\s*['"]?\s*[:=]\s*['"]([^'"\n]{8,})['"]/gi]
];
const reviewedSynthetic=new Set(['synthetic-not-a-credential','synthetic-key','synthetic-token']);
// Exact hashes of two visibly synthetic fixture literals, reviewed without outputting values.
const reviewedHeaderLiteralHashes=new Set(["df061c081ec116af5d7249255d49f10da158e5f80f81a3d41f406a0f31fb20b8", "4ad25a3e8b9834c12320fa1b89819a59dd5f4650b9a3408a62a00e07db259d95"]);
for(const path of files){
 if(/(?:^|\/)\.env(?:\.|$)|\.(?:pem|key|p12|pfx|sqlite|sqlite3|db|log|tar|gz|zip|b64)$|(?:-wal|-shm)$/.test(path))report(path,0,'excluded-file-type');
 const bytes=readFileSync(resolve(root,path));if(bytes.includes(0)){report(path,0,'binary-content');continue;}
 const text=bytes.toString('utf8');
 for(const [category,pattern] of rules){pattern.lastIndex=0;for(const match of text.matchAll(pattern)){
  if(category==='credential-assignment'&&reviewedSynthetic.has(match[1])&&path.endsWith('.test.mjs'))continue;
  if(category==='credential-assignment'&&path==='projects/hongchenxian/research/central-step/protected-wire.test.mjs'&&reviewedHeaderLiteralHashes.has(createHash('sha256').update(match[1]).digest('hex')))continue;
  report(path,text.slice(0,match.index).split('\n').length,category);
 }}
 if(path.endsWith('.mjs'))for(const match of text.matchAll(/(?:from\s+|import\()\s*['"]([^'"]+)['"]/g)){
  const spec=match[1];if(spec.startsWith('node:'))continue;
  if(!spec.startsWith('.')){report(path,text.slice(0,match.index).split('\n').length,'non-builtin-package-import');continue;}
  const target=resolve(root,path,'..',spec);if(!target.startsWith(resolve(root)+sep)){report(path,0,'escaping-import');continue;}
  try{if(!lstatSync(target).isFile())report(path,0,'nonfile-import');}catch{report(path,0,'missing-import');}
 }
}
const result={status:findings.length?'review-required':'passed',scannedFiles:files.length,findings,limits:'Heuristic candidate-only review; does not prove absence of all secrets or rights issues.'};
console.log(JSON.stringify(result,null,2));if(findings.length)process.exitCode=1;
