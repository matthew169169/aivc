"""ElementTree SBML adapter for COBRApy in WebAssembly.

Supports steady-state Core L2/L3 models with FBC v1/v2, or legacy COBRA
kinetic-law bounds. Dynamic SBML constructs are rejected explicitly. This is
not a replacement for libSBML validation or a dynamic SBML simulator.
"""
from __future__ import annotations

import io
import math
import re
import sys
import types
import xml.etree.ElementTree as ET
from pathlib import Path

CORE = "http://www.sbml.org/sbml/level3/version1/core"
FBC = "http://www.sbml.org/sbml/level3/version1/fbc/version2"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
BQB = "http://biomodels.net/biology-qualifiers/"


class CobraSBMLError(ValueError):
    pass


def local(value):
    return value.rsplit("}", 1)[-1]


def attr(node, name, default=""):
    return next((v for k, v in node.attrib.items() if local(k) == name), default)


def child(node, name):
    return next((e for e in node if local(e.tag) == name), None)


def children(node, container, name):
    parent = child(node, container)
    return [] if parent is None else [e for e in parent if local(e.tag) == name]


def decode(value, prefix):
    value = value[len(prefix):] if value.startswith(prefix) else value
    value = value.replace("__SBML_DOT__", ".")
    return re.sub(r"__(\d+)__", lambda m: chr(int(m[1])), value)


def encode(value, prefix):
    return prefix + re.sub(r"[^A-Za-z0-9_]", lambda m: f"__{ord(m[0])}__", value)


def notes(node):
    section = child(node, "notes")
    if section is None:
        return {}
    result = {}
    for item in section.iter():
        if local(item.tag) == "p":
            text = "".join(item.itertext()).strip()
            if ":" in text:
                key, value = text.split(":", 1)
                result[key.strip()] = value.strip()
    return result


def annotations(node):
    section = child(node, "annotation")
    result = {}
    if section is not None:
        for item in section.iter():
            resource = attr(item, "resource")
            match = re.search(r"identifiers\.org/(?:([^/:]+)[:/])(.+)", resource)
            if match:
                result.setdefault(match[1], []).append(match[2])
    return result


def gpr(node, genes):
    name = local(node.tag)
    if name == "geneProductRef":
        raw = attr(node, "geneProduct")
        if raw not in genes:
            raise CobraSBMLError(f"Unknown gene product {raw}")
        return genes[raw]
    if name in {"and", "or"}:
        return "(" + f" {name} ".join(gpr(e, genes) for e in node) + ")"
    raise CobraSBMLError(f"Unsupported gene association: {name}")


def _number(value, label):
    try:
        result = float(value)
    except (ValueError, TypeError) as exc:
        raise CobraSBMLError(f"Invalid numeric {label}: {value}") from exc
    if math.isnan(result):
        raise CobraSBMLError(f"NaN is not a valid {label}")
    return result


def read_sbml_model(filename, **kwargs):
    from cobra import Model, Reaction, Metabolite
    text = filename.read() if hasattr(filename, "read") else Path(filename).read_text(encoding="utf-8-sig")
    if isinstance(text, bytes):
        text = text.decode("utf-8-sig")
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise CobraSBMLError("XML document types/entities are not supported in browser mode.")
    root = ET.fromstring(text)
    if local(root.tag) != "sbml" or root.get("level") not in {"2", "3"}:
        raise CobraSBMLError("Browser mode supports SBML Level 2/3 steady-state models.")
    for key, value in root.attrib.items():
        if local(key) == "required" and value.lower() == "true" and "fbc" not in key:
            raise CobraSBMLError(f"Required SBML package is unsupported: {key}")
    node = child(root, "model")
    if node is None:
        raise CobraSBMLError("SBML contains no model.")
    for item in node.iter():
        if local(item.tag) in {"assignmentRule", "rateRule", "algebraicRule", "initialAssignment", "event", "stoichiometryMath"}:
            raise CobraSBMLError(f"Dynamic SBML construct {local(item.tag)} is unsupported; use a steady-state FBC model.")
    model = Model(node.get("id") or "browser_model")
    model.name = node.get("name") or ""
    model.notes, model.annotation = notes(node), annotations(node)
    model.compartments = {c.get("id"): c.get("name", c.get("id")) for c in children(node, "listOfCompartments", "compartment")}
    params = {p.get("id"): _number(p.get("value"), "parameter") for p in children(node, "listOfParameters", "parameter")}
    metabolites = {}
    for s in children(node, "listOfSpecies", "species"):
        raw_id = s.get("id")
        if not raw_id or raw_id in metabolites:
            raise CobraSBMLError("Species IDs must be present and unique.")
        if attr(s, "conversionFactor"):
            raise CobraSBMLError("Species conversion factors are unsupported in browser mode.")
        m = Metabolite(decode(raw_id, "M_"), name=s.get("name", ""), compartment=s.get("compartment", ""))
        formula, charge = attr(s, "chemicalFormula"), attr(s, "charge")
        m.notes, m.annotation = notes(s), annotations(s)
        m.formula = formula or m.notes.get("FORMULA") or None
        if charge:
            m.charge = int(charge)
        metabolites[raw_id] = m
    model.add_metabolites(list(metabolites.values()))
    gene_nodes = children(node, "listOfGeneProducts", "geneProduct")
    genes = {attr(g, "id"): decode(attr(g, "label") or attr(g, "id"), "G_") for g in gene_nodes}
    boundary = {s.get("id") for s in children(node, "listOfSpecies", "species") if s.get("boundaryCondition", "false").lower() == "true"}
    legacy_objective, raw_reactions = {}, {}
    for r in children(node, "listOfReactions", "reaction"):
        raw_id = r.get("id")
        if not raw_id or raw_id in raw_reactions:
            raise CobraSBMLError("Reaction IDs must be present and unique.")
        kinetic = child(r, "kineticLaw")
        local_params = {}
        if kinetic is not None:
            for p in kinetic.iter():
                if local(p.tag) in {"parameter", "localParameter"}:
                    local_params[p.get("id")] = _number(p.get("value"), "kinetic parameter")
        lower, upper = attr(r, "lowerFluxBound"), attr(r, "upperFluxBound")
        try:
            lb = params[lower] if lower else local_params.get("LOWER_BOUND", -1000 if r.get("reversible", "true").lower() == "true" else 0)
            ub = params[upper] if upper else local_params.get("UPPER_BOUND", 1000)
        except KeyError as exc:
            raise CobraSBMLError(f"Unknown flux bound parameter: {exc}") from exc
        rxn = Reaction(decode(raw_id, "R_"), name=r.get("name", ""), lower_bound=lb, upper_bound=ub)
        rxn.notes, rxn.annotation = notes(r), annotations(r)
        rxn.subsystem = rxn.notes.get("SUBSYSTEM", "")
        stoich = {}
        for container, sign in [("listOfReactants", -1), ("listOfProducts", 1)]:
            for s in children(r, container, "speciesReference"):
                raw = s.get("species")
                if raw not in metabolites:
                    raise CobraSBMLError(f"Unknown species {raw} in reaction {raw_id}")
                coefficient = sign * _number(s.get("stoichiometry", "1"), "stoichiometry")
                if not math.isfinite(coefficient) or abs(coefficient) > 1e12:
                    raise CobraSBMLError("Stoichiometry must be finite and within supported numeric bounds.")
                m = metabolites[raw]
                stoich[m] = stoich.get(m, 0) + coefficient
        rxn.add_metabolites(stoich)
        association = child(r, "geneProductAssociation")
        if association is not None and len(association):
            rxn.gene_reaction_rule = gpr(association[0], genes)
        else:
            rxn.gene_reaction_rule = rxn.notes.get("GENE_ASSOCIATION", "")
        legacy_objective[rxn] = local_params.get("OBJECTIVE_COEFFICIENT", 0)
        raw_reactions[raw_id] = rxn
    model.add_reactions(list(raw_reactions.values()))
    for bound in children(node, "listOfFluxBounds", "fluxBound"):
        raw = attr(bound, "reaction")
        if raw not in raw_reactions:
            raise CobraSBMLError(f"Unknown FBC v1 bound reaction {raw}")
        rxn = raw_reactions[raw]
        value = _number(attr(bound, "value"), "flux bound")
        operation = attr(bound, "operation")
        if operation in {"greaterEqual", "greater"}:
            if operation == "greater":
                raise CobraSBMLError("Strict flux inequalities are unsupported.")
            rxn.lower_bound = value
        elif operation in {"lessEqual", "less"}:
            if operation == "less":
                raise CobraSBMLError("Strict flux inequalities are unsupported.")
            rxn.upper_bound = value
        elif operation == "equal":
            rxn.bounds = (value, value)
        else:
            raise CobraSBMLError(f"Unsupported flux-bound operation {operation}")
    for raw in boundary:
        m = metabolites[raw]
        identifier = "EX_" + m.id
        if identifier not in model.reactions:
            model.add_boundary(m, type="exchange", reaction_id=identifier, lb=-1000, ub=1000)
    objectives = child(node, "listOfObjectives")
    selected = None
    if objectives is not None:
        active = attr(objectives, "activeObjective")
        if active:
            selected = next((o for o in objectives if attr(o, "id") == active), None)
            if selected is None:
                raise CobraSBMLError(f"Active objective {active} was not found.")
        elif len(objectives) == 1:
            selected = objectives[0]
        elif len(objectives):
            raise CobraSBMLError("Multiple objectives require an activeObjective.")
    objective = legacy_objective
    if selected is not None:
        objective = {}
        for term in selected.iter():
            if local(term.tag) != "fluxObjective":
                continue
            raw = attr(term, "reaction")
            if raw not in raw_reactions:
                raise CobraSBMLError(f"Unknown objective reaction {raw}")
            rxn = raw_reactions[raw]
            objective[rxn] = objective.get(rxn, 0) + _number(attr(term, "coefficient", "1"), "objective coefficient")
    if not any(objective.values()):
        raise CobraSBMLError("No nonzero objective was found. Add an FBC objective before running FBA.")
    model.objective = objective
    model.objective_direction = "min" if selected is not None and attr(selected, "type") == "minimize" else "max"
    for g in gene_nodes:
        identifier = genes[attr(g, "id")]
        if identifier in model.genes:
            gene = model.genes.get_by_id(identifier)
            gene.name, gene.annotation = attr(g, "name"), annotations(g)
    return model


def _metadata(node, item):
    if item.notes:
        section = ET.SubElement(node, f"{{{CORE}}}notes")
        body = ET.SubElement(section, "{http://www.w3.org/1999/xhtml}body")
        for key, value in item.notes.items():
            ET.SubElement(body, "{http://www.w3.org/1999/xhtml}p").text = f"{key}: {value}"
    if item.annotation:
        identifier = attr(node, "id")
        node.set("metaid", identifier)
        section = ET.SubElement(node, f"{{{CORE}}}annotation")
        desc = ET.SubElement(ET.SubElement(section, f"{{{RDF}}}RDF"), f"{{{RDF}}}Description", {f"{{{RDF}}}about": "#" + identifier})
        bag = ET.SubElement(ET.SubElement(desc, f"{{{BQB}}}is"), f"{{{RDF}}}Bag")
        for key, values in item.annotation.items():
            for value in values if isinstance(values, list) else [values]:
                ET.SubElement(bag, f"{{{RDF}}}li", {f"{{{RDF}}}resource": f"https://identifiers.org/{key}/{value}"})


def write_sbml_model(model, filename, **kwargs):
    """Write Core L3 FBC v2, preserving bounds, objective, GPR, notes and IDs."""
    import ast
    from cobra.util.solver import linear_reaction_coefficients
    ET.register_namespace("", CORE)
    ET.register_namespace("fbc", FBC)
    root = ET.Element(f"{{{CORE}}}sbml", {"level": "3", "version": "1", f"{{{FBC}}}required": "false"})
    node = ET.SubElement(root, f"{{{CORE}}}model", {"id": encode(model.id or "model", ""), "name": model.name or "", f"{{{FBC}}}strict": "true"})
    _metadata(node, model)
    compartments = ET.SubElement(node, f"{{{CORE}}}listOfCompartments")
    for key, name in model.compartments.items():
        ET.SubElement(compartments, f"{{{CORE}}}compartment", {"id": key, "name": name or key, "constant": "true"})
    species = ET.SubElement(node, f"{{{CORE}}}listOfSpecies")
    for m in model.metabolites:
        attrs = {"id": encode(m.id, "M_"), "name": m.name or "", "compartment": m.compartment or "c", "boundaryCondition": "false", "constant": "false", "hasOnlySubstanceUnits": "false"}
        if m.formula:
            attrs[f"{{{FBC}}}chemicalFormula"] = m.formula
        if m.charge is not None:
            attrs[f"{{{FBC}}}charge"] = str(int(m.charge))
        _metadata(ET.SubElement(species, f"{{{CORE}}}species", attrs), m)
    params = ET.SubElement(node, f"{{{CORE}}}listOfParameters")
    reactions = ET.SubElement(node, f"{{{CORE}}}listOfReactions")
    def association(parent, term):
        if isinstance(term, ast.Name):
            ET.SubElement(parent, f"{{{FBC}}}geneProductRef", {f"{{{FBC}}}geneProduct": encode(term.id, "G_")})
        elif isinstance(term, ast.BoolOp):
            sub = ET.SubElement(parent, f"{{{FBC}}}" + ("and" if isinstance(term.op, ast.And) else "or"))
            for value in term.values:
                association(sub, value)
        else:
            raise CobraSBMLError("Unsupported gene rule during SBML export.")
    for i, rxn in enumerate(model.reactions):
        for label, value in [("lb", rxn.lower_bound), ("ub", rxn.upper_bound)]:
            ET.SubElement(params, f"{{{CORE}}}parameter", {"id": f"{label}_{i}", "value": str(value), "constant": "true"})
        r = ET.SubElement(reactions, f"{{{CORE}}}reaction", {"id": encode(rxn.id, "R_"), "name": rxn.name or "", "reversible": str(rxn.lower_bound < 0).lower(), "fast": "false", f"{{{FBC}}}lowerFluxBound": f"lb_{i}", f"{{{FBC}}}upperFluxBound": f"ub_{i}"})
        if rxn.subsystem:
            rxn.notes = {**rxn.notes, "SUBSYSTEM": rxn.subsystem}
        _metadata(r, rxn)
        for container, sign in [("listOfReactants", -1), ("listOfProducts", 1)]:
            values = [(m, n) for m, n in rxn.metabolites.items() if n * sign > 0]
            if values:
                section = ET.SubElement(r, f"{{{CORE}}}{container}")
                for m, n in values:
                    ET.SubElement(section, f"{{{CORE}}}speciesReference", {"species": encode(m.id, "M_"), "stoichiometry": str(abs(n)), "constant": "true"})
        if rxn.gpr.body is not None:
            association(ET.SubElement(r, f"{{{FBC}}}geneProductAssociation"), rxn.gpr.body)
    objectives = ET.SubElement(node, f"{{{FBC}}}listOfObjectives", {f"{{{FBC}}}activeObjective": "obj"})
    objective = ET.SubElement(objectives, f"{{{FBC}}}objective", {f"{{{FBC}}}id": "obj", f"{{{FBC}}}type": "minimize" if model.objective_direction == "min" else "maximize"})
    terms = ET.SubElement(objective, f"{{{FBC}}}listOfFluxObjectives")
    for rxn, value in linear_reaction_coefficients(model).items():
        ET.SubElement(terms, f"{{{FBC}}}fluxObjective", {f"{{{FBC}}}reaction": encode(rxn.id, "R_"), f"{{{FBC}}}coefficient": str(value)})
    if model.genes:
        genes = ET.SubElement(node, f"{{{FBC}}}listOfGeneProducts")
        for gene in model.genes:
            _metadata(ET.SubElement(genes, f"{{{FBC}}}geneProduct", {f"{{{FBC}}}id": encode(gene.id, "G_"), f"{{{FBC}}}label": gene.id, f"{{{FBC}}}name": gene.name or ""}), gene)
    output = ET.tostring(root, encoding="unicode", xml_declaration=True)
    if hasattr(filename, "write"):
        filename.write(output)
    else:
        Path(filename).write_text(output, encoding="utf-8")


def validate_sbml_model(*args, **kwargs):
    raise CobraSBMLError("Full libSBML validation is unavailable in browser mode. Use a server with libSBML for standards validation.")


def install():
    """Supply COBRA's SBML IO module before importing COBRA in WebAssembly."""
    module = types.ModuleType("cobra.io.sbml")
    for name in ("read_sbml_model", "write_sbml_model", "validate_sbml_model", "CobraSBMLError"):
        setattr(module, name, globals()[name])
    sys.modules["cobra.io.sbml"] = module
    # COBRA imports its optional network model loader eagerly, and that module
    # also imports libSBML. Uploaded/bundled models use the adapter above; do not
    # pretend a browser has a working native repository downloader.
    remote = types.ModuleType("cobra.io.web.load")
    def unavailable(*args, **kwargs):
        raise CobraSBMLError("Automatic COBRA repository downloads are unavailable in browser mode. Upload an SBML model or use a bundled example.")
    remote.load_model = unavailable
    sys.modules["cobra.io.web.load"] = remote
