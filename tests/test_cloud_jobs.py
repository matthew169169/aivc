import json
import threading
import time
from types import SimpleNamespace
from pathlib import Path
import pytest
from api import services
from api.background_jobs import JobQueue, JobQueueError, recover_interrupted_jobs
from api.runtime_paths import seed_cloud_workspace
from api.source_cache import SourceCache


def wait_job(client, job):
    deadline = time.monotonic() + 10
    while job["status"] in {"queued", "running"}:
        assert time.monotonic() < deadline, job
        time.sleep(0.01)
        response = client.get('/api/jobs/' + job['job_id'])
        assert response.status_code == 200
        job = response.json()
    return job


def test_background_response_does_not_block_health_or_allow_workspace_switch(client, monkeypatch, model_bytes):
    from test_workflows import upload
    upload(client, model_bytes)
    monkeypatch.setenv("OMICS_GEM_JOB_MODE", "background")
    queue = JobQueue(workers=1, capacity=2)
    monkeypatch.setattr(services, "BACKGROUND_JOBS", queue)
    entered, release = threading.Event(), threading.Event()
    def compute(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return SimpleNamespace(status="completed", message="Done", files={}, step_rows=[])
    monkeypatch.setattr(services, "run_user_package_minimal", compute)
    try:
        response = client.post('/api/runs/portable/workflow/run', json={})
        assert response.status_code == 202, response.text
        job = response.json()
        assert entered.wait(2)
        assert client.get('/api/health').json()['queue']['active_jobs'] == 1
        assert client.get('/api/jobs/' + job['job_id']).json()['status'] == 'running'
        queued = queue.submit('test', 'other', services.TASK_LOGS_DIR, lambda log: {'status': 'completed'})
        queued_status = client.get('/api/jobs/' + queued['job_id'])
        assert queued_status.status_code == 200
        assert queued_status.json()['status'] == 'queued'
        assert client.post('/api/runs/portable/workflow/run', json={}).status_code == 409
        assert client.post('/api/workspace/reset').status_code == 409
        assert client.post('/api/workspace/root', json={'root': str(services.WORKSPACE_ROOT)}).status_code == 409
        assert client.post('/api/runs/portable/archive', json={}).status_code == 409
    finally:
        release.set()
        queue.shutdown()
    assert wait_job(client, job)['status'] == 'completed'


def test_queue_bounds_and_execution_order(tmp_path):
    queue = JobQueue(workers=1, capacity=2)
    entered, release = threading.Event(), threading.Event()
    order = []
    def first(log):
        entered.set()
        assert release.wait(5)
        order.append('first')
        return {'result_status': 'completed'}
    try:
        one = queue.submit('test', 'one', tmp_path, first)
        assert entered.wait(2)
        two = queue.submit('test', 'two', tmp_path, lambda log: order.append('second') or {'result_status': 'completed'})
        assert json.loads((tmp_path / (two['job_id'] + '.json')).read_text())['status'] == 'queued'
        with pytest.raises(JobQueueError) as conflict:
            queue.submit('test', 'one', tmp_path, first)
        assert conflict.value.status_code == 409
        with pytest.raises(JobQueueError) as full:
            queue.submit('test', 'three', tmp_path, first)
        assert full.value.status_code == 429
    finally:
        release.set()
        queue.shutdown()
    assert order == ['first', 'second']
    assert json.loads((tmp_path / (one['job_id'] + '.json')).read_text())['status'] == 'completed'
    assert not queue.has_active(tmp_path)


def test_background_real_fba_archive_and_restore(client, monkeypatch, model_bytes):
    from test_workflows import upload
    upload(client, model_bytes)
    monkeypatch.setenv('OMICS_GEM_JOB_MODE', 'background')
    response = client.post('/api/runs/portable/pipeline', json={'model_generation_methods': ['baseline_gem'], 'analysis_modules': ['fba_pfba']})
    assert response.status_code == 202
    job = wait_job(client, response.json())
    assert job['status'] == 'completed', job
    response = client.post('/api/runs/portable/archive', json={'dry_run': False, 'confirm_run_id': 'portable'})
    assert response.status_code == 202, response.text
    assert wait_job(client, response.json())['status'] == 'completed'
    assert client.get('/api/runs/archived').json()['runs'][0]['run_id'] == 'portable'
    response = client.post('/api/runs/archived/portable/restore', json={'dry_run': False, 'confirm_run_id': 'portable'})
    assert response.status_code == 202, response.text
    assert wait_job(client, response.json())['status'] == 'completed'
    assert client.get('/api/runs/portable/summary').status_code == 200


def test_interrupted_jobs_are_explicitly_failed(tmp_path):
    for status in ['queued', 'running', 'completed']:
        (tmp_path / f'{status}.json').write_text(json.dumps({'job_id': status, 'status': status}))
    (tmp_path / 'bad.json').write_text('broken')
    assert recover_interrupted_jobs(tmp_path) == 2
    assert recover_interrupted_jobs(tmp_path) == 0
    for name in ['queued', 'running']:
        data = json.loads((tmp_path / f'{name}.json').read_text())
        assert data['status'] == 'failed'
        assert data['interruption_reason'] == 'server_restart'
        assert 'restarted' in (tmp_path / f'{name}.log').read_text()
    assert json.loads((tmp_path / 'completed.json').read_text())['status'] == 'completed'


def test_cloud_seed_preserves_existing_data(tmp_path):
    app, cloud = tmp_path / 'app', tmp_path / 'cloud'
    source = app / 'user_runs/shewanella_gecko_case'
    source.mkdir(parents=True)
    (source / 'model.xml').write_text('original')
    seed_cloud_workspace(app, cloud)
    copied = cloud / 'user_runs/shewanella_gecko_case/model.xml'
    assert copied.read_text() == 'original'
    copied.write_text('user results')
    (source / 'model.xml').write_text('new image')
    seed_cloud_workspace(app, cloud)
    assert copied.read_text() == 'user results'
    assert (cloud / 'workspaces').is_dir()
    copied.unlink()
    seed_cloud_workspace(app, cloud)
    assert not copied.exists(), "Archived/deleted examples must not reappear on restart"


def test_index_cache_invalidates_and_isolates_mutations(tmp_path):
    source = tmp_path / 'index.json'
    source.write_text('{"rows": [1]}')
    loads = []
    def load():
        loads.append(1)
        return json.loads(source.read_text())
    cache = SourceCache()
    result = cache.get([source], load)
    result['rows'].append('mutated')
    assert cache.get([source], load)['rows'] == [1]
    assert len(loads) == 1
    source.write_text('{"rows": [1,2]}')
    assert cache.get([source], load)['rows'] == [1, 2]
    assert len(loads) == 2
