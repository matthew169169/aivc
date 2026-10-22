import json
from pathlib import Path
import pytest
from api import services
from omics_router.constraints import read_csv_records, write_csv, read_package_input_map, resolve_package_input_path
from omics_router.user_pipeline import find_staged_model_path, find_staged_omics_path
from omics_router.id_mapping import run_id_mapping_review


def upload(client, model_bytes, run_id="portable"):
    r = client.post("/api/workspace/upload-run-package", data={"run_id": run_id}, files={"model_file": ("toy.xml", model_bytes, "application/xml")})
    assert r.status_code == 200, r.text
    return r.json()


def move_input_map_to_windows(package):
    rows = read_csv_records(package / "input_file_map.csv")
    for row in rows:
        relative = row["relative_path"].replace("/", "\\")
        row["relative_path"] = relative
        row["path"] = "D:\\generate\\user_runs\\old_name\\" + relative
    write_csv(package / "input_file_map.csv", rows)


def test_uploaded_moved_package_executes_fba_and_downloads(client, model_bytes):
    data = upload(client, model_bytes)
    package = Path(data["output_dir"])
    move_input_map_to_windows(package)
    assert find_staged_model_path(package).is_file()
    job_response = client.post("/api/runs/portable/pipeline", json={"model_generation_methods": ["baseline_gem"], "analysis_modules": ["fba_pfba"]})
    assert job_response.status_code == 200, job_response.text
    job = job_response.json()
    assert job["status"] == "completed", job
    assert job["result"]["result_status"] != "failed", job
    manifest_path = next((package / "variant_cobra_results").glob("*/cobra_runner_manifest.json"))
    manifest = json.loads(manifest_path.read_text())
    assert manifest["cobra_available"] is True
    rows = read_csv_records(manifest_path.parent / "fba_summary.csv")
    assert rows, manifest
    assert any(float(row.get("objective_value") or 0) == pytest.approx(10) for row in rows), rows
    assert client.get(f'/api/jobs/{job["job_id"]}').json()["status"] == "completed"
    assert "Running selected" in client.get(f'/api/jobs/{job["job_id"]}/logs').json()["log"]
    old_path = "D:\\generate\\user_runs\\portable\\inputs\\model\\model__toy.xml"
    download = client.get("/api/files", params={"path": old_path})
    assert download.status_code == 200
    assert b"portable_test" in download.content
    assert client.get("/api/files", params={"path": old_path.split("generate\\", 1)[1]}).status_code == 200


def test_missing_model_is_failed_job(client):
    package = services.USER_RUNS_DIR / "missing"
    package.mkdir(parents=True)
    (package / "run_config.json").write_text("{}")
    r = client.post("/api/runs/missing/pipeline", json={"model_generation_methods": ["baseline_gem"], "analysis_modules": ["fba_pfba"]})
    assert r.status_code == 200
    assert r.json()["status"] == "failed", r.text
    assert r.json()["result"]["result_status"] == "failed"


def test_portable_omics_and_mapping(client, model_bytes):
    data = upload(client, model_bytes)
    package = Path(data["output_dir"])
    table = package / "inputs/omics/expression.csv"
    table.parent.mkdir(parents=True, exist_ok=True)
    write_csv(table, [{"gene_id": "gene1", "sample": "s1", "condition": "c1", "value": "2", "unit": "relative"}])
    rows = read_csv_records(package / "input_file_map.csv")
    rows.append({"kind": "omics_table", "role": "transcriptomics", "relative_path": "inputs/omics/expression.csv", "path": str(table)})
    write_csv(package / "input_file_map.csv", rows)
    move_input_map_to_windows(package)
    assert find_staged_omics_path(package, "transcriptomics") == table.resolve()
    result = run_id_mapping_review(package)
    assert json.loads(Path(result.files["manifest"]).read_text())["model_status"] == "indexed"
    assert any(row["mapping_status"] == "mapped" for row in result.detail_rows)
    assert read_package_input_map(package, normalized=True)
    assert resolve_package_input_path(package, {"relative_path": "", "path": ""}) is None
    assert resolve_package_input_path(package, {"relative_path": "inputs"}) is None


@pytest.mark.parametrize("result_status, expected", [("failed", "failed"), ("input_missing", "failed"), ("probe_failed", "failed"), ("skipped_cobra_missing", "skipped"), ("dry_run", "skipped"), ("completed", "completed")])
def test_job_status_matches_execution(client, result_status, expected):
    job = services.run_sync_job("test", "run", lambda log: {"result_status": result_status})
    assert job["status"] == expected
    assert services.get_job(job["job_id"])["status"] == expected


def test_environment_repair_preview_is_portable(client):
    r = client.post("/api/environment/backend/repair", json={"mode": "full", "dry_run": True})
    assert r.status_code == 200, r.text
    job = r.json()
    assert job["status"] == "skipped"
    assert job["result"]["command"][1:4] == ["-m", "pip", "install"]
    assert job["result"]["command"][-1].endswith("requirements-optional.txt")
    assert client.post("/api/environment/backend/repair", json={"dry_run": False}).status_code == 400


def test_visualization_report_and_ml_jobs(client, model_bytes):
    data = upload(client, model_bytes)
    package = Path(data["output_dir"])
    pipeline = client.post("/api/runs/portable/workflow/run", json={"model_generation_methods": ["baseline_gem"], "analysis_modules": ["fba_pfba"]}).json()
    assert pipeline["status"] == "completed", pipeline
    for path, payload in [("visualizations/interactive-render", {"variant_id": "baseline_gem", "top_n": 20}), ("visualizations/sammi-native-export", {"variant_id": "baseline_gem"}), ("reports", {})]:
        r = client.post(f"/api/runs/portable/{path}", json=payload)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "completed", r.json()
    write_csv(package / "ml_results/ml_feature_matrix.csv", [{"sample": f"s{i}", "condition": f"c{i}", "target": i, "flux__BIOMASS": i * 2} for i in range(1, 7)])
    r = client.post("/api/runs/portable/ml-hybrid/profiles", json={"profile_id": "smoke", "target_column": "target", "task_type": "regression"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed", r.json()
    r = client.post("/api/runs/portable/ml-hybrid/profiles/smoke/export", json={"export_format": "both"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed", r.json()


def test_static_and_file_boundaries(client):
    assert client.get("/").status_code == 200
    assert client.get("/assets/index-D6lmiGWb.js").status_code == 200
    assert client.get("/api/unknown").status_code == 404
    assert client.get("/assets/missing.js").status_code == 404
    assert client.get("/.git/config").status_code == 404
    assert client.get("/requirements.txt").status_code == 404
    assert client.get("/api/files", params={"path": "/etc/passwd"}).status_code == 403
    assert client.get("/api/files", params={"path": "user_runs/../../../../etc/passwd"}).status_code in {403, 404}


def test_project_creation_and_switching(client, tmp_path, monkeypatch):
    monkeypatch.setattr(services, "APP_ROOT", tmp_path)
    r = client.post("/api/projects", json={"project_id": "research", "name": "Research project"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "created"
    assert r.json()["project"]["name"] == "Research project"
    assert Path(r.json()["project"]["user_runs_dir"]).is_dir()
    assert client.get("/api/workspace").json()["workspace_root"] == str(tmp_path / "workspaces/research")
    assert client.post("/api/projects", json={"project_id": "research"}).status_code == 409
    assert client.post("/api/projects", json={"project_id": "../escape"}).status_code == 400
    assert client.post("/api/projects", json={"project_id": "second"}).status_code == 200
    assert {p["project_id"] for p in client.get("/api/projects").json()["projects"]} == {"research", "second"}


def test_bundled_input_and_native_export_portability():
    from omics_router.sammi_native_export import list_sammi_native_exports
    root = Path(__file__).resolve().parents[1]
    for package in (root / "user_runs").iterdir():
        if not (package / "input_file_map.csv").is_file():
            continue
        rows = read_package_input_map(package)
        assert rows
        assert all(Path(row["path"]).is_file() for row in rows), package
        exports = list_sammi_native_exports(package)
        assert exports["count"] > 0
        assert all(item["session_exists"] and item["check_exists"] for item in exports["exports"]), exports


def test_atlas_candidates_and_curation_lifecycle(client):
    model_id = "model_synechocystis_ijn678_spkb_case"
    evidence_id = "omics_synechocystis_spkb_annotation_validation"
    payload = {"resource_ids": [model_id, evidence_id], "run_id": "atlas_case"}
    r = client.post("/api/resources/candidate-package/preview", json=payload)
    assert r.status_code == 200, r.text
    assert r.json()["can_stage"], r.json()
    staged = client.post("/api/resources/candidate-package/stage", json=payload)
    assert staged.status_code == 200, staged.text
    assert find_staged_model_path(Path(staged.json()["output_dir"])).is_file()
    create = client.post("/api/resources/curation-workspaces", json={"resource_ids": [model_id, evidence_id], "workspace_id": "curation_test"})
    assert create.status_code == 200, create.text
    response = client.post("/api/resources/curation-workspaces/curation_test/curated-files", data={"resource_id": evidence_id, "role": "transcriptomics"}, files={"file": ("expression.csv", b"gene_id,sample,value,unit,condition\nsll1574,sample1,2,relative,control\n", "text/csv")})
    assert response.status_code == 200, response.text
    preview = client.post("/api/resources/curation-workspaces/curation_test/mapping-preview", json={})
    assert preview.status_code == 200, preview.text
    assert preview.json().get("mapping_preview", {}).get("model_summary", {}).get("reaction_count", 0) > 0, preview.json()
    staged = client.post("/api/resources/curation-workspaces/curation_test/stage-run-package", json={"run_id": "curated_case"})
    assert staged.status_code == 200, staged.text


def test_builtin_examples_available_in_new_workspace(client):
    response = client.get("/api/workspace/example-presets")
    assert response.status_code == 200
    ids = {row["preset_id"] for row in response.json()["presets"]}
    assert {"shewanella_gecko_case", "putida_acetate_isoprenol_case", "synechocystis_spkb_case"} <= ids
    response = client.post("/api/workspace/import-example-preset", json={"preset_id": "synechocystis_spkb_case", "dry_run": True})
    assert response.status_code == 200, response.text


def test_case_listing_does_not_execute_comparison_qa(client, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(services, "USER_RUNS_DIR", root / "user_runs")
    def unexpected_check(*args, **kwargs):
        raise AssertionError("Listing cases must not trigger deep comparison QA")
    monkeypatch.setattr(services, "case_study_readiness", unexpected_check)
    response = client.get("/api/case-studies")
    assert response.status_code == 200, response.text
    cases = response.json()["case_studies"]
    assert len(cases) == 3
    assert all(case["readiness_source"] == "saved_check" for case in cases)
