const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('assets/api-transport.js', 'utf8');
function response(status, data, headers = {}) {
  return { status, ok: status >= 200 && status < 300, headers: { get: key => headers[key] || null }, text: async () => typeof data === 'string' ? data : JSON.stringify(data) };
}
function transport(fetch) {
  const events = [];
  const window = { fetch, dispatchEvent: event => events.push(event.detail) };
  vm.runInNewContext(source, { window, AbortController, Map, Set, Date, JSON, CustomEvent: class { constructor(name, data) { this.detail = data.detail; } },
    // Resolve retry/poll delays immediately; keep timeout timers cancellable.
    setTimeout: (fn, ms) => ms >= 60000 ? setTimeout(fn, ms) : setTimeout(fn, 0), clearTimeout });
  return { request: (path, options = {method:'GET'}) => window.OMICS_GEM_REQUEST('https://cloud.example', path, options, Error), events };
}
test('coalesces and caches metadata reads while isolating callers', async () => {
  let calls = 0;
  const { request } = transport(async () => { calls++; return response(200, {rows:[1]}); });
  const [a, b] = await Promise.all([request('/api/resources/search?q=test'), request('/api/resources/search?q=test')]);
  a.rows.push(2);
  assert.deepEqual(b.rows, [1]);
  assert.deepEqual((await request('/api/resources/search?q=test')).rows, [1]);
  assert.equal(calls, 1);
});
test('retries a temporary read failure and reports recovery', async () => {
  let calls = 0;
  const t = transport(async () => ++calls === 1 ? response(503, 'Sleeping') : response(200, {status:'ok'}));
  assert.equal((await t.request('/api/health')).status, 'ok');
  assert.equal(calls, 2);
  assert.ok(t.events.some(event => event.state === 'reconnecting'));
});
test('never retries a mutation after a connection failure', async () => {
  let calls = 0;
  const t = transport(async () => { calls++; throw new TypeError('disconnected'); });
  await assert.rejects(t.request('/api/runs/run/workflow/run', {method:'POST',body:'{}'}), /Check Jobs/);
  assert.equal(calls, 1);
});
test('follows background jobs to their actual terminal result', async () => {
  const calls = [];
  const t = transport(async (url, options) => {
    calls.push([url, options.method]);
    if (options.method === 'POST') return response(202, {job_id:'test_1',status:'queued'});
    return response(200, {job_id:'test_1',status:calls.length === 2 ? 'running' : 'completed',result:{message:'Solved'}});
  });
  const job = await t.request('/api/runs/run/workflow/run', {method:'POST',body:'{}'});
  assert.equal(job.status, 'completed');
  assert.equal(job.result.message, 'Solved');
  assert.equal(calls.filter(x => x[1] === 'POST').length, 1);
  assert.ok(t.events.some(event => event.state === 'working' && event.jobId === 'test_1'));
});
test('preserves failed job status and does not resubmit it', async () => {
  const t = transport(async (url, options) => response(options.method === 'POST' ? 202 : 200, {job_id:'test_2',status:options.method === 'POST' ? 'queued' : 'failed',error:'solver failed'}));
  const job = await t.request('/api/runs/run/workflow/run', {method:'POST'});
  assert.equal(job.status, 'failed');
  assert.equal(job.error, 'solver failed');
});
test('invalidates resource metadata after a successful mutation', async () => {
  let reads = 0;
  const t = transport(async (url, options) => response(200, options.method === 'POST' ? {} : {revision:++reads}));
  assert.equal((await t.request('/api/environment/backend')).revision, 1);
  await t.request('/api/environment/external-dependencies/config', {method:'POST'});
  assert.equal((await t.request('/api/environment/backend')).revision, 2);
});
test('explains non-JSON gateway errors without leaking HTML', async () => {
  const t = transport(async () => response(500, '<html>broken</html>'));
  await assert.rejects(t.request('/api/health'), /invalid response/);
});
