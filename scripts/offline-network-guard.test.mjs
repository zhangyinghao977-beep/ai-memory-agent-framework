import test from 'node:test';
import assert from 'node:assert/strict';
import {connect,createConnection,Socket} from 'node:net';
import {request as httpRequest,get as httpGet} from 'node:http';
import {request as httpsRequest} from 'node:https';
import {connect as tlsConnect} from 'node:tls';
import {connect as http2Connect} from 'node:http2';
import {createSocket} from 'node:dgram';
import {lookup} from 'node:dns';
import {lookup as promiseLookup} from 'node:dns/promises';
test('preview guard rejects global fetch before a network request',async()=>{
 await assert.rejects(fetch('https://example.invalid/'),/OFFLINE_PREVIEW_NETWORK_FORBIDDEN/);
 assert.equal(Object.getOwnPropertyDescriptor(globalThis,'fetch').writable,false);
});
test('preview guard rejects common builtin socket, HTTP, TLS and DNS entry points',()=>{
 for(const fn of [()=>connect(),()=>createConnection(),()=>new Socket().connect(),()=>httpRequest(),()=>httpGet(),()=>httpsRequest(),()=>tlsConnect(),()=>http2Connect(),()=>createSocket(),()=>lookup(),()=>promiseLookup()])assert.throws(fn,/OFFLINE_PREVIEW_NETWORK_FORBIDDEN/);
});
