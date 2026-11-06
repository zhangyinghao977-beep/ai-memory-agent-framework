// Explicit local double of the inspected public lifecycle and source shape.
// This never imports the official runtime, calls apply, or contacts a provider.
import assert from 'node:assert/strict';
import { AsyncLocalStorage } from 'node:async_hooks';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';


const copy = value => structuredClone(value);
const schema = ({ name, description, parameters }) => copy({ name, description, parameters });
const messageOf = event => event.type === 'user/message' ? event.data : event.data.message;

export function fakeRuntime({ modelConfig:CONFIG, faults = {}, states = new Map(), pageSize = 7, generationBaseline = { replaceGeneration: 0, contentGeneration: 0 } } = {}) {
  const hooks = [], handles = [], maintenanceContext = new AsyncLocalStorage();
  const stats = { reads: [], flushes: 0, opens: 0, closes: 0, bodies: 0, streams: 0, followups: 0,
    scopedServiceReads: 0, disposeCalls: 0, maintenanceStarted: 0, maintenanceFinished: 0,
    maintenanceRejected: 0, whenIdleInMaintenance: 0, probes: [], lifecycle: [] };
  let provider, probed = false, startupProbed = false;
  const ctx = {
    on(type, callback) {
      assert.equal(type, 'llm/stream'); hooks.push(callback);
      return () => { const index = hooks.indexOf(callback); if (index >= 0) hooks.splice(index, 1); };
    },
    systemPrompt: {},
    llm: { registerAdapter(names, adapter) {
      assert.deepEqual(names, [CONFIG.provider]); provider = adapter;
      return () => { provider = undefined; };
    } },
    tools: { schemas(agent) { return agent ? [...agent.defs.values()].map(schema) : []; } },
    sessions: { async flush(session) {
      assert.equal(this, ctx.sessions); assert.equal(states.get(session.id), session.state);
      session.state.durable = copy(session.state.events); stats.flushes++; return true;
    } },
    sessionPersistence: {
      async stat(id) { assert.equal(this, ctx.sessionPersistence); assert.ok(states.has(id)); return { header: copy(states.get(id).header) }; },
      async open(id, mode) {
        assert.equal(this, ctx.sessionPersistence); assert.equal(mode, 'read'); assert.ok(states.has(id));
        stats.opens++; let closed = false;
        return {
          async read(after, count) {
            assert.equal(closed, false); assert.ok(Number.isSafeInteger(after) && after >= 0);
            const events = copy(states.get(id).durable.slice(after, after + Math.min(count, pageSize)));
            stats.reads.push({ id, after, count, returned: events.length });
            if (faults.afterRead) await faults.afterRead({ id, after, count, events, state: states.get(id), handles });
            return { events };
          },
          async close() { assert.equal(closed, false); closed = true; stats.closes++; }
        };
      }
    }
  };

  async function* dispatch(options) {
    assert.ok(provider, 'registered explicit adapter required');
    let next = () => provider.stream(options);
    for (const hook of [...hooks].reverse()) { const inner = next; next = () => hook(options, inner); }
    yield* next();
  }
  ctx.llm.stream=dispatch;
  async function swallowedProbe(name, options, direct = false) {
    try { for await (const ignored of direct ? provider.stream(options) : dispatch(options)) void ignored;
      stats.probes.push({ name, rejected: false });
    } catch (error) { stats.probes.push({ name, rejected: true, code: error.message }); }
  }

  function make(id, setup, resume, agentOptions) {
    assert.deepEqual(agentOptions, CONFIG);
    const state = resume ? states.get(id) : { events: [], durable: [], header: { id, formatVersion: 'explicit-local-double' }, generationBaseline: copy(generationBaseline) };
    assert.ok(state, 'resume requires the same persisted source');
    if (resume) state.events = copy(state.durable);
    else { assert.equal(states.has(id), false); states.set(id, state); }
    const surface = { nodes: [], ...copy(state.generationBaseline) }, inbox = [];
    if (faults.surface) faults.surface(surface, state);
    const foldSurface = event => {
      if (event.surfaceOp === 'append') surface.nodes.push(event.seq);
      else if (event.surfaceOp) {
        assert.equal(event.surfaceOp.op, 'replace');
        const start = surface.nodes.indexOf(event.surfaceOp.startSeq), end = surface.nodes.indexOf(event.surfaceOp.endSeq);
        assert.ok(start >= 1 && end >= start); assert.deepEqual(event.sourceEventSeqs, surface.nodes.slice(start, end + 1));
        surface.nodes.splice(start, end - start + 1, event.seq); surface.replaceGeneration++; surface.contentGeneration++;
      }
      if (event.type === 'agent/inbox/spliced' && event.data.target === 'next-turn') {
        inbox.splice(event.data.start, event.data.removedCount ?? 0, ...copy(event.data.inserted));
      }
    };
    for (const event of state.events) foldSurface(event);
    const session = { id, state, surface, get seq() { return state.events.length; },
      deriveMessages() { throw Error('FULL_HISTORY_DERIVE_FORBIDDEN_IN_DRIVER_DOUBLE'); },
      append(type, data, intent = {}) {
        // Saved Session.append1517–1534 builds metadata in this order,
        // independently from the caller's SurfaceIntent object key order.
        const metadata={...(intent.sourceEventSeqs===undefined?{}:{sourceEventSeqs:copy(intent.sourceEventSeqs)}),...(intent.surfaceOp===undefined?{}:{surfaceOp:copy(intent.surfaceOp)})};
        let event = { type, seq: state.events.length, time: state.events.length, data: copy(data), ...metadata };
        // Explicit fault boundary, never an official module. Tests may model
        // persistence field order or a tampered replacement without changing inputs.
        if (faults.materializeEvent) event=faults.materializeEvent(event);
        foldSurface(event); state.events.push(event); return event;
      }
    };
    // Saved Session constructor1428 admits a clean lifecycle marker on restore.
    if(resume&&state.events.at(-1)?.type!=='session/end-seed')session.append('session/end-seed',{});
    const defs = new Map(), listeners = [];
    let requestHeaderLogged=false, requestSurfaceGeneration=surface.contentGeneration;
    let section, phase = 'idle', disposed = false, wakeRequested = false, maintenance, maintenanceController, turnJob, turnError, turnController, disposeJob;
    const agentCtx = {
      get sessions() { stats.scopedServiceReads++; throw Error('SCOPED_PERSISTENCE_MUST_NOT_BE_USED'); },
      get sessionPersistence() { stats.scopedServiceReads++; throw Error('SCOPED_PERSISTENCE_MUST_NOT_BE_USED'); },
      tools: { register(def) {
        assert.equal(defs.has(def.name), false); defs.set(def.name, def); return () => defs.delete(def.name);
      } },
      on(type, callback) {
        assert.equal(type, 'tools/result'); listeners.push(callback);
        return () => { const index = listeners.indexOf(callback); if (index >= 0) listeners.splice(index, 1); };
      },
      systemPrompt: { section(value) {
        assert.equal(value.complete, true); assert.equal(value.interpolate, false); section = value;
        return () => { section = undefined; };
      } }
    };
    const currentMessages = () => surface.nodes.map(seq => copy(messageOf(state.events[seq])));
    const splice = (inserted, removedCount = 0) => session.append('agent/inbox/spliced', {
      target: 'next-turn', start: inserted.length ? inbox.length : 0, removedCount, inserted
    });
    const agent = { id, session, ctx: agentCtx, defs,
      get phase() { return phase; }, get status() { return phase === 'running' ? 'running' : 'idle'; },
      get disposed() { return disposed; },
      followup(message) {
        assert.equal(disposed, false); stats.followups++; splice([message]); wakeRequested = true;
        stats.lifecycle.push({ kind: 'followup', id, phase, seq: session.seq });
        // The immediate source mutation is real; maintenance only latches wake.
        if (phase === 'idle') launchTurn();
      },
      async whenIdle() {
        if (maintenanceContext.getStore() === agent) {
          stats.whenIdleInMaintenance++; throw Error('WHEN_IDLE_WITHIN_OWN_MAINTENANCE_FORBIDDEN');
        }
        while (maintenance || turnJob) await (maintenance ?? turnJob);
        if (turnError) { const error = turnError; turnError = undefined; throw error; }
      },
      runMaintenance(job) {
        // Gate is acquired synchronously, before the callback's first microtask.
        if (disposed || phase !== 'idle') { stats.maintenanceRejected++; return Promise.reject(Error('MAINTENANCE_EXCLUSIVE_ADMISSION_REQUIRED')); }
        phase = 'maintenance'; stats.maintenanceStarted++; maintenanceController = new AbortController();
        const signal = maintenanceController.signal;
        maintenance = Promise.resolve().then(() => maintenanceContext.run(agent, () => job(signal))).finally(() => {
          maintenance = undefined; maintenanceController = undefined; phase = 'idle'; stats.maintenanceFinished++;
          if (!disposed && wakeRequested && inbox.length) launchTurn();
        });
        return maintenance;
      },
      cancel(reason, options) {
        assert.equal(reason.kind, 'user'); assert.equal(options.keepInbox, true);
        maintenanceController?.abort(reason); turnController?.abort(reason);
      }
    };
    async function runTurn() {
      turnController = new AbortController();
      const turn = 1 + state.events.reduce((max, event) => event.type === 'turn/start' ? Math.max(max, event.data.turn) : max, 0);
      const input = copy(inbox[0]);
      session.append('turn/start', { turn }); splice([], 1);
      for (let step = 1; step <= 8; step++) {
        session.append('step/start', { turn, step });
        if (step === 1) {
          if (!surface.nodes.length) {
            assert.ok(section, 'scoped system section required');
            session.append('system/message', { turn, step, message: { id: 'system:' + id, role: 'system', source: { kind: 'system-prompt' }, content: [{ type: 'text', text: section.text }] } }, { surfaceOp: 'append' });
          }
          session.append('user/message', input, { surfaceOp: 'append' });
        }
        // Match saved public buildRequest: header on first built request (not
        // attachment), new series after content changes, context only on change.
        const previousHeader=state.events.findLast(e=>e.type==='request/header');
        const startsSeries=requestSurfaceGeneration!==surface.contentGeneration;
        if (!requestHeaderLogged) {
          session.append('request/header',{header:{config:copy(CONFIG),tools:ctx.tools.schemas(agent)},reason:previousHeader?'resume':'initial',...(startsSeries?{startsSeries:true}:{})});
          requestHeaderLogged=true;
        } else if (startsSeries) session.append('request/header',{header:{config:copy(CONFIG),tools:ctx.tools.schemas(agent)},reason:'series'});
        requestSurfaceGeneration=surface.contentGeneration;
        const context={provider:CONFIG.provider,model:CONFIG.model,contextWindow:32768,systemPromptUpdate:'in-history'};
        if (JSON.stringify(state.events.findLast(e=>e.type==='request/context')?.data)!==JSON.stringify(context)) session.append('request/context',context);
        const options = { ...CONFIG, sessionId: id, tools: ctx.tools.schemas(agent), messages: currentMessages(), signal: turnController.signal };
        if (faults.admissionAttempt && !probed) {
          probed = true;
          const changes = { foreignSession: { sessionId: id + ':foreign' }, provider: { provider: 'foreign-provider' }, model: { model: 'foreign-model' },
            maxTokens: { maxTokens: 999 }, reasoningEffort: { reasoningEffort: 'high' }, tools: { tools: [] } };
          assert.ok(changes[faults.admissionAttempt]);
          await swallowedProbe(faults.admissionAttempt, { ...options, ...changes[faults.admissionAttempt] }, faults.directAttempt);
        }
        const chunks = [];
        try{for await (const chunk of dispatch(options)) chunks.push(chunk);}
        catch(error){
          // Saved public agent-loop source: failed stream commits an attempt,
          // then step/end and an error turn/end. Empty stream is an explicit
          // double, not a claim about installed stream-record byte encoding.
          session.append('assistant/attempt',{turn,step,stream:[]});
          session.append('step/end',{turn,step});
          session.append('turn/end',{turn,reason:{kind:'error',error:{code:'UNKNOWN',message:'EXPLICIT_DOUBLE_STREAM_FAILURE'}}});
          throw error;
        }
        stats.streams++;
        const content = chunks.filter(chunk => chunk.type === 'block-end').map(chunk => chunk.block);
        assert.equal(content.length, 1); assert.equal(chunks.at(-1).type, 'finish');
        session.append('assistant/message', { turn, step, message: { id: `assistant:${id}:${turn}:${step}`, role: 'assistant', source: { kind: 'model', provider: CONFIG.provider, model: CONFIG.model }, content } }, { surfaceOp: 'append' });
        const block = content[0];
        if (block.type !== 'tool-call') {
          session.append('step/end', { turn, step }); session.append('turn/end', { turn, reason: { kind: 'completed' } }); return;
        }
        const call = session.append('tool/call', { turn, step, callId: block.id, name: block.name, arguments: block.arguments });
        const args = JSON.parse(block.arguments), exec = { agent, name: block.name, callId: block.id, rootCallId: block.id, arguments: args, signal: turnController.signal };
        const def = defs.get(block.name); assert.ok(def, 'only exact scoped native tool may execute'); stats.bodies++;
        const value = await def.execute(args, exec);
        const final = { isError: false, value, content: def.output.render(args, value), meta: def.output.presentationMeta(args, value) };
        for (const listener of listeners) listener(exec, final);
        session.append('tool/result', { turn, step, message: { id: 'result:' + block.id, role: 'tool', source: { kind: 'tool', callId: block.id }, toolCallId: block.id, isError: false, content: final.content }, meta: final.meta }, { surfaceOp: 'append', sourceEventSeqs: [call.seq] });
        session.append('step/end', { turn, step });
      }
      throw Error('EXPLICIT_DOUBLE_STEP_BUDGET');
    }
    function launchTurn() {
      assert.equal(phase, 'idle'); assert.ok(inbox.length); phase = 'running'; wakeRequested = false;
      turnJob = Promise.resolve().then(runTurn).catch(error => { turnError = error; }).finally(() => {
        phase = 'idle'; turnController = undefined; turnJob = undefined;
        if (!disposed && wakeRequested && inbox.length && !turnError) launchTurn();
      });
    }
    const handle = { agent, dispose() {
      if (disposeJob) return disposeJob;
      stats.disposeCalls++; disposed = true;
      maintenanceController?.abort({ kind: 'disposed' }); turnController?.abort({ kind: 'disposed' });
      disposeJob = (async () => {
        if (faults.cleanupAttempt) await swallowedProbe('cleanup', { ...CONFIG, sessionId: id }, true);
        // The callback returns before disposal settles; never await disposal from
        // inside that callback. This is the ownership edge probeMaintenance tests.
        await Promise.allSettled([maintenance, turnJob].filter(Boolean));
        stats.lifecycle.push({ kind: 'disposed', id, phase });
      })();
      return disposeJob;
    } };
    if (setup && faults.wrongAgentId) agent.id += ':wrong';
    if (setup && faults.wrongAgentCtx) agent.ctx = {};
    const prepared = setup?.(agentCtx, agent); prepared?.commit();
    handles.push(handle); return handle;
  }
  ctx.agents = {
    async create({ sessionId, agentOptions, setup }) {
      const handle = make(sessionId, setup, false, agentOptions);
      if (faults.startupAttempt && !startupProbed) { startupProbed = true; await swallowedProbe('startup', { ...CONFIG, sessionId }, faults.directAttempt); }
      return handle;
    },
    async resume({ resumeSessionId, agentOptions, setup }) { return make(resumeSessionId, setup, true, agentOptions); }
  };
  const sdk = { provenance: 'explicit-local-double', LlmAdapter: class {},
    createUserMessage({ content, source }) { return { id: `user:${source.sessionId}:${source.ticketId}`, role: 'user', content: copy(content), source: copy(source) }; }
  };
  return { ctx, sdk, states, stats, handles, dispatch,
    source(id) { return states.get(id); }, target(id) { return handles.findLast(handle => handle.agent.id === id); } };
}
