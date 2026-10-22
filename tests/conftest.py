from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from api.browser_app import app
from api import services


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("OMICS_GEM_AUTH_ENABLED", "false")
    monkeypatch.setattr(services, "WORKSPACE_ROOT", tmp_path)
    monkeypatch.setattr(services, "USER_RUNS_DIR", tmp_path / "user_runs")
    monkeypatch.setattr(services, "EXAMPLES_DIR", tmp_path / "examples")
    monkeypatch.setattr(services, "TASK_LOGS_DIR", tmp_path / "task_logs")
    monkeypatch.setattr(services, "ATLAS_CURATION_WORKSPACES_DIR", tmp_path / "atlas_curation_workspaces")
    monkeypatch.setattr(services, "ALLOWED_FILE_ROOTS", (tmp_path, services.APP_ROOT))
    monkeypatch.setattr(services, "WORKSPACE_CONFIG_PATH", tmp_path / "workspace.json")
    with TestClient(app) as c:
        yield c


@pytest.fixture
def model_bytes(tmp_path):
    from omics_router.cobra_runner import _redirect_cobra_cache
    _redirect_cobra_cache()
    from cobra import Model, Reaction, Metabolite
    from cobra.io import write_sbml_model
    model = Model("portable_test")
    metabolite = Metabolite("carbon_c", compartment="c")
    uptake = Reaction("UPTAKE", lower_bound=0, upper_bound=10)
    uptake.add_metabolites({metabolite: 1})
    growth = Reaction("BIOMASS", lower_bound=0, upper_bound=1000)
    growth.add_metabolites({metabolite: -1})
    growth.gene_reaction_rule = "gene1"
    model.add_reactions([uptake, growth])
    model.objective = growth
    path = tmp_path / "toy.xml"
    write_sbml_model(model, str(path))
    return path.read_bytes()
