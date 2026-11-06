// Strict subset of the SQLite public WAL file format. No SQLite calls or repairs.
// Header/frame checksum fields are always big-endian; magic controls input-word order.
import {createHash} from 'node:crypto';
const fail=code=>{throw Object.assign(new Error(code),{code});};
const check=(ok,code)=>{if(!ok)fail(code);};
function checksum(bytes,order,state=[0,0]){check(bytes.length%8===0,'WAL_FORMAT_UNSUPPORTED');let [a,b]=state;for(let i=0;i<bytes.length;i+=8){const x=order==='little'?bytes.readUInt32LE(i):bytes.readUInt32BE(i),y=order==='little'?bytes.readUInt32LE(i+4):bytes.readUInt32BE(i+4);a=(a+x+b)>>>0;b=(b+y+a)>>>0;}return[a,b];}
export function validateWal(db,wal){
 check(Buffer.isBuffer(db)&&Buffer.isBuffer(wal),'WAL_FORMAT_UNSUPPORTED');check(db.length>=100&&db.subarray(0,16).equals(Buffer.from('SQLite format 3\0')),'SQLITE_HEADER_INVALID');
 const dbPage=db.readUInt16BE(16)===1?65536:db.readUInt16BE(16);check(dbPage>=512&&dbPage<=65536&&(dbPage&(dbPage-1))===0&&db.length%dbPage===0,'SQLITE_HEADER_INVALID');
 check(wal.length>=32,'WAL_TRUNCATED');const magic=wal.readUInt32BE(0);check(magic===0x377f0682||magic===0x377f0683,'WAL_HEADER_INVALID');check(wal.readUInt32BE(4)===3007000,'WAL_FORMAT_UNSUPPORTED');const pageSize=wal.readUInt32BE(8);check(pageSize===dbPage,'WAL_HEADER_INVALID');const order=(magic&1)?'big':'little';let state=checksum(wal.subarray(0,24),order);check(state[0]===wal.readUInt32BE(24)&&state[1]===wal.readUInt32BE(28),'WAL_CHECKSUM_INVALID');
 const frameBytes=24+pageSize;check((wal.length-32)%frameBytes===0,'WAL_TRUNCATED');const frames=(wal.length-32)/frameBytes;check(frames>0,'WAL_NO_COMMITTED_FRAMES');const salt=wal.subarray(16,24);let commits=0,lastCommitPages=0;
 for(let i=0;i<frames;i++){const offset=32+i*frameBytes,head=wal.subarray(offset,offset+24),page=wal.subarray(offset+24,offset+frameBytes),pageNumber=head.readUInt32BE(0),commitPages=head.readUInt32BE(4);check(pageNumber>0&&pageNumber<=Math.floor(128*1024*1024/pageSize),'WAL_FRAME_INVALID');check(commitPages<=Math.floor(128*1024*1024/pageSize),'WAL_FRAME_INVALID');check(head.subarray(8,16).equals(salt),'WAL_SALT_INVALID');state=checksum(head.subarray(0,8),order,state);state=checksum(page,order,state);check(state[0]===head.readUInt32BE(16)&&state[1]===head.readUInt32BE(20),'WAL_CHECKSUM_INVALID');if(commitPages){commits++;lastCommitPages=commitPages;}if(i===frames-1)check(commitPages>0,'WAL_UNCOMMITTED_TAIL');}
 check(commits>0,'WAL_NO_COMMITTED_FRAMES');return Object.freeze({formatVersion:3007000,pageSize,checksumInputOrder:order,frames,commits,lastCommitPages,completeCommittedBoundary:true,validatedWalSha256:createHash('sha256').update(wal).digest('hex')});
}

// Verify checkpointed pages against the validated WAL overlay, not only SQLite's return code.
export function verifyDerivedPages(originalDb,wal,workingDb,validation){
 check(workingDb.length===validation.lastCommitPages*validation.pageSize,'WORKING_PAGE_MISMATCH');const pages=new Map();for(let offset=32;offset<wal.length;offset+=24+validation.pageSize)pages.set(wal.readUInt32BE(offset),wal.subarray(offset+24,offset+24+validation.pageSize));
 for(let n=1;n<=validation.lastCommitPages;n++){let expected=pages.get(n)??originalDb.subarray((n-1)*validation.pageSize,n*validation.pageSize),actual=workingDb.subarray((n-1)*validation.pageSize,n*validation.pageSize);check(expected.length===validation.pageSize,'WORKING_PAGE_MISMATCH');if(n===1){expected=Buffer.from(expected);actual=Buffer.from(actual);for(const [start,end]of [[18,20],[24,28],[92,100]]){expected.fill(0,start,end);actual.fill(0,start,end);}}check(expected.equals(actual),'WORKING_PAGE_MISMATCH');}return true;
}
