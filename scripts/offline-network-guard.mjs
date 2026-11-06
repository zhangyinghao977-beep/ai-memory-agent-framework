// Test-only fail-closed protection against accidental real network use.
// This is not a security sandbox for hostile code.
import {syncBuiltinESMExports} from 'node:module';
import net from 'node:net';
import tls from 'node:tls';
import http from 'node:http';
import https from 'node:https';
import http2 from 'node:http2';
import dgram from 'node:dgram';
import dns from 'node:dns';
import dnsPromises from 'node:dns/promises';
const blocked=()=>{throw Error('OFFLINE_PREVIEW_NETWORK_FORBIDDEN');};
Object.defineProperty(globalThis,'fetch',{value:async()=>blocked(),writable:false,configurable:false});
for(const [object,names] of [
 [net,['connect','createConnection']], [net.Socket.prototype,['connect']],
 [tls,['connect']], [http,['request','get']], [https,['request','get']],
 [http2,['connect']], [dgram,['createSocket']],
 [dns,['lookup','lookupService','resolve','resolve4','resolve6','resolveAny','resolveCaa','resolveCname','resolveMx','resolveNaptr','resolveNs','resolvePtr','resolveSoa','resolveSrv','resolveTxt','reverse']],
 [dnsPromises,['lookup','lookupService','resolve','resolve4','resolve6','resolveAny','resolveCaa','resolveCname','resolveMx','resolveNaptr','resolveNs','resolvePtr','resolveSoa','resolveSrv','resolveTxt','reverse']]
])for(const name of names)if(typeof object[name]==='function')object[name]=blocked;
syncBuiltinESMExports();
