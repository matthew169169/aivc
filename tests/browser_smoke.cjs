/* Full browser test against a STATIC server: there is no Python API process. */
const assert = require('node:assert/strict');
const { chromium } = require('../browser/node_modules/playwright');
const fs = require('node:fs');
const base = process.env.BROWSER_TEST_URL || 'http://127.0.0.1:4173/?mode=browser';
const xml = `<?xml version="1.0" encoding="utf-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version1/core" xmlns:fbc="http://www.sbml.org/sbml/level3/version1/fbc/version2" level="3" version="1" fbc:required="false">
<model id="browser_test" fbc:strict="true">
<listOfCompartments><compartment id="c" constant="true"/></listOfCompartments>
<listOfSpecies><species id="M_carbon_c" compartment="c" boundaryCondition="false" constant="false" hasOnlySubstanceUnits="false"/></listOfSpecies>
<listOfParameters><parameter id="zero" value="0" constant="true"/><parameter id="uptake" value="8" constant="true"/><parameter id="max" value="1000" constant="true"/></listOfParameters>
<listOfReactions>
<reaction id="R_UPTAKE" reversible="false" fast="false" fbc:lowerFluxBound="zero" fbc:upperFluxBound="uptake"><listOfProducts><speciesReference species="M_carbon_c" stoichiometry="1" constant="true"/></listOfProducts></reaction>
<reaction id="R_BIOMASS" reversible="false" fast="false" fbc:lowerFluxBound="zero" fbc:upperFluxBound="max"><listOfReactants><speciesReference species="M_carbon_c" stoichiometry="1" constant="true"/></listOfReactants></reaction>
</listOfReactions>
<fbc:listOfObjectives fbc:activeObjective="obj"><fbc:objective fbc:id="obj" fbc:type="maximize"><fbc:listOfFluxObjectives><fbc:fluxObjective fbc:reaction="R_BIOMASS" fbc:coefficient="1"/></fbc:listOfFluxObjectives></fbc:objective></fbc:listOfObjectives>
</model></sbml>`;

async function api(page, path, data) {
  return page.evaluate(async ({ path, data }) => {
    const response = await fetch(window.OMICS_GEM_API_BASE + path, data === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
    const result = await response.json();
    if (!response.ok) throw new Error(JSON.stringify(result));
    return result;
  }, { path, data });
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ acceptDownloads: true });
  const page = await context.newPage();
  const forbidden = [], errors = [];
  page.on('request', request => { if (/onrender\.com|oraclecloud\.com/.test(request.url())) forbidden.push(request.url()); });
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); console.log('Browser:', message.text().slice(0, 1000)); });
  page.on('pageerror', error => { errors.push(error.message); console.log('Page error:', error.message); });
  page.on('worker', worker => worker.on('console', message => console.log('Worker:', message.text().slice(0, 1000))));
  try {
    await page.goto(base);
    const health = await api(page, '/api/health');
    assert.equal(health.execution_mode, 'browser');
    assert.equal(health.api_server_required, false);
    assert.equal((await api(page, '/api/case-studies')).case_studies.length, 3);
    assert.ok((await api(page, '/api/runs')).runs.length >= 3);
    console.log('PASS: browser boot, saved examples and API-free catalog');
    const uploaded = await page.evaluate(async xml => {
      const body = new FormData();
      body.set('run_id', 'browser_smoke'); body.set('model_file', new File([xml], 'model.xml', { type: 'application/xml' }));
      const response = await fetch(window.OMICS_GEM_API_BASE + '/api/workspace/upload-run-package', { method: 'POST', body });
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    }, xml);
    assert.equal(uploaded.run_id, 'browser_smoke');
    const job = await api(page, '/api/runs/browser_smoke/workflow/run', { model_generation_methods: ['baseline_gem'], analysis_modules: ['fba_pfba'] });
    assert.equal(job.status, 'completed', JSON.stringify(job));
    const fba = await page.evaluate(async path => {
      const response = await fetch(window.OMICS_GEM_API_BASE + '/api/files?path=' + encodeURIComponent(path + '/variant_cobra_results/variant_fba_summary.csv'));
      if (!response.ok) throw new Error(await response.text());
      return response.text();
    }, uploaded.output_dir);
    assert.match(fba, /optimal/);
    const lines = fba.trim().split(/\r?\n/), header = lines[0].split(','), values = lines[1].split(',');
    assert.equal(Number(values[header.indexOf('objective_value')]), 8, fba);
    console.log('PASS: real browser FBA objective=8');
    for (const [path, data] of [['visualizations/interactive-render', { variant_id: 'baseline_gem', top_n: 20 }], ['visualizations/sammi-native-export', { variant_id: 'baseline_gem' }], ['reports', {}]]) {
      const result = await api(page, '/api/runs/browser_smoke/' + path, data);
      assert.equal(result.status, 'completed', JSON.stringify(result));
    }
    console.log('PASS: browser maps, SAMMI export and reports');
    const capabilities = await api(page, '/api/browser/capabilities');
    assert.ok(capabilities.unavailable.includes('MATLAB'));
    const backup = await page.evaluate(async () => {
      const r = await fetch(window.OMICS_GEM_API_BASE + '/api/browser/backup');
      return { status: r.status, bytes: (await r.arrayBuffer()).byteLength };
    });
    assert.equal(backup.status, 200); assert.ok(backup.bytes > 100);
    console.log('PASS: complete workspace backup', backup.bytes);
    // A normal anchor download traverses the service worker, outside fetch().
    await page.evaluate(() => navigator.serviceWorker.ready);
    await page.waitForFunction(() => !!navigator.serviceWorker.controller);
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.evaluate(path => { const a = document.createElement('a'); a.href = window.OMICS_GEM_API_BASE + '/api/files?path=' + encodeURIComponent(path + '/variant_cobra_results/variant_fba_summary.csv'); a.click(); }, uploaded.output_dir)
    ]);
    assert.equal(download.suggestedFilename(), 'variant_fba_summary.csv');
    assert.match(fs.readFileSync(await download.path(), 'utf8'), /optimal/);
    console.log('PASS: ordinary file download through browser service worker');
    await page.reload();
    assert.equal((await api(page, '/api/runs/browser_smoke/summary')).run_id, 'browser_smoke');
    console.log('PASS: uploaded model and results survive reload');
    assert.deepEqual(forbidden, [], 'The browser must never contact the previous API server');
    assert.deepEqual(errors, [], 'Uncaught browser errors');
    console.log('Browser integration checks passed.');
  } catch (error) {
    console.error(error);
    console.error('Status:', await page.locator('#browser-runtime-status').innerText().catch(() => 'unavailable'));
    await page.screenshot({ path: 'browser-failure.png', fullPage: true }).catch(() => {});
    process.exitCode = 1;
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
