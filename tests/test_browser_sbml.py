"""Compare the browser SBML reader against real libSBML/COBRA results."""
import io
import os
import subprocess
import sys
from pathlib import Path
import pytest
from browser import sbml
from omics_router.cobra_runner import _redirect_cobra_cache

_redirect_cobra_cache()
from cobra.io import read_sbml_model, write_sbml_model
from cobra.util.solver import linear_reaction_coefficients


def signature(model):
    return {
        r.id: (r.bounds, {m.id: n for m, n in r.metabolites.items()}, {g.id for g in r.genes})
        for r in model.reactions
    }


def objectives(model):
    return {r.id: n for r, n in linear_reaction_coefficients(model).items()}


def test_browser_sbml_toy_roundtrip_and_pfba(model_bytes):
    from cobra.flux_analysis import pfba, flux_variability_analysis
    native = read_sbml_model(io.StringIO(model_bytes.decode()))
    model = sbml.read_sbml_model(io.BytesIO(model_bytes))
    assert signature(model) == signature(native)
    assert objectives(model) == objectives(native)
    assert model.slim_optimize() == pytest.approx(10)
    assert pfba(model).fluxes['BIOMASS'] == pytest.approx(10)
    assert flux_variability_analysis(model, ['BIOMASS'], processes=1).loc['BIOMASS', 'minimum'] == pytest.approx(10)
    model.reactions.BIOMASS.gene_reaction_rule = '(gene1 and gene.2) or gene3'
    model.reactions.BIOMASS.notes['SUBSYSTEM'] = 'Growth'
    model.genes.get_by_id('gene1').annotation = {'uniprot': ['P12345']}
    output = io.StringIO()
    sbml.write_sbml_model(model, output)
    written = output.getvalue()
    reparsed = read_sbml_model(io.StringIO(written))
    assert signature(reparsed) == signature(model)
    assert reparsed.slim_optimize() == pytest.approx(10)
    assert sbml.read_sbml_model(io.StringIO(written)).slim_optimize() == pytest.approx(10)


@pytest.mark.parametrize('run_id', ['shewanella_gecko_case', 'putida_acetate_isoprenol_case', 'synechocystis_spkb_case'])
def test_browser_reader_matches_bundled_models(run_id):
    path = next((Path('user_runs') / run_id / 'inputs/model').glob('*.xml'))
    native = read_sbml_model(str(path))
    browser = sbml.read_sbml_model(path)
    assert signature(browser) == signature(native)
    assert objectives(browser) == objectives(native)
    expected, actual = native.optimize(), browser.optimize()
    assert actual.status == expected.status
    if actual.status == 'optimal':
        assert actual.objective_value == pytest.approx(expected.objective_value, rel=1e-7, abs=1e-7)


def test_browser_reader_rejects_dynamic_models_and_missing_objective(model_bytes):
    xml = model_bytes.decode()
    altered = xml.replace('</model>', '<listOfRules><assignmentRule variable="x"/></listOfRules></model>')
    with pytest.raises(sbml.CobraSBMLError, match='Dynamic SBML'):
        sbml.read_sbml_model(io.StringIO(altered))
    model = sbml.read_sbml_model(io.BytesIO(model_bytes))
    model.objective = {}
    output = io.StringIO()
    sbml.write_sbml_model(model, output)
    with pytest.raises(sbml.CobraSBMLError, match='No nonzero objective'):
        sbml.read_sbml_model(io.StringIO(output.getvalue()))


def test_cobra_imports_without_native_libsbml(tmp_path):
    program = '''
import importlib.abc, sys
class NoLibSBML(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname == 'libsbml' or fullname.startswith('libsbml.'):
            raise ImportError('Native libSBML is intentionally unavailable')
sys.meta_path.insert(0, NoLibSBML())
from omics_router.cobra_runner import _redirect_cobra_cache
_redirect_cobra_cache()
from browser.sbml import install
install()
import cobra
from cobra.io import read_sbml_model
assert read_sbml_model.__module__ == 'browser.sbml'
assert 'libsbml' not in sys.modules
print('COBRA imports with the browser SBML adapter')
'''
    environment = {**os.environ, 'XDG_CACHE_HOME': str(tmp_path), 'LOCALAPPDATA': str(tmp_path)}
    result = subprocess.run([sys.executable, '-c', program], capture_output=True, text=True, env=environment)
    assert result.returncode == 0, result.stderr
