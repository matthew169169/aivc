"""Bridge GECKO/ecFactory outputs back into production-design reports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .constraints import read_csv_records, write_csv, write_json


GECKO_TARGET_RESULT_FILES = [
    "gecko_production_targets.csv",
    "gecko_production_target_ranking.csv",
    "gecko_production_envelope.csv",
    "ecfactory_product_targets.csv",
    "ecfactory_production_targets.csv",
]
GECKO_DESIGN_RESULT_FILES = [
    "gecko_design_targets.csv",
    "gecko_gene_targets.csv",
    "gecko_reaction_targets.csv",
    "ecfactory_targets.csv",
    "ecfactory_gene_targets.csv",
    "ecfactory_reaction_targets.csv",
]
GECKO_PRODUCT_TARGET_COLUMNS = [
    "condition",
    "product_reaction_id",
    "product_name",
    "gecko_max_product_flux",
    "status",
    "source",
    "note",
]
GECKO_REACTION_DESIGN_COLUMNS = [
    "condition",
    "product_reaction_id",
    "candidate_reaction_id",
    "recommended_action",
    "score",
    "source",
    "note",
]
GECKO_GENE_DESIGN_COLUMNS = [
    "condition",
    "product_reaction_id",
    "gene_id",
    "recommended_action",
    "score",
    "source",
    "note",
]
GECKO_RESULT_IMPORT_TYPES = {
    "product_targets": {
        "filename": "gecko_production_targets.csv",
        "columns": GECKO_PRODUCT_TARGET_COLUMNS,
        "label": "GECKO/ecFactory product targets",
    },
    "reaction_design_targets": {
        "filename": "gecko_design_targets.csv",
        "columns": GECKO_REACTION_DESIGN_COLUMNS,
        "label": "GECKO/ecFactory reaction design targets",
    },
    "gene_design_targets": {
        "filename": "gecko_gene_targets.csv",
        "columns": GECKO_GENE_DESIGN_COLUMNS,
        "label": "GECKO/ecFactory gene design targets",
    },
}


@dataclass(slots=True)
class ProductionGeckoBridgeResult:
    """Summary returned after comparing COBRApy and GECKO/ecFactory production outputs."""

    status: str
    output_dir: str
    message: str
    files: dict[str, str]


def gecko_result_template_columns(result_type: str) -> list[str]:
    """Return the expected columns for a GECKO/ecFactory result import type."""

    spec = GECKO_RESULT_IMPORT_TYPES.get(result_type)
    if spec is None:
        raise ValueError(f"Unknown GECKO/ecFactory result type: {result_type}")
    return list(spec["columns"])


def gecko_result_template_rows(result_type: str) -> list[dict[str, object]]:
    """Return a one-row example template for user-facing downloads."""

    if result_type == "product_targets":
        return [
            {
                "condition": "default",
                "product_reaction_id": "R_EX_ac_e",
                "product_name": "acetate",
                "gecko_max_product_flux": 1.0,
                "status": "optimal",
                "source": "GECKO",
                "note": "example row; replace with your result",
            }
        ]
    if result_type == "reaction_design_targets":
        return [
            {
                "condition": "default",
                "product_reaction_id": "R_EX_ac_e",
                "candidate_reaction_id": "R_PFK",
                "recommended_action": "OE",
                "score": 0.9,
                "source": "ecFactory",
                "note": "example row; replace with your result",
            }
        ]
    if result_type == "gene_design_targets":
        return [
            {
                "condition": "default",
                "product_reaction_id": "R_EX_ac_e",
                "gene_id": "G_b0001",
                "recommended_action": "OE",
                "score": 0.9,
                "source": "ecFactory",
                "note": "example row; replace with your result",
            }
        ]
    gecko_result_template_columns(result_type)
    return []


def write_gecko_result_table_to_package(
    package_dir: str | Path,
    result_type: str,
    rows: list[dict[str, object]],
) -> Path:
    """Save an uploaded GECKO/ecFactory result table where the comparison bridge can find it."""

    spec = GECKO_RESULT_IMPORT_TYPES.get(result_type)
    if spec is None:
        raise ValueError(f"Unknown GECKO/ecFactory result type: {result_type}")
    package = Path(package_dir)
    output_dir = package / "gecko_run_results"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / str(spec["filename"])
    columns = list(spec["columns"])
    normalized_rows = normalize_gecko_import_rows(rows, columns)
    write_csv(output_path, normalized_rows)
    write_csv(
        output_dir / "gecko_external_run_summary.csv",
        [
            {
                "status": "imported",
                "message": f"Imported {spec['label']} table.",
                "package_status": "external_results_imported",
                "matlab_path": "",
                "gecko_home": "",
                "gecko_home_exists": "",
                "return_code": "",
                "timeout_seconds": "",
            }
        ],
    )
    write_json(
        output_dir / "gecko_result_import_manifest.json",
        {
            "schema_version": "0.1.0",
            "status": "imported",
            "result_type": result_type,
            "label": spec["label"],
            "row_count": len(normalized_rows),
            "file": str(output_path),
            "recognized_by_bridge": output_path.name in {*GECKO_TARGET_RESULT_FILES, *GECKO_DESIGN_RESULT_FILES},
        },
    )
    return output_path


def normalize_gecko_import_rows(
    rows: list[dict[str, object]],
    columns: list[str],
) -> list[dict[str, object]]:
    """Align uploaded result rows to the bridge template columns."""

    normalized = []
    for row in rows:
        if not any(str(value).strip() for value in row.values()):
            continue
        normalized.append({column: row.get(column, "") for column in columns})
    return normalized


def run_production_gecko_bridge(
    production_results_dir: str | Path,
    gecko_package_dir: str | Path,
    gecko_run_dir: str | Path,
    output_dir: str | Path | None = None,
) -> ProductionGeckoBridgeResult:
    """Compare COBRApy-only production suggestions with GECKO/ecFactory outputs when available."""

    production_dir = Path(production_results_dir)
    gecko_package = Path(gecko_package_dir)
    gecko_run = Path(gecko_run_dir)
    output = Path(output_dir) if output_dir else production_dir
    output.mkdir(parents=True, exist_ok=True)
    files = production_gecko_bridge_files(output)

    cobra_targets = _read_optional(production_dir / "production_target_ranking.csv")
    cobra_design = _read_optional(production_dir / "production_design_targets.csv")
    cobra_genes = _read_optional(production_dir / "production_gene_targets.csv")
    gecko_export = _read_optional(gecko_package / "gecko_export_summary.csv")
    gecko_run_summary = _read_optional(gecko_run / "gecko_external_run_summary.csv")
    gecko_targets = load_named_result_tables(gecko_run, GECKO_TARGET_RESULT_FILES)
    gecko_design = load_named_result_tables(gecko_run, GECKO_DESIGN_RESULT_FILES)

    target_rows = compare_product_targets(cobra_targets, gecko_targets)
    design_rows = compare_design_targets(cobra_design, cobra_genes, gecko_design)
    summary_rows = [
        build_bridge_summary(
            cobra_targets=cobra_targets,
            cobra_design=cobra_design,
            cobra_genes=cobra_genes,
            gecko_export=gecko_export,
            gecko_run_summary=gecko_run_summary,
            gecko_targets=gecko_targets,
            gecko_design=gecko_design,
            target_rows=target_rows,
            design_rows=design_rows,
        )
    ]

    write_csv(files["summary"], summary_rows)
    write_csv(files["target_comparison"], target_rows)
    write_csv(files["design_comparison"], design_rows)
    write_json(
        files["manifest"],
        {
            "schema_version": "0.1.0",
            "status": summary_rows[0]["status"],
            "production_results_dir": str(production_dir),
            "gecko_package_dir": str(gecko_package),
            "gecko_run_dir": str(gecko_run),
            "files": files,
            "input_counts": {
                "cobra_targets": len(cobra_targets),
                "cobra_design": len(cobra_design),
                "cobra_genes": len(cobra_genes),
                "gecko_export": len(gecko_export),
                "gecko_run_summary": len(gecko_run_summary),
                "gecko_targets": len(gecko_targets),
                "gecko_design": len(gecko_design),
            },
        },
    )
    return ProductionGeckoBridgeResult(
        status="completed",
        output_dir=str(output),
        message=str(summary_rows[0]["guidance"]),
        files=files,
    )


def compare_product_targets(
    cobra_rows: list[dict[str, str]],
    gecko_rows: list[dict[str, str]],
) -> list[dict[str, object]]:
    """Compare product-level COBRApy ranking against enzyme-constrained target rows."""

    gecko_index = index_product_rows(gecko_rows)
    output: list[dict[str, object]] = []
    seen_keys: set[tuple[str, str]] = set()
    for cobra in cobra_rows:
        key = product_key(cobra)
        seen_keys.add(key)
        gecko = gecko_index.get(key) or gecko_index.get(("", key[1])) or {}
        cobra_high = _safe_float(cobra.get("max_product_flux_at_high_growth"))
        gecko_flux = gecko_product_flux(gecko)
        label = product_comparison_label(cobra_high, gecko_flux, bool(gecko))
        output.append(
            {
                "condition": cobra.get("condition", ""),
                "product_reaction_id": cobra.get("product_reaction_id", ""),
                "product_name": cobra.get("product_name", ""),
                "cobra_growth_coupling_label": cobra.get("growth_coupling_label", ""),
                "cobra_max_product_flux_at_high_growth": cobra_high,
                "gecko_max_product_flux": gecko_flux,
                "gecko_solve_status": gecko.get("status") or gecko.get("solve_status") or gecko.get("gecko_status", ""),
                "flux_ratio_gecko_to_cobra": flux_ratio(gecko_flux, cobra_high),
                "comparison_label": label,
                "guidance": product_comparison_guidance(label),
                "gecko_source_file": gecko.get("source_file", ""),
            }
        )
    for gecko in gecko_rows:
        key = product_key(gecko)
        if key in seen_keys:
            continue
        output.append(
            {
                "condition": gecko.get("condition", ""),
                "product_reaction_id": product_reaction_id(gecko),
                "product_name": gecko.get("product_name", ""),
                "cobra_growth_coupling_label": "",
                "cobra_max_product_flux_at_high_growth": "",
                "gecko_max_product_flux": gecko_product_flux(gecko),
                "gecko_solve_status": gecko.get("status") or gecko.get("solve_status") or gecko.get("gecko_status", ""),
                "flux_ratio_gecko_to_cobra": "",
                "comparison_label": "gecko_only_target",
                "guidance": "GECKO/ecFactory reports this product target, but COBRApy production ranking did not include it.",
                "gecko_source_file": gecko.get("source_file", ""),
            }
        )
    return output


def compare_design_targets(
    cobra_design_rows: list[dict[str, str]],
    cobra_gene_rows: list[dict[str, str]],
    gecko_rows: list[dict[str, str]],
) -> list[dict[str, object]]:
    """Compare reaction/gene production-design targets against GECKO/ecFactory target rows."""

    cobra_rows = [
        normalize_cobra_design_row(row, "reaction") for row in cobra_design_rows
    ] + [
        normalize_cobra_design_row(row, "gene") for row in cobra_gene_rows
    ]
    gecko_targets = [normalize_gecko_design_row(row) for row in gecko_rows]
    gecko_index = index_design_rows(gecko_targets)
    output: list[dict[str, object]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for cobra in cobra_rows:
        key = design_key(cobra)
        seen.add(key)
        gecko = gecko_index.get(key) or gecko_index.get((cobra["target_level"], cobra["candidate_id_norm"], "", "")) or {}
        label = design_comparison_label(cobra, gecko)
        output.append(
            {
                "condition": cobra["condition"],
                "product_reaction_id": cobra["product_reaction_id"],
                "target_level": cobra["target_level"],
                "candidate_id": cobra["candidate_id"],
                "cobra_action": cobra["action"],
                "gecko_action": gecko.get("action", ""),
                "cobra_score": cobra["score"],
                "gecko_score": gecko.get("score", ""),
                "comparison_label": label,
                "guidance": design_comparison_guidance(label),
                "gecko_source_file": gecko.get("source_file", ""),
            }
        )
    for gecko in gecko_targets:
        key = design_key(gecko)
        if key in seen:
            continue
        output.append(
            {
                "condition": gecko["condition"],
                "product_reaction_id": gecko["product_reaction_id"],
                "target_level": gecko["target_level"],
                "candidate_id": gecko["candidate_id"],
                "cobra_action": "",
                "gecko_action": gecko["action"],
                "cobra_score": "",
                "gecko_score": gecko["score"],
                "comparison_label": "gecko_only_design_target",
                "guidance": "GECKO/ecFactory suggests this target, but the COBRApy-only design table did not rank it.",
                "gecko_source_file": gecko.get("source_file", ""),
            }
        )
    return output


def build_bridge_summary(
    *,
    cobra_targets: list[dict[str, str]],
    cobra_design: list[dict[str, str]],
    cobra_genes: list[dict[str, str]],
    gecko_export: list[dict[str, str]],
    gecko_run_summary: list[dict[str, str]],
    gecko_targets: list[dict[str, str]],
    gecko_design: list[dict[str, str]],
    target_rows: list[dict[str, object]],
    design_rows: list[dict[str, object]],
) -> dict[str, object]:
    gecko_external_status = gecko_run_summary[0].get("status", "") if gecko_run_summary else "not_available"
    status = bridge_status(cobra_targets, cobra_design, cobra_genes, gecko_export, gecko_external_status, gecko_targets, gecko_design)
    supported = sum(1 for row in design_rows if row.get("comparison_label") == "supported_by_gecko_or_ecfactory")
    conflicts = sum(1 for row in design_rows if row.get("comparison_label") == "action_conflict_review")
    cobra_only = sum(1 for row in design_rows if str(row.get("comparison_label", "")).startswith("cobra_only"))
    return {
        "status": status,
        "gecko_export_status": "available" if gecko_export else "missing",
        "gecko_external_status": gecko_external_status,
        "cobra_product_count": len(cobra_targets),
        "cobra_design_count": len(cobra_design),
        "cobra_gene_target_count": len(cobra_genes),
        "gecko_target_result_count": len(gecko_targets),
        "gecko_design_result_count": len(gecko_design),
        "supported_design_count": supported,
        "conflict_design_count": conflicts,
        "cobra_only_design_count": cobra_only,
        "guidance": bridge_guidance(status, gecko_external_status, supported, conflicts),
    }


def production_gecko_bridge_files(output: Path) -> dict[str, str]:
    return {
        "summary": str(output / "production_gecko_comparison_summary.csv"),
        "target_comparison": str(output / "production_gecko_target_comparison.csv"),
        "design_comparison": str(output / "production_gecko_design_comparison.csv"),
        "manifest": str(output / "production_gecko_bridge_manifest.json"),
    }


def load_named_result_tables(root: Path, filenames: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for name in filenames:
        path = root / name
        if not path.exists() or path.stat().st_size == 0:
            continue
        for row in read_csv_records(path):
            rows.append({**row, "source_file": name})
    return rows


def index_product_rows(rows: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    index = {}
    for row in rows:
        index.setdefault(product_key(row), row)
    return index


def product_key(row: dict[str, object]) -> tuple[str, str]:
    return (str(row.get("condition", "")), normalize_id(product_reaction_id(row)))


def product_reaction_id(row: dict[str, object]) -> str:
    return _first_value(
        row,
        [
            "product_reaction_id",
            "model_product_reaction_id",
            "product_exchange_reaction",
            "reaction_id",
            "target_id",
        ],
    )


def gecko_product_flux(row: dict[str, object]) -> float | None:
    return _safe_float(
        _first_value(
            row,
            [
                "gecko_max_product_flux",
                "enzyme_constrained_max_product_flux",
                "max_product_flux_at_high_growth",
                "max_product_flux",
                "product_flux",
            ],
        )
    )


def product_comparison_label(cobra_flux: float | None, gecko_flux: float | None, has_gecko: bool) -> str:
    if not has_gecko:
        return "cobra_only_no_gecko_target_result"
    if gecko_flux is None:
        return "gecko_result_without_flux"
    if gecko_flux > 1e-9:
        return "enzyme_constrained_supported"
    if cobra_flux is not None and cobra_flux > 1e-9:
        return "enzyme_constraint_blocks_cobra_target"
    return "enzyme_constrained_no_product_flux"


def product_comparison_guidance(label: str) -> str:
    return {
        "cobra_only_no_gecko_target_result": "No enzyme-constrained product result was found; treat production ranking as COBRApy-only.",
        "gecko_result_without_flux": "GECKO/ecFactory target row exists but lacks a flux value; inspect the external result table.",
        "enzyme_constrained_supported": "Product flux remains feasible in enzyme-constrained output.",
        "enzyme_constraint_blocks_cobra_target": "COBRApy predicts product potential, but enzyme constraints appear to block it.",
        "enzyme_constrained_no_product_flux": "Both production and enzyme-constrained outputs report no product flux.",
    }.get(label, "Inspect target comparison manually.")


def normalize_cobra_design_row(row: dict[str, str], level: str) -> dict[str, object]:
    candidate_id = row.get("candidate_reaction_id", "") if level == "reaction" else row.get("gene_id", "")
    return {
        "condition": row.get("condition", ""),
        "product_reaction_id": row.get("product_reaction_id", ""),
        "target_level": level,
        "candidate_id": candidate_id,
        "candidate_id_norm": normalize_id(candidate_id),
        "action": row.get("recommended_action", ""),
        "score": row.get("intervention_score", "") if level == "reaction" else row.get("gene_target_score", ""),
    }


def normalize_gecko_design_row(row: dict[str, str]) -> dict[str, object]:
    gene_id = _first_value(row, ["gene_id", "model_gene_id", "target_gene_id"])
    reaction_id = _first_value(row, ["candidate_reaction_id", "reaction_id", "model_reaction_id", "target_reaction_id"])
    level = "gene" if gene_id else "reaction"
    candidate_id = gene_id or reaction_id or _first_value(row, ["target_id", "candidate_id"])
    action = _first_value(row, ["recommended_action", "action", "intervention", "target_action"])
    return {
        "condition": row.get("condition", ""),
        "product_reaction_id": _first_value(row, ["product_reaction_id", "model_product_reaction_id", "product_exchange_reaction"]),
        "target_level": level,
        "candidate_id": candidate_id,
        "candidate_id_norm": normalize_id(candidate_id),
        "action": normalize_action(action),
        "score": _first_value(row, ["score", "target_score", "intervention_score", "gene_target_score"]),
        "source_file": row.get("source_file", ""),
    }


def index_design_rows(rows: list[dict[str, object]]) -> dict[tuple[str, str, str, str], dict[str, object]]:
    index = {}
    for row in rows:
        index.setdefault(design_key(row), row)
    return index


def design_key(row: dict[str, object]) -> tuple[str, str, str, str]:
    return (
        str(row.get("target_level", "")),
        str(row.get("candidate_id_norm", "")),
        str(row.get("condition", "")),
        normalize_id(str(row.get("product_reaction_id", ""))),
    )


def design_comparison_label(cobra: dict[str, object], gecko: dict[str, object]) -> str:
    if not gecko:
        return "cobra_only_no_gecko_design_result"
    cobra_action = normalize_action(str(cobra.get("action", "")))
    gecko_action = normalize_action(str(gecko.get("action", "")))
    if not gecko_action or not cobra_action or cobra_action == gecko_action:
        return "supported_by_gecko_or_ecfactory"
    return "action_conflict_review"


def design_comparison_guidance(label: str) -> str:
    return {
        "cobra_only_no_gecko_design_result": "No matching enzyme-constrained design target was found yet.",
        "supported_by_gecko_or_ecfactory": "COBRApy-only target is supported by GECKO/ecFactory result rows.",
        "action_conflict_review": "COBRApy and GECKO/ecFactory suggest different actions; review enzyme constraints and GPR mapping.",
        "gecko_only_design_target": "External enzyme-constrained workflow suggests an additional target not ranked by COBRApy-only analysis.",
    }.get(label, "Inspect design comparison manually.")


def bridge_status(
    cobra_targets: list[dict[str, str]],
    cobra_design: list[dict[str, str]],
    cobra_genes: list[dict[str, str]],
    gecko_export: list[dict[str, str]],
    gecko_external_status: str,
    gecko_targets: list[dict[str, str]],
    gecko_design: list[dict[str, str]],
) -> str:
    if not any([cobra_targets, cobra_design, cobra_genes]):
        return "no_cobra_production_results"
    if gecko_targets or gecko_design:
        return "gecko_comparison_available"
    if gecko_external_status in {"completed", "failed"}:
        return "gecko_run_without_supported_result_tables"
    if gecko_external_status in {"dry_run", "skipped"} or gecko_export:
        return "gecko_staged_no_results"
    return "gecko_not_available"


def bridge_guidance(status: str, gecko_external_status: str, supported: int, conflicts: int) -> str:
    if status == "gecko_comparison_available":
        if conflicts:
            return f"GECKO/ecFactory comparison is available: supported={supported}, conflicts={conflicts}; inspect conflicting actions."
        return f"GECKO/ecFactory comparison is available: supported={supported}, conflicts=0."
    if status == "gecko_run_without_supported_result_tables":
        return "GECKO external run status is available, but no recognized production target/design result table was found."
    if status == "gecko_staged_no_results":
        return f"GECKO package/run is staged ({gecko_external_status}), but no enzyme-constrained production results are available yet."
    if status == "no_cobra_production_results":
        return "No COBRApy production design outputs were found for comparison."
    return "No GECKO/ecFactory outputs were found; production recommendations remain COBRApy-only."


def flux_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or abs(denominator) <= 1e-12:
        return None
    return numerator / denominator


def normalize_action(action: str) -> str:
    text = str(action or "").strip().upper()
    aliases = {
        "OVEREXPRESSION": "OE",
        "UP": "OE",
        "OVER_EXPRESS": "OE",
        "KNOCKDOWN": "KD",
        "DOWN": "KD",
        "KNOCKOUT": "KO",
        "DELETE": "KO",
        "DELETION": "KO",
    }
    return aliases.get(text, text)


def normalize_id(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("R_"):
        text = text[2:]
    return text.lower()


def _read_optional(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    return read_csv_records(path)


def _first_value(row: dict[str, object], keys: list[str]) -> str:
    for key in keys:
        value = str(row.get(key, "")).strip()
        if value:
            return value
    return ""


def _safe_float(value: object) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
