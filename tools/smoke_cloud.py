"""Exercise the actual cloud container over HTTP, including a real solver job."""
from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.request import Request, urlopen


RUN_ID = 'cloud_ci_smoke'


def request(base, path, data=None, content_type='application/json'):
    body = json.dumps(data).encode() if isinstance(data, dict) else data
    req = Request(base + path, data=body, headers={'Content-Type': content_type} if body is not None else {})
    with urlopen(req, timeout=20) as response:
        return response.status, json.loads(response.read())


def wait_ready(base):
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        try:
            _, health = request(base, '/api/health')
            if health.get('status') == 'ok':
                return health
        except (OSError, ValueError):
            time.sleep(1)
    raise RuntimeError('Container did not become ready.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://127.0.0.1:8765')
    parser.add_argument('--verify-restart', action='store_true')
    args = parser.parse_args()
    base = args.base.rstrip('/')
    health = wait_ready(base)
    assert health['job_mode'] == 'background', health
    assert health['workspace_root'].startswith('/data'), health
    if args.verify_restart:
        _, summary = request(base, f'/api/runs/{RUN_ID}/summary')
        assert summary['run_id'] == RUN_ID, summary
        package = Path(health['user_runs_dir']) / RUN_ID
        summaries = list((package / 'variant_cobra_results').glob('*/fba_summary.csv'))
        assert summaries, 'Solver output did not survive restart'
        rows = list(csv.DictReader(summaries[0].open()))
        assert any(abs(float(row.get('objective_value') or 0) - 8) < 1e-6 for row in rows), rows
        print('Cloud restart check passed: uploaded model and solver outputs persisted.')
        return
    with urlopen(base + '/') as response:
        html = response.read().decode()
    import re
    for asset in re.findall(r'(?:src|href)="(\./assets/[^\"]+)"', html):
        with urlopen(base + '/' + asset.removeprefix('./')) as response:
            assert response.status == 200
    assert 'api-transport' in html
    _, examples = request(base, '/api/workspace/example-presets')
    assert examples['count'] >= 3, examples
    _, environment = request(base, '/api/environment/backend')
    assert environment['cobra_importable'], environment['status']
    _, cases = request(base, '/api/case-studies')
    assert len(cases['case_studies']) == 3
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from omics_router.cobra_runner import _redirect_cobra_cache
    _redirect_cobra_cache()
    from cobra import Model, Reaction, Metabolite
    from cobra.io import write_sbml_model
    model = Model('cloud_ci_model')
    metabolite = Metabolite('carbon_c', compartment='c')
    uptake = Reaction('UPTAKE', lower_bound=0, upper_bound=8)
    uptake.add_metabolites({metabolite: 1})
    biomass = Reaction('BIOMASS')
    biomass.add_metabolites({metabolite: -1})
    model.add_reactions([uptake, biomass])
    model.objective = biomass
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'model.xml'
        write_sbml_model(model, str(path))
        model_data = path.read_bytes()
    boundary = uuid.uuid4().hex
    payload = (f'--{boundary}\r\nContent-Disposition: form-data; name="run_id"\r\n\r\n{RUN_ID}\r\n'
               f'--{boundary}\r\nContent-Disposition: form-data; name="model_file"; filename="model.xml"\r\nContent-Type: application/xml\r\n\r\n').encode() + model_data + f'\r\n--{boundary}--\r\n'.encode()
    _, uploaded = request(base, '/api/workspace/upload-run-package', payload, f'multipart/form-data; boundary={boundary}')
    assert uploaded['run_id'] == RUN_ID
    status, job = request(base, f'/api/runs/{RUN_ID}/workflow/run', {'model_generation_methods':['baseline_gem'], 'analysis_modules':['fba_pfba']})
    assert status == 202, (status, job)
    deadline = time.monotonic() + 120
    while job['status'] in {'queued', 'running'}:
        assert time.monotonic() < deadline, job
        time.sleep(0.2)
        _, job = request(base, '/api/jobs/' + job['job_id'])
    assert job['status'] == 'completed', job
    package = Path(uploaded['output_dir'])
    summary = next((package / 'variant_cobra_results').glob('*/fba_summary.csv'))
    rows = list(csv.DictReader(summary.open()))
    assert any(abs(float(row.get('objective_value') or 0) - 8) < 1e-6 for row in rows), rows
    assert request(base, '/api/health')[1]['status'] == 'ok'
    print('Cloud HTTP smoke check passed: assets, catalog, upload, queued job and real FBA objective=8.')


if __name__ == '__main__':
    main()
