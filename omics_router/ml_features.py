"""Build normalized feature tables for ML + GEM hybrid analyses."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .constraints import read_csv_records, write_csv, write_json


@dataclass(slots=True)
class MlFeatureMatrixResult:
    """Summary returned after building ML feature tables."""

    status: str
    output_dir: str
    message: str
    files: dict[str, str]
    summary_rows: list[dict[str, object]]
    feature_rows: list[dict[str, object]]


def run_ml_feature_matrix(
    package_dir: str | Path,
    output_dir: str | Path | None = None,
) -> MlFeatureMatrixResult:
    """Build condition-level ML feature tables from normalized omics and GEM outputs."""

    package = Path(package_dir)
    output = Path(output_dir) if output_dir else package / "ml_results"
    output.mkdir(parents=True, exist_ok=True)

    feature_rows = build_ml_feature_rows(package)
    matrix_rows = build_feature_matrix(feature_rows)
    summary_rows = summarize_feature_rows(feature_rows, matrix_rows)
    files = {
        "feature_long": str(output / "ml_feature_long.csv"),
        "feature_matrix": str(output / "ml_feature_matrix.csv"),
        "feature_summary": str(output / "ml_feature_summary.csv"),
        "manifest": str(output / "ml_feature_manifest.json"),
    }
    write_csv(files["feature_long"], feature_rows)
    write_csv(files["feature_matrix"], matrix_rows)
    write_csv(files["feature_summary"], summary_rows)
    status = "completed" if feature_rows else "completed_no_features"
    message = (
        f"Built ML feature matrix with {len(matrix_rows)} condition rows and "
        f"{_feature_count(feature_rows)} feature columns."
    )
    if not feature_rows:
        message = "No ML-compatible feature rows were found yet."
    write_json(
        files["manifest"],
        {
            "schema_version": "0.1.0",
            "status": status,
            "message": message,
            "package_dir": str(package),
            "condition_count": len(matrix_rows),
            "feature_count": _feature_count(feature_rows),
            "feature_row_count": len(feature_rows),
            "files": files,
        },
    )
    return MlFeatureMatrixResult(status, str(output), message, files, summary_rows, feature_rows)


def build_ml_feature_rows(package_dir: str | Path) -> list[dict[str, object]]:
    """Collect long-form ML features from available custom pipeline outputs."""

    package = Path(package_dir)
    rows: list[dict[str, object]] = []
    rows.extend(
        _features_from_table(
            package / "generated_constraints" / "gene_expression_evidence.csv",
            source="transcriptomics_gene",
            feature_prefix="tx_gene",
            entity_column="model_gene_id",
            value_column="value",
        )
    )
    rows.extend(
        _features_from_table(
            package / "generated_constraints" / "reaction_expression_evidence.csv",
            source="transcriptomics_reaction",
            feature_prefix="tx_reaction",
            entity_column="reaction_id",
            value_column="reaction_score",
        )
    )
    rows.extend(
        _features_from_table(
            package / "generated_constraints" / "relative_protein_evidence.csv",
            source="relative_proteomics_gene",
            feature_prefix="prot_gene",
            entity_column="model_gene_id",
            value_column="log2_fold_change",
        )
    )
    rows.extend(
        _features_from_table(
            package / "generated_constraints" / "relative_protein_reaction_evidence.csv",
            source="relative_proteomics_reaction",
            feature_prefix="prot_reaction",
            entity_column="reaction_id",
            value_column="reaction_score",
        )
    )
    rows.extend(
        _features_from_table(
            package / "cobra_results" / "predicted_fluxes.csv",
            source="fba_flux",
            feature_prefix="fba_flux",
            entity_column="reaction_id",
            value_column="predicted_flux",
        )
    )
    rows.extend(
        _features_from_table(
            package / "cobra_results" / "pfba_fluxes.csv",
            source="pfba_flux",
            feature_prefix="pfba_flux",
            entity_column="reaction_id",
            value_column="predicted_flux",
        )
    )
    rows.extend(
        _features_from_table(
            package / "transcriptomics_flux_results" / "eflux_fluxes.csv",
            source="eflux_flux",
            feature_prefix="eflux_flux",
            entity_column="reaction_id",
            value_column="predicted_flux",
        )
    )
    rows.extend(_phenotype_features(package / "generated_constraints" / "flux_validation_targets.csv"))
    return rows


def build_feature_matrix(feature_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Pivot long-form feature rows into condition x feature matrix."""

    conditions = sorted({str(row.get("condition", "")) for row in feature_rows if row.get("condition")})
    features = sorted({str(row.get("feature_id", "")) for row in feature_rows if row.get("feature_id")})
    values: dict[tuple[str, str], float] = {}
    for row in feature_rows:
        condition = str(row.get("condition", ""))
        feature_id = str(row.get("feature_id", ""))
        value = _to_float(row.get("value"))
        if not condition or not feature_id or value is None:
            continue
        values[(condition, feature_id)] = value

    matrix_rows: list[dict[str, object]] = []
    for condition in conditions:
        matrix_row: dict[str, object] = {"condition": condition}
        for feature_id in features:
            matrix_row[feature_id] = values.get((condition, feature_id), "")
        matrix_rows.append(matrix_row)
    return matrix_rows


def summarize_feature_rows(
    feature_rows: list[dict[str, object]],
    matrix_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Summarize feature coverage by source."""

    grouped: dict[str, list[dict[str, object]]] = {}
    for row in feature_rows:
        grouped.setdefault(str(row.get("source", "unknown")), []).append(row)
    summary = [
        {
            "source": source,
            "condition_count": len({str(row.get("condition", "")) for row in rows if row.get("condition")}),
            "feature_count": len({str(row.get("feature_id", "")) for row in rows if row.get("feature_id")}),
            "value_count": len(rows),
            "status": "available",
        }
        for source, rows in sorted(grouped.items())
    ]
    summary.insert(
        0,
        {
            "source": "ALL",
            "condition_count": len(matrix_rows),
            "feature_count": _feature_count(feature_rows),
            "value_count": len(feature_rows),
            "status": "available" if feature_rows else "missing",
        },
    )
    return summary


def _features_from_table(
    path: Path,
    *,
    source: str,
    feature_prefix: str,
    entity_column: str,
    value_column: str,
) -> list[dict[str, object]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    rows: list[dict[str, object]] = []
    for record in read_csv_records(path):
        condition = record.get("condition") or record.get("sample") or "default"
        entity_id = record.get(entity_column) or record.get("cobra_reaction_id") or record.get("reaction_id") or ""
        value = _to_float(record.get(value_column))
        if not entity_id or value is None:
            continue
        rows.append(
            {
                "condition": condition,
                "feature_id": f"{feature_prefix}::{entity_id}",
                "feature_type": feature_prefix,
                "entity_id": entity_id,
                "source": source,
                "value": value,
                "status": record.get("status", ""),
                "evidence": record.get("evidence", ""),
                "note": record.get("note", ""),
            }
        )
    return rows


def _phenotype_features(path: Path) -> list[dict[str, object]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    rows: list[dict[str, object]] = []
    for record in read_csv_records(path):
        condition = record.get("condition") or record.get("sample") or "default"
        reaction_id = record.get("model_reaction_id") or record.get("reaction_id") or ""
        value = _to_float(record.get("measured_flux") or record.get("flux"))
        if not reaction_id or value is None:
            continue
        rows.append(
            {
                "condition": condition,
                "feature_id": f"phenotype_flux::{reaction_id}",
                "feature_type": "phenotype_flux",
                "entity_id": reaction_id,
                "source": "fluxomics_phenotype",
                "value": value,
                "status": record.get("status", ""),
                "evidence": "",
                "note": record.get("note", ""),
            }
        )
    return rows


def _feature_count(feature_rows: list[dict[str, object]]) -> int:
    return len({str(row.get("feature_id", "")) for row in feature_rows if row.get("feature_id")})


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None
