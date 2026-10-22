const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('assets/api-bootstrap.js', 'utf8');
function base(hostname, search = '', configured) {
  const window = { location: { hostname, search, origin: `https://${hostname}` }, OMICS_GEM_API_BASE: configured };
  vm.runInNewContext(source, { window, URL, URLSearchParams });
  return window.OMICS_GEM_API_BASE;
}
test('Pages uses the deployed backend; server uses same origin', () => {
  assert.equal(base('matthew169169.github.io'), 'https://aivc-tcls.onrender.com');
  assert.equal(base('localhost'), 'https://localhost');
});
test('explicit API links work without retaining stale overrides', () => {
  assert.equal(base('matthew169169.github.io', '?api=https%3A%2F%2Fexample.com%2F'), 'https://example.com');
  assert.equal(base('localhost', '', 'https://configured.example/'), 'https://configured.example');
});
test('invalid URLs and credentials retain the default', () => {
  for (const api of ['javascript:alert(1)', 'invalid', 'https://user:password@example.com', 'https://example.com/?secret=1']) {
    assert.equal(base('matthew169169.github.io', '?api=' + encodeURIComponent(api)), 'https://aivc-tcls.onrender.com');
  }
});
