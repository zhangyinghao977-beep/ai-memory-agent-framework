import { createHash } from 'node:crypto';

// Local-only adapter. The injected bridge owns durability, incremental source
// ingestion, bounded projection queries and archive paging. This module never
// opens a session, invokes a model, reconstructs a full prefix or derives a
// session surface. Its source checks are lineage checks, not authentication.
export const VERSION = 'hcx-rolling-history-native/v1';
export const digest = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const copy = value => JSON.parse(JSON.stringify(value));
const need = (ok, code) => { if (!ok) throw Error(code); };
const scopeKeys = ['actorId', 'sessionId', 'policyEpoch', 'policyDigest'];
const str = { type: 'string', description: 'Nonempty string; enforced by the read body.' };
const positive = { type: 'integer', description: 'Positive safe integer; enforced by the read body.' };
// Intentionally identical to sealed a03 ARCHIVE_SCHEMAS. No legacy paragraph
// tools are registered here; expectedSchemas explicitly describes composition.
export const ARCHIVE_SCHEMAS = [
  { name: 'hcx_history_index', description: 'Read handles for exact whole original source messages, without source bodies.', parameters: { type: 'object', additionalProperties: false, required: ['indexId'], properties: { indexId: str, pageSize: positive, cursor: str } } },
  { name: 'hcx_history_preview', description: 'Check a mechanical source excerpt for a whole-message index hit. Not an authored summary.', parameters: { type: 'object', additionalProperties: false, required: ['hitHandle'], properties: { hitHandle: str, pageChars: positive, cursor: str } } },
  { name: 'hcx_history_original', description: 'Read paginated exact original source event JSON after its index preview, retaining the whole message.', parameters: { type: 'object', additionalProperties: false, required: ['readHandle', 'relevance'], properties: { readHandle: str, relevance: str, pageChars: positive, cursor: str } } },
];
export const NATIVE_OUTPUT = { type: 'object', additionalProperties: false, required: ['version', 'actorId', 'sessionId', 'policyEpoch', 'dispatchId', 'callId', 'toolName', 'sourceBinding', 'result', 'resultDigest'], properties: {
  version: str, actorId: str, sessionId: str, policyEpoch: str, dispatchId: str, callId: str, toolName: str, sourceBinding: { type: 'object' }, result: { type: 'object' }, resultDigest: str,
} };
export const render = value => [{ type: 'text', text: JSON.stringify(value) }];
export const meta = value => ({ version: VERSION, actorId: value.actorId, sessionId: value.sessionId, policyEpoch: value.policyEpoch, dispatchId: value.dispatchId, callId: value.callId, resultDigest: value.resultDigest });
export const schemaDigest = schemas => digest([...schemas].sort((a, b) => a.name.localeCompare(b.name)));
export function validate(name, input) {
  const schema = ARCHIVE_SCHEMAS.find(s => s.name === name)?.parameters;
  need(schema, 'UNREGISTERED_HISTORY_TOOL');
  need(input && typeof input === 'object' && !Array.isArray(input) && Object.keys(input).every(k => Object.hasOwn(schema.properties, k)), 'INVALID_HISTORY_TOOL_ARGUMENTS');
  for (const key of schema.required) need(Object.hasOwn(input, key), 'MISSING_HISTORY_TOOL_ARGUMENT');
  for (const [key, value] of Object.entries(input)) need(schema.properties[key].type === 'string' ? typeof value === 'string' && value.trim() : Number.isSafeInteger(value) && value > 0, 'INVALID_HISTORY_TOOL_ARGUMENT');
  return copy(input);
}
const targetOf = input => input.indexId ?? input.hitHandle ?? input.readHandle;
const cursorBinding = input => Object.fromEntries(Object.entries(input).filter(([key]) => key !== 'cursor').sort(([a], [b]) => a.localeCompare(b)));
const rowData = row => row?.data ?? row;

export class RollingHistoryNativeAdapter {
  constructor({ bridge, expectedSchemas, config, onCut = () => {}, maxResultBytes = 32768, extension = null }) {
    need(bridge && ['sync', 'assertOwner', 'healthy', 'hold', 'event', 'findEvents', 'checkpoint', 'currentMessages', 'visibleIndexIds', 'readIndex', 'preview', 'readOriginal', 'put', 'one', 'pending', 'pendingSourceRequests', 'reissuePage'].every(key => typeof bridge[key] === 'function'), 'ROLLING_BRIDGE_CONTRACT_REQUIRED');
    need(Array.isArray(expectedSchemas) && new Set(expectedSchemas.map(s => s.name)).size === expectedSchemas.length, 'EXPLICIT_EXPECTED_SCHEMAS_REQUIRED');
    for (const schema of ARCHIVE_SCHEMAS) need(digest(expectedSchemas.find(s => s.name === schema.name)) === digest(schema), 'HISTORY_SCHEMA_COMPOSITION_MISMATCH');
    need(config && typeof config.provider === 'string' && config.provider && typeof config.model === 'string' && config.model && Number.isSafeInteger(config.maxTokens) && config.maxTokens > 0 && typeof config.reasoningEffort === 'string', 'EXPLICIT_NATIVE_CONFIG_REQUIRED');
    need(Number.isSafeInteger(maxResultBytes) && maxResultBytes > 0, 'NATIVE_RESULT_BUDGET_REQUIRED');
    this.bridge = bridge; this.agent = bridge.agent; this.identity = Object.freeze(copy(bridge.identity));
    for (const key of scopeKeys) need(typeof this.identity[key] === 'string' && this.identity[key], 'NATIVE_IDENTITY_REQUIRED');
    this.expectedSchemas = copy(expectedSchemas); this.config = Object.freeze(copy(config));
    this.extension=extension; this.reissuing=new Set();
    this.onCut = onCut; this.maxResultBytes = maxResultBytes; this.reconciled = false; this.latched = null;
    bridge.assertOwner(this.agent);
  }
  healthy() {
    need(!this.latched, 'NATIVE_BINDING_HELD'); this.bridge.healthy(); this.bridge.assertOwner(this.agent);
    for (const key of scopeKeys) need(this.bridge.identity[key] === this.identity[key], 'NATIVE_SCOPE_CHANGED');
  }
  hold(error) {
    const code = typeof error === 'string' ? error : String(error?.message ?? 'NATIVE_OPERATION_FAILED');
    this.latched = code; this.reconciled = false;
    // bridge.hold must persist the latch before throwing. Never recover by
    // silently swapping to another ledger, session or source reader.
    return this.bridge.hold(code);
  }
  guarded(error) { if (error?.syntheticCrash === true) throw error; return this.hold(error); }
  assertCheckpoint(checkpoint) {
    const now = this.bridge.checkpoint();
    need(checkpoint && checkpoint.headerDigest === now.headerDigest && Number.isSafeInteger(checkpoint.boundary) && checkpoint.boundary <= now.boundary, 'NATIVE_SOURCE_CHECKPOINT_MISMATCH');
  }
  async reserve(dispatchId, message) {
    try {
      this.healthy(); need(typeof dispatchId === 'string' && dispatchId, 'DISPATCH_ID_REQUIRED');
      await this.reconcile(); need(!this.bridge.one('native-dispatch', dispatchId), 'CONSUMED_DISPATCH_NO_BLIND_REPLAY');
      need(message?.role === 'user' && message.source?.kind === 'hcx-index-native-abi' && message.source.ticketId === dispatchId, 'HOST_MESSAGE_BINDING_REQUIRED');
      for (const key of scopeKeys) need(message.source[key] === this.identity[key], 'HOST_MESSAGE_POLICY_MISMATCH');
      this.extension?.assertDispatch(dispatchId,message);
      const binding = { ...this.identity, dispatchId, message: copy(message), checkpoint: this.bridge.checkpoint() };
      this.bridge.put('native-dispatch', dispatchId, binding); return copy(binding);
    } catch (error) { return this.guarded(error); }
  }
  assertUnboundRequests(activeCallId) {
    // Dedicated bridge projection anti-joins native-call by callId. It excludes
    // source requests outside a host-reserved dispatch; no full source walk.
    for (const row of this.bridge.pendingSourceRequests()) {
      const request = rowData(row), callId = request.callId;
      const requestName = request.name ?? this.bridge.event(request.assistantSeq).data.message.content.find(b => b.type === 'tool-call' && b.id === callId)?.name;
      if (!ARCHIVE_SCHEMAS.some(schema => schema.name === requestName)) continue;
      need(!request.closed, 'UNBOUND_SOURCE_REQUEST_NO_REPLAY');
      const calls = this.bridge.findEvents({ type: 'tool/call', callId });
      const results = this.bridge.findEvents({ type: 'tool/result', callId });
      const endings = [...this.bridge.findEvents({ type: 'turn/end', turn: request.turn, after: request.assistantSeq }),
        ...this.bridge.findEvents({ type: 'step/end', turn: request.turn, after: request.assistantSeq }).filter(e => e.data.step === request.step)];
      need(callId === activeCallId && calls.length === 1 && results.length === 0 && endings.length === 0, 'UNBOUND_SOURCE_REQUEST_NO_REPLAY');
    }
  }
  bindExecution(name, input, exec) {
    this.bridge.assertOwner(exec.agent);
    need(exec.agent === this.agent && exec.name === name && typeof exec.callId === 'string' && exec.callId, 'EXACT_NATIVE_EXECUTION_REQUIRED');
    need(exec.parent === undefined && (exec.rootCallId === undefined || exec.rootCallId === exec.callId), 'NESTED_EXECUTION_NOT_ALLOWED');
    need(digest(input) === digest(exec.arguments), 'EXEC_INPUT_DIFFERS_FROM_ARGUMENTS');
    const calls = this.bridge.findEvents({ type: 'tool/call', callId: exec.callId });
    need(calls.length === 1, 'EXACT_ONE_SOURCE_TOOL_CALL_REQUIRED'); const sourceCall = calls[0];
    need(sourceCall.data.name === name && typeof sourceCall.data.arguments === 'string', 'SOURCE_TOOL_NAME_OR_ARGUMENTS_MISMATCH');
    let args; try { args = JSON.parse(sourceCall.data.arguments); } catch { throw Error('SOURCE_ARGUMENT_JSON_INVALID'); }
    need(digest(args) === digest(exec.arguments), 'EXEC_ARGUMENTS_DIFFER_FROM_SOURCE');
    const assistants = this.bridge.findEvents({ type: 'assistant/message', callId: exec.callId }).filter(e => e.seq < sourceCall.seq && e.data.turn === sourceCall.data.turn && e.data.step === sourceCall.data.step);
    need(assistants.length === 1, 'EXACT_SOURCE_ASSISTANT_CALL_REQUIRED'); const assistant = assistants[0], message = assistant.data.message;
    need(assistant.surfaceOp === 'append' && assistant.data.interrupted !== true && message?.role === 'assistant' && message.source?.kind === 'model' && message.source.provider === this.config.provider && message.source.model === this.config.model, 'SOURCE_ASSISTANT_PROVENANCE_MISMATCH');
    need(message.content.length === 1 && message.content[0].type === 'tool-call' && message.content[0].id === exec.callId && message.content[0].name === name && message.content[0].arguments === sourceCall.data.arguments, 'SOURCE_ASSISTANT_TOOL_BLOCK_MISMATCH');
    const starts = this.bridge.findEvents({ type: 'turn/start', turn: sourceCall.data.turn, before: assistant.seq });
    need(starts.length === 1, 'EXACT_SOURCE_TURN_START_REQUIRED');
    const users = this.bridge.findEvents({ type: 'user/message', after: starts[0].seq, before: assistant.seq });
    need(users.length === 1, 'EXACT_HOST_INPUT_PER_TURN_REQUIRED');
    const binding = this.bridge.one('native-dispatch', users[0].data.source?.ticketId);
    need(binding && digest(users[0].data) === digest(binding.message), 'SOURCE_HOST_DISPATCH_BINDING_MISMATCH');
    for (const key of scopeKeys) need(binding[key] === this.identity[key], 'SOURCE_DISPATCH_POLICY_MISMATCH');
    this.assertCheckpoint(binding.checkpoint); this.extension?.assertDispatch(binding.dispatchId,binding.message);
    const header = this.bridge.findEvents({ type: 'request/header', before: assistant.seq, latest: true }).at(-1);
    need(header && schemaDigest(header.data.header.tools ?? []) === schemaDigest(this.expectedSchemas), 'SOURCE_REQUEST_TOOL_SCHEMA_MISMATCH');
    return { ...this.identity, dispatchId: binding.dispatchId, callId: exec.callId, name, arguments: copy(args), argumentsDigest: digest(args), turn: sourceCall.data.turn, step: sourceCall.data.step,
      assistantSeq: assistant.seq, assistantDigest: digest(assistant), toolCallSeq: sourceCall.seq, toolCallDigest: digest(sourceCall), checkpoint: this.bridge.checkpoint() };
  }
  assertObserved(callId) {
    const observation = this.bridge.one('native-observed', callId), call = this.bridge.one('native-call', callId);
    need(observation && call && !observation.isError, 'SOURCE_OBSERVED_SUCCESS_REQUIRED');
    this.assertCheckpoint(observation.checkpoint);
    need(digest(this.bridge.event(call.assistantSeq)) === call.assistantDigest && digest(this.bridge.event(call.toolCallSeq)) === call.toolCallDigest && digest(this.bridge.event(observation.eventSeq)) === observation.eventDigest, 'SOURCE_OBSERVED_ANCHOR_CHANGED');
    const body = this.bridge.one('native-body', callId), final = this.bridge.one('native-final', callId);
    need(body?.status === 'succeeded' && digest(body.value) === body.valueDigest && final?.isError === false && digest(final.content) === digest(render(body.value)) && digest(final.meta ?? null) === digest(meta(body.value)), 'OBSERVED_BODY_FINAL_MISMATCH');
    const checked = this.verifyResult(call, final);
    need(checked.eventSeq === observation.eventSeq && checked.eventDigest === observation.eventDigest, 'SOURCE_OBSERVED_PROOF_CHANGED');
    return observation;
  }
  requireCapability(kind, token, name, target, input) {
    const cap = this.bridge.one('native-capability', kind + ':' + token);
    need(cap && cap.kind === kind && cap.token === token && (!name || cap.name === name) && (!target || cap.target === target), 'HANDLE_NOT_IN_SOURCE_OBSERVED_RESULT');
    if (kind === 'cursor') need(digest(cap.inputBinding) === digest(cursorBinding(input)), 'CURSOR_INPUT_BINDING_MISMATCH');
    try {
      this.assertObserved(cap.callId);
      const body = this.bridge.one('native-body', cap.callId);
      const call=this.bridge.one('native-call',cap.callId);
      if(this.extension?.owns(call.name)) {
        need(!this.reissuing.has(call.callId),'CAPABILITY_REISSUE_CYCLE_HELD');this.reissuing.add(call.callId);
        try { this.validateDelivery(call.name,call.arguments);const page=this.extension.read(call.name,call.arguments);need(digest(page)===digest(body.value.result),'ROUND_READ_REISSUE_CHANGED'); }
        finally {this.reissuing.delete(call.callId);}
      } else this.bridge.reissuePage(copy(body.value.result));
    } catch (error) { return this.guarded(error); }
    return cap;
  }
  validateDelivery(name, input) {
    this.healthy();
    if(this.extension?.owns(name)) {for(const [key,kind] of [['hitHandle','hit'],['indexHandle','index'],['readHandle','read']])if(input[key])this.requireCapability(kind,input[key]);}
    if (name === 'hcx_history_index' && !this.bridge.visibleIndexIds().includes(input.indexId)) this.requireCapability('index', input.indexId);
    if (name === 'hcx_history_preview') this.requireCapability('hit', input.hitHandle);
    if (name === 'hcx_history_original') this.requireCapability('read', input.readHandle);
    if (input.cursor) this.requireCapability('cursor', input.cursor, name, targetOf(input), input);
  }
  async execute(name, input, exec) {
    let call;
    try {
      this.healthy(); need(this.reconciled, 'SOURCE_RECONCILIATION_REQUIRED');
      need(exec?.signal && !exec.signal.aborted, 'TOOL_CANCELLED_BEFORE_SOURCE_READ');
      this.bridge.assertOwner(exec.agent); need(exec.agent === this.agent, 'EXACT_AGENT_REQUIRED');
      need(!this.bridge.one('native-call', exec.callId), 'CONSUMED_NATIVE_CALL_NO_BLIND_REPLAY');
      await this.reconcile(exec.callId);
      this.onCut('before-call-binding', this.bridge.checkpoint());
      call = this.bindExecution(name, input, exec);
      this.bridge.put('native-call', exec.callId, call); this.onCut('after-call-binding', call.checkpoint);
    } catch (error) { return this.guarded(error); }
    let outcome;
    try {
      const args = this.extension?.owns(name) ? this.extension.validate(name,input) : validate(name, input); this.validateDelivery(name, args); need(!exec.signal.aborted, 'TOOL_CANCELLED_BEFORE_READ');
      const result = this.extension?.owns(name) ? this.extension.read(name,args) : name === 'hcx_history_index' ? this.bridge.readIndex(args) : name === 'hcx_history_preview' ? this.bridge.preview(args) : this.bridge.readOriginal(args);
      need(result && typeof result === 'object' && !Array.isArray(result) && typeof result.then !== 'function', 'SYNCHRONOUS_HISTORY_RESULT_REQUIRED');
      need(!exec.signal.aborted, 'TOOL_CANCELLED_AFTER_READ');
      const value = { version: VERSION, actorId: this.identity.actorId, sessionId: this.identity.sessionId, policyEpoch: this.identity.policyEpoch, dispatchId: call.dispatchId, callId: call.callId, toolName: name,
        sourceBinding: { assistantSeq: call.assistantSeq, assistantDigest: call.assistantDigest, toolCallSeq: call.toolCallSeq, toolCallDigest: call.toolCallDigest, checkpoint: call.checkpoint }, result: copy(result), resultDigest: digest(result) };
      need(Buffer.byteLength(JSON.stringify(value)) <= this.maxResultBytes, 'NATIVE_RESULT_RESOURCE_HELD');
      outcome = { status: 'succeeded', value, valueDigest: digest(value) };
    } catch (error) {
      if (error?.syntheticCrash === true) throw error;
      outcome = { status: 'failed', code: /RESOURCE|BUDGET|HELD|database|disk/i.test(String(error.message)) ? 'READ_RESOURCE_HELD' : /CANCELLED/.test(String(error.message)) ? 'READ_CANCELLED' : 'READ_REJECTED', diagnostic: String(error.message) };
    }
    try { this.bridge.put('native-body', exec.callId, outcome); this.onCut('after-body-outcome', call.checkpoint); } catch (error) { return this.guarded(error); }
    if (outcome.status === 'failed') {
      if (outcome.code !== 'READ_REJECTED') return this.hold(outcome.code);
      throw Error('HCX_NATIVE_READ_REJECTED');
    }
    return copy(outcome.value);
  }
  observeFinal(exec, result) {
    try {
      this.healthy(); this.bridge.assertOwner(exec.agent); need(exec.agent === this.agent, 'EXACT_AGENT_REQUIRED');
      const call = this.bridge.one('native-call', exec.callId), body = this.bridge.one('native-body', exec.callId);
      need(call && call.name === exec.name && body, 'NATIVE_FINAL_WITHOUT_BOUND_BODY');
      need(typeof result?.isError === 'boolean' && Array.isArray(result.content), 'NATIVE_FINAL_SHAPE');
      need(!result.concludesTurn && !(result.additionalContexts?.length), 'NATIVE_READ_TOOL_SIDE_EFFECT');
      if (!result.isError) need(body.status === 'succeeded' && digest(result.value) === body.valueDigest && digest(result.content) === digest(render(body.value)) && digest(result.meta ?? null) === digest(meta(body.value)), 'NATIVE_FINAL_CHANGED_SUCCESS');
      else need(result.value === undefined && typeof result.error?.message === 'string', 'NATIVE_FAILURE_MUST_NOT_BE_SUCCESS');
      const final = { isError: result.isError, content: copy(result.content), ...(result.meta === undefined ? {} : { meta: copy(result.meta) }), ...(result.error === undefined ? {} : { error: copy(result.error) }) };
      this.bridge.put('native-final', exec.callId, final); this.onCut('after-native-final', call.checkpoint);
    } catch (error) { return this.guarded(error); }
  }
  verifyResult(call, final) {
    this.assertCheckpoint(call.checkpoint);
    need(digest(this.bridge.event(call.assistantSeq)) === call.assistantDigest && digest(this.bridge.event(call.toolCallSeq)) === call.toolCallDigest, 'SOURCE_CALL_ANCHOR_CHANGED');
    const results = this.bridge.findEvents({ type: 'tool/result', callId: call.callId });
    need(results.length === 1, 'EXACT_ONE_SOURCE_TOOL_RESULT_REQUIRED'); const event = results[0], m = event.data.message;
    need(event.seq > call.toolCallSeq && event.surfaceOp === 'append' && event.data.turn === call.turn && event.data.step === call.step && m?.role === 'tool' && m.source?.kind === 'tool' && m.source.callId === call.callId && m.toolCallId === call.callId && typeof m.id === 'string' && m.id, 'SOURCE_RESULT_LINEAGE_MISMATCH');
    need(Array.isArray(event.sourceEventSeqs) && digest(event.sourceEventSeqs) === digest([call.toolCallSeq]), 'SOURCE_RESULT_CALL_SEQ_LINK_MISMATCH');
    need(m.isError === final.isError && digest(m.content) === digest(final.content) && digest(event.data.meta ?? null) === digest(final.meta ?? null) && digest(event.data.error ?? null) === digest(final.error?.info ?? null), 'SOURCE_RESULT_DIFFERS_FROM_NATIVE_FINAL');
    return { ...this.identity, callId: call.callId, dispatchId: call.dispatchId, isError: m.isError, eventSeq: event.seq, eventDigest: digest(event), checkpoint: this.bridge.checkpoint(), replayAllowed: false, sourceApiLineageChecked: true, cryptographicAuthentication: false };
  }
  publish(call, result) {
    const grant = (kind, token, name, target) => {
      need(typeof token === 'string' && token, 'INVALID_ISSUED_HISTORY_CAPABILITY');
      const id = kind + ':' + token;
      const existing = this.bridge.one('native-capability', id);
      if (existing) { need(existing.kind === kind && existing.token === token && (!name || existing.name === name) && (!target || existing.target === target) && (kind !== 'cursor' || digest(existing.inputBinding) === digest(cursorBinding(call.arguments))), 'HISTORY_CAPABILITY_COLLISION'); this.assertObserved(existing.callId); return; }
      this.bridge.put('native-capability', id, { kind, token, callId: call.callId, ...(name ? { name } : {}), ...(target ? { target } : {}), ...(kind === 'cursor' ? { inputBinding: cursorBinding(call.arguments) } : {}) });
    };
    if(this.extension?.owns(call.name)) {
      for(const hit of result.hits??[])if(hit.hitHandle)grant('hit',hit.hitHandle);
      for(const ref of result.refs??[])if(ref.handle)grant(ref.kind==='index'?'index':'hit',ref.handle);
      if(result.previewHandle)grant('index',result.previewHandle);if(result.readHandle)grant('read',result.readHandle);
    }
    if (call.name === 'hcx_history_index') {
      for (const item of [...(result.hits ?? []), ...(result.entries ?? [])]) if (item.hitHandle) grant('hit', item.hitHandle);
      for (const child of result.children ?? []) grant('index', child.indexId);
    }
    if (call.name === 'hcx_history_preview' && result.readHandle) grant('read', result.readHandle);
    if (result.nextCursor) grant('cursor', result.nextCursor, call.name, targetOf(call.arguments));
  }
  async reconcile(activeCallId = null) {
    this.reconciled = false;
    try {
      this.healthy(); await this.bridge.sync(); this.healthy(); this.assertUnboundRequests(activeCallId);
      // Queries return only incomplete local native calls. Complete historical
      // calls and source messages never get rescanned per request or restart.
      for (const row of this.bridge.pending('native-call', 'native-complete')) {
        const call = rowData(row), final = this.bridge.one('native-final', call.callId), body = this.bridge.one('native-body', call.callId);
        need(final && body, 'NATIVE_OUTCOME_UNOBSERVED_HOLD');
        const proof = this.verifyResult(call, final), previous = this.bridge.one('native-observed', call.callId);
        if (previous) need(previous.eventSeq === proof.eventSeq && previous.eventDigest === proof.eventDigest && previous.isError === proof.isError, 'PREVIOUS_SOURCE_OBSERVATION_CHANGED');
        else { this.bridge.put('native-observed', call.callId, proof); this.onCut('after-source-result', proof.checkpoint); }
        if (!proof.isError) { need(body.status === 'succeeded', 'SUCCESS_BODY_REQUIRED'); this.publish(call, body.value.result); }
        this.bridge.put('native-complete', call.callId, { callId: call.callId, eventSeq: proof.eventSeq, eventDigest: proof.eventDigest, isError: proof.isError });
      }
      this.reconciled = true; return this.bridge.checkpoint();
    } catch (error) { return this.guarded(error); }
  }
  async beforeRequest(options) {
    try {
      this.healthy(); need(options?.sessionId === this.identity.sessionId, 'STREAM_SESSION_MISMATCH');
      for (const key of ['provider', 'model', 'maxTokens', 'reasoningEffort']) need(options[key] === this.config[key], 'STREAM_CONFIG_MISMATCH');
      need(schemaDigest(options.tools ?? []) === schemaDigest(this.expectedSchemas), 'STREAM_TOOL_SCHEMA_SET_MISMATCH');
      await this.reconcile();
      const header = this.bridge.findEvents({ type: 'request/header', latest: true }).at(-1);
      need(header && digest(header.data.header.tools ?? []) === digest(options.tools ?? []), 'STREAM_TOOLS_DIFFER_FROM_LOGGED_HEADER');
      need(digest(this.bridge.currentMessages()) === digest(options.messages), 'STREAM_MESSAGES_DIFFER_FROM_CURRENT_PROJECTION');
      return this.bridge.checkpoint();
    } catch (error) { return this.guarded(error); }
  }
  resultFor(callId) {
    this.healthy(); need(this.reconciled, 'SOURCE_RECONCILIATION_REQUIRED'); this.assertObserved(callId);
    const body = this.bridge.one('native-body', callId); need(body?.status === 'succeeded', 'SUCCESS_BODY_REQUIRED'); return copy(body.value.result);
  }
  evidence(callId) {
    this.healthy(); need(this.reconciled, 'SOURCE_RECONCILIATION_REQUIRED');
    const call = this.bridge.one('native-call', callId); need(call, 'BOUND_NATIVE_CALL_REQUIRED');
    return copy({ call, body: this.bridge.one('native-body', callId), final: this.bridge.one('native-final', callId), source: this.bridge.one('native-observed', callId), complete: this.bridge.one('native-complete', callId) });
  }
}

export function installScopedHistoryTools({ agentCtx, agent, core }) {
  need(agent?.ctx === agentCtx && agent === core.agent && agent === core.bridge.agent, 'EXACT_AGENT_SETUP_CONTEXT_REQUIRED');
  core.bridge.assertOwner(agent); const disposers = [];
  try {
    for (const schema of core.expectedSchemas) disposers.push(agentCtx.tools.register({ ...copy(schema), output: { schema: copy(NATIVE_OUTPUT), render: (_args, value) => render(value), presentationMeta: (_args, value) => meta(value) }, execute: (args, exec) => core.execute(schema.name, args, exec) }));
    disposers.push(agentCtx.on('tools/result', (exec, result) => { if (exec.agent === agent) core.observeFinal(exec, result); }));
  } catch (error) { for (const dispose of disposers.reverse()) dispose(); throw error; }
  return () => { for (const dispose of disposers.reverse()) dispose(); };
}
export { RollingHistoryNativeAdapter as NativeHistoryBinding };
