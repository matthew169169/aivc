"""Local UniProt / GPR semantic checks for staged GEM models.

This v1 checker is intentionally offline and reproducible. It combines
annotations already present in SBML with optional user-uploaded annotation,
alias, or ML-prior tables, then reports coverage and review flags without
modifying the model.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constraints import read_package_input_map
from .constraints import (
    CORE_NS,
    FBC_NS,
    parse_sbml_gpr_rules,
    parse_sbml_index,
    read_csv_records,
    write_csv,
    write_json,
)
from .uniprot_cache import (
    enrichment_summary_row,
    load_or_fetch_uniprot_records,
)


CHECK_VERSION = "0.1.0"
ANNOTATION_ROLES = {"uniprot_annotation", "id_alias_table", "ml_priors"}
EC_RE = re.compile(r"\b\d+\.(?:\d+|-)\.(?:\d+|-)\.(?:\d+|-)\b")
UNIPROT_CONTEXT_RE = re.compile(
    r"(?:uniprot(?:kb)?|uniprotkb|identifiers\.org/uniprot)[/:#_\s-]+([A-Z0-9]{5,12}(?:-\d+)?)",
    re.IGNORECASE,
)
UNIPROT_ACCESSION_RE = re.compile(
    r"\b(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9][A-Z][A-Z0-9]{2}[0-9](?:-\d+)?)\b"
)


@dataclass(slots=True)
class UniProtModelCheckResult:
    """Result object consumed by the custom pipeline runner."""

    status: str
    message: str
    files: dict[str, str]
    manifest: dict[str, object]


def run_uniprot_model_check(
    model_path: str | Path,
    output_dir: str | Path,
    package_dir: str | Path | None = None,
    enable_uniprot_rest: bool = False,
    uniprot_cache_dir: str | Path | None = None,
    uniprot_fetcher: Any | None = None,
) -> UniProtModelCheckResult:
    """Run the local UniProt/GPR model check and write CSV/JSON outputs."""

    model = Path(model_path)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    files = output_file_map(output)

    if model.suffix.lower() not in {".xml", ".sbml"}:
        return write_skipped_outputs(
            model,
            files,
            status="skipped_non_sbml",
            message="UniProt/GPR model check v1 only parses SBML/XML models.",
        )

    model_index = parse_sbml_index(model)
    gpr_rules = parse_sbml_gpr_rules(model)
    sbml_annotations = parse_sbml_annotations(model)
    user_annotations = load_user_annotations(package_dir, model_index) if package_dir else empty_annotation_bundle()

    gene_annotations = merge_annotation_maps(sbml_annotations["genes"], user_annotations["genes"])
    reaction_annotations = merge_annotation_maps(sbml_annotations["reactions"], user_annotations["reactions"])
    cache_dir = Path(uniprot_cache_dir) if uniprot_cache_dir else default_uniprot_cache_dir(output, package_dir)
    accession_ids = collect_uniprot_accessions(gene_annotations, reaction_annotations)
    uniprot_records, enrichment_records = load_or_fetch_uniprot_records(
        accession_ids,
        cache_dir=cache_dir,
        enable_network=enable_uniprot_rest,
        fetcher=uniprot_fetcher,
    )
    enrich_annotations_from_uniprot_records(gene_annotations, uniprot_records)
    enrich_annotations_from_uniprot_records(reaction_annotations, uniprot_records)
    enrichment_summary = enrichment_summary_row(enrichment_records, cache_dir=cache_dir, enable_network=enable_uniprot_rest)

    gene_rows = build_gene_coverage_rows(model_index.genes, gpr_rules, gene_annotations)
    gpr_rows = build_gpr_consistency_flags(gpr_rules, gene_annotations)
    reaction_rows = build_reaction_annotation_flags(gpr_rules, reaction_annotations, gene_annotations)
    summary_rows = [
        build_summary_row(
            model_id=model_index.model_id,
            gene_rows=gene_rows,
            gpr_rows=gpr_rows,
            reaction_rows=reaction_rows,
            source_files=user_annotations["source_files"],
            enrichment_summary=enrichment_summary,
        )
    ]

    write_csv(files["uniprot_gene_coverage"], gene_rows)
    write_csv(files["gpr_consistency_flags"], gpr_rows)
    write_csv(files["reaction_annotation_flags"], reaction_rows)
    write_csv(files["uniprot_enrichment_summary"], [enrichment_summary])
    write_csv(files["uniprot_enrichment_records"], enrichment_records)
    write_csv(files["uniprot_model_check_summary"], summary_rows)

    summary = summary_rows[0]
    manifest = {
        "schema_version": CHECK_VERSION,
        "status": summary["status"],
        "message": summary["guidance"],
        "model_path": str(model),
        "network_access": "enabled" if enable_uniprot_rest else "disabled",
        "uniprot_cache_dir": str(cache_dir),
        "source_files": user_annotations["source_files"],
        "counts": {
            "gene_rows": len(gene_rows),
            "gpr_rows": len(gpr_rows),
            "reaction_rows": len(reaction_rows),
            "high_risk_flag_count": summary["high_risk_flag_count"],
            "inconclusive_reaction_count": summary["inconclusive_reaction_count"],
            "uniprot_requested_accessions": enrichment_summary["requested_accession_count"],
            "uniprot_cache_hits": enrichment_summary["cache_hit_count"],
            "uniprot_fetched": enrichment_summary["fetched_count"],
        },
        "files": files,
    }
    write_json(files["uniprot_model_check_manifest"], manifest)
    message = (
        f"UniProt/GPR model check completed: genes={summary['gene_count']}, "
        f"reactions={summary['reaction_count']}, high_risk={summary['high_risk_flag_count']}."
    )
    return UniProtModelCheckResult(status="completed", message=message, files=files, manifest=manifest)


def output_file_map(output: Path) -> dict[str, str]:
    return {
        "uniprot_gene_coverage": str(output / "uniprot_gene_coverage.csv"),
        "gpr_consistency_flags": str(output / "gpr_consistency_flags.csv"),
        "reaction_annotation_flags": str(output / "reaction_annotation_flags.csv"),
        "uniprot_enrichment_summary": str(output / "uniprot_enrichment_summary.csv"),
        "uniprot_enrichment_records": str(output / "uniprot_enrichment_records.csv"),
        "uniprot_model_check_summary": str(output / "uniprot_model_check_summary.csv"),
        "uniprot_model_check_manifest": str(output / "uniprot_model_check_manifest.json"),
    }


def write_skipped_outputs(model: Path, files: dict[str, str], status: str, message: str) -> UniProtModelCheckResult:
    """Write stable empty outputs when v1 cannot parse the model format."""

    write_csv(files["uniprot_gene_coverage"], [])
    write_csv(files["gpr_consistency_flags"], [])
    write_csv(files["reaction_annotation_flags"], [])
    write_csv(files["uniprot_enrichment_summary"], [])
    write_csv(files["uniprot_enrichment_records"], [])
    summary_rows = [
        {
            "model_id": model.stem,
            "status": status,
            "gene_count": 0,
            "gene_uniprot_count": 0,
            "gene_uniprot_coverage_fraction": None,
            "reaction_count": 0,
            "reaction_with_gpr_count": 0,
            "reaction_with_gpr_fraction": None,
            "missing_gpr_count": 0,
            "ec_mismatch_count": 0,
            "annotation_missing_count": 0,
            "high_risk_flag_count": 0,
            "inconclusive_reaction_count": 0,
            "user_annotation_source_count": 0,
            "uniprot_enrichment_status": "skipped",
            "uniprot_cache_hit_count": 0,
            "uniprot_fetched_count": 0,
            "uniprot_reviewed_count": 0,
            "guidance": message,
        }
    ]
    write_csv(files["uniprot_model_check_summary"], summary_rows)
    manifest = {
        "schema_version": CHECK_VERSION,
        "status": status,
        "message": message,
        "model_path": str(model),
        "network_access": "disabled",
        "source_files": [],
        "counts": {
            "gene_rows": 0,
            "gpr_rows": 0,
            "reaction_rows": 0,
            "high_risk_flag_count": 0,
            "inconclusive_reaction_count": 0,
        },
        "files": files,
    }
    write_json(files["uniprot_model_check_manifest"], manifest)
    return UniProtModelCheckResult(status="completed", message=message, files=files, manifest=manifest)


def parse_sbml_annotations(model_path: str | Path) -> dict[str, dict[str, dict[str, set[str]]]]:
    """Extract local gene/reaction annotation snippets from SBML XML."""

    tree = ET.parse(model_path)
    root = tree.getroot()
    genes: dict[str, dict[str, set[str]]] = {}
    reactions: dict[str, dict[str, set[str]]] = {}

    for gene in root.findall(f".//{FBC_NS}geneProduct"):
        gene_id = (
            gene.attrib.get(f"{FBC_NS}id")
            or gene.attrib.get("id")
            or gene.attrib.get(f"{FBC_NS}label")
            or gene.attrib.get("label")
            or gene.attrib.get(f"{FBC_NS}name")
            or gene.attrib.get("name")
            or ""
        )
        if not gene_id:
            continue
        extracted = extract_annotation_values(gene)
        gene_name = gene.attrib.get(f"{FBC_NS}name") or gene.attrib.get("name") or ""
        if gene_name:
            extracted["functions"].add(gene_name)
        if has_annotation_values(extracted):
            _merge_annotation(genes, gene_id, extracted, source="sbml_gene_product")

    for reaction in root.findall(f".//{CORE_NS}reaction"):
        reaction_id = reaction.attrib.get("id", "")
        if not reaction_id:
            continue
        extracted = extract_annotation_values(reaction)
        if has_annotation_values(extracted):
            _merge_annotation(reactions, reaction_id, extracted, source="sbml_reaction")

    return {"genes": genes, "reactions": reactions}


def extract_annotation_values(element: ET.Element) -> dict[str, set[str]]:
    """Extract UniProt-like accessions and EC numbers from one XML element."""

    xml_text = ET.tostring(element, encoding="unicode")
    uniprot_ids = set()
    for match in UNIPROT_CONTEXT_RE.finditer(xml_text):
        uniprot_ids.add(match.group(1).upper())
    ec_numbers = {match.group(0) for match in EC_RE.finditer(xml_text)}
    return {
        "uniprot_ids": uniprot_ids,
        "ec_numbers": ec_numbers,
        "functions": set(),
        "sources": set(),
        "notes": set(),
    }


def load_user_annotations(
    package_dir: str | Path | None,
    model_index: Any,
) -> dict[str, Any]:
    """Read optional annotation, alias, and ML-prior tables from a run package."""

    if package_dir is None:
        return empty_annotation_bundle()
    package = Path(package_dir)
    bundle = empty_annotation_bundle()
    seen_paths: set[Path] = set()
    for role, path in iter_package_annotation_tables(package):
        if path in seen_paths or not path.exists() or path.stat().st_size == 0:
            continue
        seen_paths.add(path)
        bundle["source_files"].append({"role": role, "path": str(path)})
        rows = read_csv_records(path)
        if role == "uniprot_annotation":
            consume_uniprot_annotation_rows(rows, bundle, model_index)
        elif role == "id_alias_table":
            consume_alias_rows(rows, bundle, model_index)
        elif role == "ml_priors":
            consume_ml_prior_rows(rows, bundle, model_index)
    return bundle


def iter_package_annotation_tables(package: Path) -> list[tuple[str, Path]]:
    """Return annotation-capable staged tables from normalized and raw maps."""

    entries: list[tuple[str, Path]] = []
    for map_path in (
        package / "normalized_inputs" / "normalized_input_map.csv",
        package / "input_file_map.csv",
    ):
        if not map_path.exists() or map_path.stat().st_size == 0:
            continue
        for row in read_package_input_map(package, normalized=map_path.parent.name == "normalized_inputs"):
            role = row.get("role", "")
            if role not in ANNOTATION_ROLES:
                continue
            path_text = row.get("path", "")
            path = Path(path_text) if path_text else Path("")
            if (not path_text or not path.exists()) and row.get("relative_path"):
                path = package / str(row.get("relative_path"))
            if path_text or row.get("relative_path"):
                entries.append((role, path))
    return entries


def consume_uniprot_annotation_rows(rows: list[dict[str, str]], bundle: dict[str, Any], model_index: Any) -> None:
    """Map flexible user annotation rows onto model genes and reactions."""

    for row in rows:
        target_type = _norm(row.get("target_type") or row.get("entity_type"))
        gene_id = _first_value(row, ["model_gene_id", "gene_id", "gene", "model_id"])
        reaction_id = _first_value(row, ["model_reaction_id", "reaction_id", "reaction"])
        target_id = _first_value(row, ["model_target_id", "target_id"])
        values = _row_annotation_values(row)
        if target_type == "gene" and target_id and not gene_id:
            gene_id = target_id
        if target_type == "reaction" and target_id and not reaction_id:
            reaction_id = target_id

        if gene_id:
            model_gene, status = model_index.resolve_gene(gene_id)
            if status in {"mapped", "not_checked", ""} or model_gene in model_index.genes:
                _merge_annotation(bundle["genes"], model_gene, values, source="uniprot_annotation")
        if reaction_id:
            model_reaction, status = model_index.resolve_reaction(reaction_id)
            if status in {"mapped", "not_checked", ""} or model_reaction in model_index.reactions:
                _merge_annotation(bundle["reactions"], model_reaction, values, source="uniprot_annotation")


def consume_alias_rows(rows: list[dict[str, str]], bundle: dict[str, Any], model_index: Any) -> None:
    """Use ID alias tables as local annotation hints when possible."""

    for row in rows:
        target_type = _norm(row.get("target_type") or row.get("entity_type"))
        model_id = _first_value(row, ["model_id", "model_target_id", "target_id"])
        if not model_id:
            continue
        source_type = _norm(row.get("source_type") or row.get("database") or row.get("db"))
        source_id = _first_value(row, ["source_id", "external_id", "alias_id"])
        values = _row_annotation_values(row)
        if "uniprot" in source_type or _looks_like_uniprot(source_id):
            values["uniprot_ids"].add(source_id.upper())
        if source_type in {"ec", "ec_number", "enzyme_commission"}:
            values["ec_numbers"].update(extract_ec_numbers(source_id))

        if target_type == "reaction":
            model_reaction, status = model_index.resolve_reaction(model_id)
            if status in {"mapped", "not_checked", ""} or model_reaction in model_index.reactions:
                _merge_annotation(bundle["reactions"], model_reaction, values, source="id_alias_table")
            continue

        model_gene, status = model_index.resolve_gene(model_id)
        if status in {"mapped", "not_checked", ""} or model_gene in model_index.genes:
            _merge_annotation(bundle["genes"], model_gene, values, source="id_alias_table")


def consume_ml_prior_rows(rows: list[dict[str, str]], bundle: dict[str, Any], model_index: Any) -> None:
    """Record ML priors as auxiliary local evidence, not authoritative annotation."""

    for row in rows:
        target_type = _norm(row.get("target_type") or row.get("entity_type"))
        target_id = _first_value(row, ["model_target_id", "target_id", "model_id"])
        if not target_id:
            continue
        values = _row_annotation_values(row)
        values["notes"].add("ml_prior_available")
        if target_type == "reaction":
            model_reaction, status = model_index.resolve_reaction(target_id)
            if status in {"mapped", "not_checked", ""} or model_reaction in model_index.reactions:
                _merge_annotation(bundle["reactions"], model_reaction, values, source="ml_priors")
            continue
        if target_type == "gene":
            model_gene, status = model_index.resolve_gene(target_id)
            if status in {"mapped", "not_checked", ""} or model_gene in model_index.genes:
                _merge_annotation(bundle["genes"], model_gene, values, source="ml_priors")


def build_gene_coverage_rows(
    model_genes: set[str],
    gpr_rules: dict[str, Any],
    gene_annotations: dict[str, dict[str, set[str]]],
) -> list[dict[str, object]]:
    """Build per-gene annotation coverage rows."""

    gene_ids = sorted(set(model_genes) | {gene for rule in gpr_rules.values() for gene in rule.genes})
    rows: list[dict[str, object]] = []
    for gene_id in gene_ids:
        ann = gene_annotations.get(gene_id, empty_annotation())
        uniprot_ids = sorted(ann["uniprot_ids"])
        ec_numbers = sorted(ann["ec_numbers"])
        functions = sorted(ann["functions"])
        protein_names = sorted(ann["protein_names"])
        reviewed_statuses = sorted(ann["reviewed_statuses"])
        sources = sorted(ann["sources"])
        has_annotation = bool(uniprot_ids or ec_numbers or functions or sources)
        if uniprot_ids:
            status = "annotated"
        elif has_annotation:
            status = "annotation_without_uniprot"
        else:
            status = "annotation_missing"
        rows.append(
            {
                "gene_id": gene_id,
                "has_uniprot": bool(uniprot_ids),
                "uniprot_id": ";".join(uniprot_ids),
                "has_ec": bool(ec_numbers),
                "ec_numbers": ";".join(ec_numbers),
                "has_function": bool(functions),
                "function_text": ";".join(functions[:3]),
                "protein_name": ";".join(protein_names[:3]),
                "reviewed_status": ";".join(reviewed_statuses),
                "annotation_sources": ";".join(sources),
                "status": status,
                "note": ";".join(sorted(ann["notes"])),
            }
        )
    return rows


def build_gpr_consistency_flags(
    gpr_rules: dict[str, Any],
    gene_annotations: dict[str, dict[str, set[str]]],
) -> list[dict[str, object]]:
    """Flag reaction-level GPR and gene annotation coverage."""

    rows: list[dict[str, object]] = []
    for reaction_id, rule in sorted(gpr_rules.items()):
        gene_count = len(rule.genes)
        annotated_genes = [gene for gene in rule.genes if gene_annotations.get(gene, {}).get("uniprot_ids")]
        annotated_count = len(annotated_genes)
        coverage = annotated_count / gene_count if gene_count else None
        if gene_count == 0:
            flag, severity, status = "missing_gpr", "high", "review"
        elif annotated_count == 0:
            flag, severity, status = "gpr_without_uniprot_annotation", "medium", "inconclusive"
        elif annotated_count < gene_count:
            flag, severity, status = "partial_uniprot_annotation", "low", "usable_with_caution"
        else:
            flag, severity, status = "gpr_annotation_available", "info", "usable"
        uniprot_ids = sorted(
            {
                uid
                for gene in rule.genes
                for uid in gene_annotations.get(gene, empty_annotation())["uniprot_ids"]
            }
        )
        rows.append(
            {
                "reaction_id": reaction_id,
                "reaction_name": rule.name,
                "has_gpr": gene_count > 0,
                "gene_count": gene_count,
                "annotated_gene_count": annotated_count,
                "uniprot_coverage_fraction": coverage,
                "flag": flag,
                "severity": severity,
                "status": status,
                "genes": ";".join(rule.genes),
                "annotated_genes": ";".join(annotated_genes),
                "uniprot_ids": ";".join(uniprot_ids),
                "gpr_rule": rule.rule_text,
            }
        )
    return rows


def build_reaction_annotation_flags(
    gpr_rules: dict[str, Any],
    reaction_annotations: dict[str, dict[str, set[str]]],
    gene_annotations: dict[str, dict[str, set[str]]],
) -> list[dict[str, object]]:
    """Flag reaction EC/UniProt annotation coverage and obvious conflicts."""

    rows: list[dict[str, object]] = []
    for reaction_id, rule in sorted(gpr_rules.items()):
        reaction_ann = reaction_annotations.get(reaction_id, empty_annotation())
        reaction_ec = set(reaction_ann["ec_numbers"])
        reaction_uniprot = set(reaction_ann["uniprot_ids"])
        gene_ec = {
            ec_number
            for gene in rule.genes
            for ec_number in gene_annotations.get(gene, empty_annotation())["ec_numbers"]
        }
        gene_uniprot = {
            uid
            for gene in rule.genes
            for uid in gene_annotations.get(gene, empty_annotation())["uniprot_ids"]
        }
        gene_reviewed_statuses = {
            status
            for gene in rule.genes
            for status in gene_annotations.get(gene, empty_annotation())["reviewed_statuses"]
        }
        gene_protein_names = {
            name
            for gene in rule.genes
            for name in gene_annotations.get(gene, empty_annotation())["protein_names"]
        }
        overlap = sorted(reaction_ec & gene_ec)
        has_gpr = bool(rule.genes)
        has_reaction_annotation = bool(reaction_ec or reaction_uniprot or reaction_ann["sources"])

        if not has_gpr:
            flag, severity, status = "missing_gpr", "high", "review"
            note = "Reaction has no GPR, so gene-level annotation cannot support it."
        elif reaction_ec and gene_ec and not overlap:
            flag, severity, status = "ec_mismatch_review", "high", "review"
            note = "Reaction-level EC numbers do not overlap gene-level EC annotations."
        elif reaction_ec and gene_ec and overlap:
            flag, severity, status = "ec_consistent", "info", "usable"
            note = "Reaction and gene EC annotations overlap."
        elif not has_reaction_annotation and not gene_ec and not gene_uniprot:
            flag, severity, status = "annotation_missing", "medium", "inconclusive"
            note = "No local reaction or gene annotation was available."
        elif not reaction_ec and gene_ec:
            flag, severity, status = "reaction_ec_missing", "low", "usable_with_caution"
            note = "Gene-level EC annotation exists, but reaction-level EC is missing locally."
        elif reaction_ec and not gene_ec:
            flag, severity, status = "gene_ec_missing", "low", "usable_with_caution"
            note = "Reaction-level EC annotation exists, but gene-level EC is missing locally."
        else:
            flag, severity, status = "inconclusive", "info", "inconclusive"
            note = "Some local annotation exists, but not enough to evaluate EC consistency."

        rows.append(
            {
                "reaction_id": reaction_id,
                "reaction_name": rule.name,
                "has_gpr": has_gpr,
                "gene_count": len(rule.genes),
                "has_reaction_annotation": has_reaction_annotation,
                "reaction_uniprot_ids": ";".join(sorted(reaction_uniprot)),
                "gene_uniprot_ids": ";".join(sorted(gene_uniprot)),
                "gene_reviewed_status": ";".join(sorted(gene_reviewed_statuses)),
                "gene_protein_names": ";".join(sorted(gene_protein_names)[:3]),
                "reaction_ec_numbers": ";".join(sorted(reaction_ec)),
                "gene_ec_numbers": ";".join(sorted(gene_ec)),
                "ec_overlap": ";".join(overlap),
                "flag": flag,
                "severity": severity,
                "status": status,
                "note": note,
            }
        )
    return rows


def build_summary_row(
    model_id: str,
    gene_rows: list[dict[str, object]],
    gpr_rows: list[dict[str, object]],
    reaction_rows: list[dict[str, object]],
    source_files: list[dict[str, str]],
    enrichment_summary: dict[str, object] | None = None,
) -> dict[str, object]:
    """Summarize the UniProt/GPR model check for UI and reports."""

    gene_count = len(gene_rows)
    reaction_count = len(gpr_rows)
    gene_uniprot_count = sum(1 for row in gene_rows if _truthy(row.get("has_uniprot")))
    gpr_reaction_count = sum(1 for row in gpr_rows if _truthy(row.get("has_gpr")))
    missing_gpr_count = sum(1 for row in gpr_rows if row.get("flag") == "missing_gpr")
    ec_mismatch_count = sum(1 for row in reaction_rows if row.get("flag") == "ec_mismatch_review")
    annotation_missing_count = sum(1 for row in reaction_rows if row.get("flag") == "annotation_missing")
    high_risk_count = sum(1 for row in reaction_rows + gpr_rows if row.get("severity") == "high")
    inconclusive_count = sum(1 for row in reaction_rows if row.get("status") == "inconclusive")
    enrichment_summary = enrichment_summary or {}

    if high_risk_count:
        status = "completed_with_review_flags"
        guidance = "Review high-risk GPR or EC mismatch flags before trusting downstream constraints."
    elif gene_count and gene_uniprot_count == 0:
        status = "completed_inconclusive"
        guidance = "No local UniProt gene coverage was found; treat semantic QC as inconclusive."
    else:
        status = "completed"
        guidance = "Local UniProt/GPR annotation coverage is available for downstream review."

    return {
        "model_id": model_id,
        "status": status,
        "gene_count": gene_count,
        "gene_uniprot_count": gene_uniprot_count,
        "gene_uniprot_coverage_fraction": gene_uniprot_count / gene_count if gene_count else None,
        "reaction_count": reaction_count,
        "reaction_with_gpr_count": gpr_reaction_count,
        "reaction_with_gpr_fraction": gpr_reaction_count / reaction_count if reaction_count else None,
        "missing_gpr_count": missing_gpr_count,
        "ec_mismatch_count": ec_mismatch_count,
        "annotation_missing_count": annotation_missing_count,
        "high_risk_flag_count": high_risk_count,
        "inconclusive_reaction_count": inconclusive_count,
        "user_annotation_source_count": len(source_files),
        "uniprot_enrichment_status": enrichment_summary.get("status", ""),
        "uniprot_cache_hit_count": enrichment_summary.get("cache_hit_count", 0),
        "uniprot_fetched_count": enrichment_summary.get("fetched_count", 0),
        "uniprot_reviewed_count": enrichment_summary.get("reviewed_count", 0),
        "guidance": guidance,
    }


def default_uniprot_cache_dir(output_dir: Path, package_dir: str | Path | None) -> Path:
    """Choose a package-local cache path when possible."""

    if package_dir:
        return Path(package_dir) / "uniprot_cache"
    return output_dir / "uniprot_cache"


def collect_uniprot_accessions(
    *annotation_maps: dict[str, dict[str, set[str]]],
) -> list[str]:
    """Return sorted accessions present in local annotations."""

    return sorted(
        {
            uid
            for mapping in annotation_maps
            for annotation in mapping.values()
            for uid in annotation.get("uniprot_ids", set())
            if uid
        }
    )


def enrich_annotations_from_uniprot_records(
    annotations: dict[str, dict[str, set[str]]],
    records: dict[str, dict[str, Any]],
) -> None:
    """Merge cached or fetched UniProt metadata into annotation maps."""

    for annotation in annotations.values():
        for accession in list(annotation.get("uniprot_ids", set())):
            record = records.get(str(accession).upper())
            if not record:
                continue
            annotation["ec_numbers"].update(str(value) for value in record.get("ec_numbers", []) if value)
            protein_name = str(record.get("protein_name", "")).strip()
            if protein_name:
                annotation["functions"].add(protein_name)
                annotation["protein_names"].add(protein_name)
            reviewed_status = str(record.get("reviewed_status", "")).strip()
            if reviewed_status:
                annotation["reviewed_statuses"].add(reviewed_status)
            organism = str(record.get("organism", "")).strip()
            if organism:
                annotation["organisms"].add(organism)
            source_status = str(record.get("_source_status", ""))
            annotation["sources"].add("uniprot_rest" if source_status == "fetched" else "uniprot_cache")


def merge_annotation_maps(
    *maps: dict[str, dict[str, set[str]]],
) -> dict[str, dict[str, set[str]]]:
    """Merge annotation maps while preserving set-valued fields."""

    merged: dict[str, dict[str, set[str]]] = {}
    for mapping in maps:
        for entity_id, values in mapping.items():
            _merge_annotation(merged, entity_id, values, source="")
    return merged


def _row_annotation_values(row: dict[str, str]) -> dict[str, set[str]]:
    values = empty_annotation()
    for column in ["uniprot_id", "uniprot", "uniprot_accession", "protein_id", "accession"]:
        values["uniprot_ids"].update(extract_uniprot_ids(row.get(column, "")))
    for column in ["ec_number", "ec", "ec_code", "enzyme_commission"]:
        values["ec_numbers"].update(extract_ec_numbers(row.get(column, "")))
    for column in ["protein_name", "function", "gene_name", "product", "description", "name"]:
        value = str(row.get(column, "")).strip()
        if value:
            values["functions"].add(value)
    note = str(row.get("note", "")).strip()
    if note:
        values["notes"].add(note)
    return values


def extract_uniprot_ids(value: object) -> set[str]:
    text = str(value or "")
    ids = {match.group(1).upper() for match in UNIPROT_CONTEXT_RE.finditer(text)}
    ids.update(match.group(0).upper() for match in UNIPROT_ACCESSION_RE.finditer(text))
    return ids


def extract_ec_numbers(value: object) -> set[str]:
    return {match.group(0) for match in EC_RE.finditer(str(value or ""))}


def empty_annotation_bundle() -> dict[str, Any]:
    return {"genes": {}, "reactions": {}, "source_files": []}


def empty_annotation() -> dict[str, set[str]]:
    return {
        "uniprot_ids": set(),
        "ec_numbers": set(),
        "functions": set(),
        "protein_names": set(),
        "reviewed_statuses": set(),
        "organisms": set(),
        "sources": set(),
        "notes": set(),
    }


def has_annotation_values(values: dict[str, set[str]]) -> bool:
    return any(
        values.get(key)
        for key in (
            "uniprot_ids",
            "ec_numbers",
            "functions",
            "protein_names",
            "reviewed_statuses",
            "organisms",
            "sources",
            "notes",
        )
    )


def _merge_annotation(
    target: dict[str, dict[str, set[str]]],
    entity_id: str,
    values: dict[str, set[str]],
    source: str,
) -> None:
    if not entity_id:
        return
    current = target.setdefault(entity_id, empty_annotation())
    for key in ("uniprot_ids", "ec_numbers", "functions", "protein_names", "reviewed_statuses", "organisms", "sources", "notes"):
        current[key].update(values.get(key, set()))
    if source:
        current["sources"].add(source)


def _first_value(row: dict[str, str], columns: list[str]) -> str:
    for column in columns:
        value = str(row.get(column, "")).strip()
        if value:
            return value
    return ""


def _looks_like_uniprot(value: object) -> bool:
    return bool(UNIPROT_ACCESSION_RE.search(str(value or "")))


def _norm(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}
