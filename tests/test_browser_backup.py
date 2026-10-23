import io
import zipfile
import pytest
from browser import runtime


def test_browser_backup_roundtrip_preserves_projects_and_results(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, 'DATA_DIR', tmp_path)
    from api import services
    monkeypatch.setattr(services, '_initialize_workspace_from_config', lambda: None)
    saved = tmp_path / 'workspaces/project/user_runs/toy/results.csv'
    saved.parent.mkdir(parents=True)
    saved.write_text('status,value\noptimal,8\n')
    (tmp_path / '.browser_examples_initialized.json').write_text('{}')
    data = runtime.backup()
    saved.write_text('changed')
    assert runtime.restore(data)['file_count'] == 2
    assert saved.read_text() == 'status,value\noptimal,8\n'
    assert (tmp_path / '.browser_examples_initialized.json').is_file()


def test_browser_restore_rejects_traversal_before_writing(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, 'DATA_DIR', tmp_path)
    destination = tmp_path / 'valid.csv'
    destination.write_text('keep existing data')
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as archive:
        archive.writestr('browser-backup.json', '{"format":"omics-gem-browser","version":1}')
        archive.writestr('data/valid.csv', 'overwrite')
        archive.writestr('data/../escaped.csv', 'unsafe')
    with pytest.raises(ValueError, match='unsafe'):
        runtime.restore(data.getvalue())
    assert destination.read_text() == 'keep existing data'
    assert not (tmp_path.parent / 'escaped.csv').exists()
