async function load(){
  const res = await fetch('data/bundle.json');
  const d = await res.json();
  document.getElementById('version-pill').textContent = d.version;
  document.getElementById('foot-version').textContent = d.version + ' · ' + d.created_at;
  document.getElementById('st-files').textContent = d.total_files.toLocaleString();
  document.getElementById('st-uncomp').textContent = d.uncompressed_gb + ' GB';
  document.getElementById('st-endpoints').textContent = d.endpoint_count;
  document.getElementById('api-count').textContent = d.endpoint_count;
  document.getElementById('case-count').textContent = d.cases.length;
  document.getElementById('run-count').textContent = d.runs.length;
  document.getElementById('doc-count').textContent = d.doc_count;

  // API table
  const tbody = document.querySelector('#api-table tbody');
  let apiFilter = 'ALL', apiQuery = '';
  const seg = document.getElementById('api-seg');
  seg.addEventListener('click', e=>{
    if(e.target.tagName!=='BUTTON') return;
    seg.querySelectorAll('button').forEach(b=>b.classList.remove('on'));
    e.target.classList.add('on'); apiFilter = e.target.dataset.f; renderApi();
  });
  document.getElementById('api-search').addEventListener('input', e=>{apiQuery=e.target.value.toLowerCase();renderApi();});
  function renderApi(){
    tbody.innerHTML = d.endpoints
      .filter(x=>(apiFilter==='ALL'||x.method===apiFilter) && (!apiQuery || x.path.toLowerCase().includes(apiQuery)))
      .map(x=>`<tr><td class="m${x.method}">${x.method}</td><td><code>${x.path}</code></td></tr>`).join('');
  }
  renderApi();

  // cases / runs / omics
  document.getElementById('case-list').innerHTML = d.cases.map(c=>`<li>${c}</li>`).join('');
  document.getElementById('run-list').innerHTML = d.runs.map(c=>`<li>${c}</li>`).join('');
  document.getElementById('omics-list').innerHTML = d.omics_modules.map(c=>`<li>${c}</li>`).join('');

  // validation
  document.getElementById('accept-list').innerHTML = d.validation.acceptance.map(x=>`<li>${x}</li>`).join('');
  document.getElementById('browser-list').innerHTML = d.validation.browser_checks.map(x=>`<li>${x}</li>`).join('');
  document.getElementById('limit-list').innerHTML = d.validation.limitations.map(x=>`<li>${x}</li>`).join('');

  // bundle bars
  const cats = Object.entries(d.categories).slice(0,14);
  const max = cats[0][1];
  document.getElementById('cat-bars').innerHTML = cats.map(([k,v])=>
    `<div class="bar-row"><span>${k}</span><div class="bar-track"><div class="bar-fill" style="width:${(v/max*100).toFixed(1)}%"></div></div><span>${v.toLocaleString()}</span></div>`).join('');
  document.getElementById('roots-list').innerHTML = d.mutable_roots.map(r=>`<li><code>${r}</code></li>`).join('');

  // docs
  const grid = document.getElementById('doc-grid');
  const reader = document.getElementById('doc-reader');
  const body = document.getElementById('doc-body');
  const title = document.getElementById('doc-title');
  document.getElementById('doc-close').onclick = ()=>reader.classList.add('hidden');
  let q='';
  document.getElementById('doc-search').addEventListener('input',e=>{q=e.target.value.toLowerCase();renderDocs();});
  function renderDocs(){
    grid.innerHTML = d.docs
      .filter(x=>!q||x.path.toLowerCase().includes(q)||x.preview.toLowerCase().includes(q))
      .map(x=>`<div class="doc-card" data-p="${x.path}"><h4>${x.path}</h4><p>${(x.preview||'').slice(0,180).replace(/</g,'&lt;')}… · ${(x.size/1024).toFixed(1)} KB</p></div>`).join('');
  }
  renderDocs();
  grid.addEventListener('click', async e=>{
    const card = e.target.closest('.doc-card'); if(!card) return;
    const p = card.dataset.p;
    title.textContent = p;
    body.textContent = 'Loading site_docs/' + p + ' …';
    reader.classList.remove('hidden');
    reader.scrollIntoView({behavior:'smooth'});
    try{
      const r = await fetch('site_docs/' + encodeURIComponent(p));
      body.textContent = await r.text();
    }catch(err){ body.textContent = 'Failed to load: ' + err; }
  });
}
load();
