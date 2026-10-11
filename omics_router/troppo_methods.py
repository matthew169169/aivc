"""Prepare method-specific inputs for multiple TROPPO reconstruction algorithms."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .context import protected_reactions_from_outputs
from .constraints import parse_sbml_index, read_csv_records, write_csv, write_json
from .evidence_modes import EVIDENCE_MODES, evidence_mode_paths
from .troppo_runner import troppo_available


TROPPO_METHODS = ("fastcore", "imat", "gimme", "corda")
METHOD_STATUS = {
    "fastcore": "connected_runner",
    "imat": "input_ready_execution_pending",
    "gimme": "input_ready_execution_pending",
    "corda": "input_ready_execution_pending",
}


@dataclass(slots=True)
class TroppoMethodPreparationResult:
    """Summary returned after writing multi-method TROPPO input tables."""

    status: str
    output_dir: str
    message: str
    files: dict[str, str]


def run_troppo_method_preparation(
    model_path: str | Path,
    constraints_dir: str | Path,
    output_dir: str | Path,
    evidence_mode: str = "consensus",
) -> TroppoMethodPreparationResult:
    """Prepare method-specific inputs for FASTcore, iMAT, GIMME, and CORDA."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "summary": str(output / "troppo_method_input_summary.csv"),
        "reaction_inputs": str(output / "troppo_method_reaction_inputs.csv"),
        "run_matrix": str(output / "troppo_method_run_matrix.csv"),
        "manifest": str(output / "troppo_method_manifest.json"),
    }
    tables = build_troppo_method_tables(model_path, constraints_dir, evidence_mode)
    write_csv(files["summary"], tables["summary"])
    write_csv(files["reaction_inputs"], tables["reaction_inputs"])
    write_csv(files["run_matrix"], tables["run_matrix"])
    write_json(
        files["manifest"],
        {
            "status": "completed",
            "model_path": str(model_path),
            "constraints_dir": str(constraints_dir),
            "evidence_mode": evidence_mode,
            "method_count": len(TROPPO_METHODS),
            "reaction_input_rows": len(tables["reaction_inputs"]),
            "troppo_available": troppo_available(),
            "files": files,
        },
    )
    return TroppoMethodPreparationResult(
        status="completed",
        output_dir=str(output),
        message=f"Prepared TROPPO inputs for {len(TROPPO_METHODS)} methods using {evidence_mode} evidence.",
        files=files,
    )


def build_troppo_method_tables(
    model_path: str | Path,
    constraints_dir: str | Path,
    evidence_mode: str = "consensus",
) -> dict[str, list[dict[str, object]]]:
    """Return multi-method input, summary, and run-matrix tables."""

    paths = evidence_mode_paths(constraints_dir, evidence_mode)
    reaction_rows = read_csv_records(paths.reaction_evidence)
    exchange_rows = read_csv_records(Path(constraints_dir) / "exchange_bounds.csv")
    model_index = parse_sbml_index(model_path) if Path(model_path).exists() else None
    protected = protected_reactions_from_outputs(
        model_index.objective_reactions if model_index else [],
        exchange_rows,
    )
    reaction_inputs = build_method_reaction_inputs(reaction_rows, protected)
    summary = summarize_method_inputs(reaction_inputs)
    run_matrix = build_method_run_matrix(evidence_mode=evidence_mode)
    return {"reaction_inputs": reaction_inputs, "summary": summary, "run_matrix": run_matrix}


def build_method_reaction_inputs(
    reaction_rows: list[dict[str, str]],
    protected_reactions: set[str] | None = None,
) -> list[dict[str, object]]:
    """Expand reaction evidence rows into method-specific input rows."""

    protected = {_normalize_reaction_id(reaction) for reaction in (protected_reactions or set())}
    rows: list[dict[str, object]] = []
    for reaction_index, row in enumerate(reaction_rows):
        normalized_ids = {
            _normalize_reaction_id(row.get("reaction_id", "")),
            _normalize_reaction_id(row.get("cobra_reaction_id", "")),
        }
        is_protected = bool(normalized_ids & protected)
        for method in TROPPO_METHODS:
            method_value, role = method_input_value_and_role(method, row.get("evidence", ""))
            rows.append(
                {
                    "condition": row.get("condition", ""),
                    "method": method,
                    "reaction_index": reaction_index,
                    "reaction_id": row.get("reaction_id", ""),
                    "cobra_reaction_id": row.get("cobra_reaction_id", ""),
                    "reaction_name": row.get("reaction_name", ""),
                    "evidence": row.get("evidence", ""),
                    "reaction_score": row.get("reaction_score", ""),
                    "method_input_value": method_value,
                    "method_input_role": role,
                    "method_property": method_property_name(method),
                    "protected": is_protected,
                    "gene_count": row.get("gene_count", ""),
                    "measured_gene_count": row.get("measured_gene_count", ""),
                    "gene_coverage": row.get("gene_coverage", ""),
                    "source_status": row.get("status", ""),
                    "status": "prepared",
                }
            )
    return rows


def method_input_value_and_role(method: str, evidence: str) -> tuple[object, str]:
    """Return method-specific numeric/category input for one evidence label."""

    score = evidence_expression_score(evidence)
    if method == "fastcore":
        return int(evidence == "high"), "core" if evidence == "high" else "non_core"
    if method == "imat":
        if evidence == "high":
            return score, "high_expression"
        if evidence == "low":
            return score, "low_expression"
        if evidence == "medium":
            return score, "neutral_expression"
        return score, "unknown_expression"
    if method == "gimme":
        if score >= 0:
            return score, "expression_vector"
        return score, "unknown_expression"
    if method == "corda":
        confidence = corda_confidence_from_evidence(evidence)
        return confidence, f"{confidence}_confidence"
    raise ValueError(f"Unsupported TROPPO method: {method}")


def summarize_method_inputs(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Summarize prepared method inputs by condition and method."""

    conditions = sorted({str(row.get("condition") or "default") for row in rows})
    summary = []
    for condition in conditions:
        for method in TROPPO_METHODS:
            method_rows = [
                row for row in rows
                if row.get("method") == method and (row.get("condition") or "default") == condition
            ]
            summary.append(summarize_one_method_condition(condition, method, method_rows))
    return summary


def summarize_one_method_condition(condition: str, method: str, rows: list[dict[str, object]]) -> dict[str, object]:
    """Summarize one condition/method pair."""

    measured = [
        row for row in rows
        if (_to_int(row.get("gene_count")) or 0) > 0 and (_to_int(row.get("measured_gene_count")) or 0) > 0
    ]
    gpr = [row for row in rows if (_to_int(row.get("gene_count")) or 0) > 0]
    role_counts: dict[str, int] = {}
    for row in rows:
        role = str(row.get("method_input_role") or "unknown")
        role_counts[role] = role_counts.get(role, 0) + 1
    measured_fraction = len(measured) / len(gpr) if gpr else None
    status = "prepared_sparse_signal" if (measured_fraction or 0.0) < 0.05 else "prepared"
    return {
        "condition": condition,
        "method": method,
        "implementation_status": METHOD_STATUS[method],
        "reaction_count": len(rows),
        "measured_gpr_reaction_count": len(measured),
        "measured_gpr_fraction": measured_fraction,
        "positive_input_count": positive_input_count(method, rows),
        "low_or_negative_input_count": low_or_negative_input_count(method, rows),
        "protected_reaction_count": sum(1 for row in rows if row.get("protected") is True),
        "primary_input_property": method_property_name(method),
        "dominant_input_role": max(role_counts, key=role_counts.get) if role_counts else "",
        "status": status,
    }


def build_method_run_matrix(evidence_mode: str = "consensus") -> list[dict[str, object]]:
    """Return a run matrix for supported and staged TROPPO methods."""

    return [
        {
            "method": "fastcore",
            "algorithm_module": "troppo.methods.reconstruction.fastcore",
            "algorithm_class": "FASTcore",
            "properties_class": "FastcoreProperties",
            "input_strategy": "core reaction indices from high evidence plus protected reactions",
            "execution_status": METHOD_STATUS["fastcore"],
            "default_evidence_mode": evidence_mode,
            "entry_point": "tools/run_troppo_fastcore.py",
            "status": "connected",
        },
        {
            "method": "imat",
            "algorithm_module": "troppo.methods.reconstruction.imat",
            "algorithm_class": "IMAT",
            "properties_class": "IMATProperties",
            "input_strategy": "reaction expression vector: high=2, medium=1, low=0, unknown=-1",
            "execution_status": METHOD_STATUS["imat"],
            "default_evidence_mode": evidence_mode,
            "entry_point": "prepared in tools/prepare_troppo_methods.py",
            "status": "prepared",
        },
        {
            "method": "gimme",
            "algorithm_module": "troppo.methods.reconstruction.gimme",
            "algorithm_class": "GIMME",
            "properties_class": "GIMMEProperties",
            "input_strategy": "reaction expression vector plus objective reaction constraints",
            "execution_status": METHOD_STATUS["gimme"],
            "default_evidence_mode": evidence_mode,
            "entry_point": "prepared in tools/prepare_troppo_methods.py",
            "status": "prepared",
        },
        {
            "method": "corda",
            "algorithm_module": "troppo.methods.reconstruction.corda",
            "algorithm_class": "CORDA",
            "properties_class": "CORDAProperties",
            "input_strategy": "high/medium/negative confidence reaction indices",
            "execution_status": METHOD_STATUS["corda"],
            "default_evidence_mode": evidence_mode,
            "entry_point": "prepared in tools/prepare_troppo_methods.py",
            "status": "prepared",
        },
    ]


def evidence_expression_score(evidence: str) -> int:
    """Map evidence labels to nonnegative expression scores for iMAT/GIMME."""

    return {
        "high": 2,
        "medium": 1,
        "low": 0,
        "unknown": -1,
        "no_gpr": -1,
    }.get(str(evidence or ""), -1)


def corda_confidence_from_evidence(evidence: str) -> str:
    """Map evidence labels to CORDA confidence categories."""

    return {
        "high": "high",
        "medium": "medium",
        "low": "negative",
        "unknown": "unknown",
        "no_gpr": "unknown",
    }.get(str(evidence or ""), "unknown")


def method_property_name(method: str) -> str:
    """Return the primary TROPPO property populated by a prepared input."""

    return {
        "fastcore": "core",
        "imat": "exp_vector",
        "gimme": "exp_vector",
        "corda": "high_conf_rx/medium_conf_rx/neg_conf_rx",
    }[method]


def positive_input_count(method: str, rows: list[dict[str, object]]) -> int:
    """Count method-specific positive/supporting inputs."""

    if method == "fastcore":
        return sum(1 for row in rows if row.get("method_input_role") == "core")
    if method == "corda":
        return sum(1 for row in rows if row.get("method_input_role") in {"high_confidence", "medium_confidence"})
    return sum(1 for row in rows if row.get("method_input_role") in {"high_expression", "expression_vector"})


def low_or_negative_input_count(method: str, rows: list[dict[str, object]]) -> int:
    """Count low or negative evidence inputs for a method."""

    if method == "corda":
        return sum(1 for row in rows if row.get("method_input_role") == "negative_confidence")
    return sum(1 for row in rows if row.get("evidence") == "low")


def _normalize_reaction_id(reaction_id: str) -> str:
    text = str(reaction_id or "").strip()
    if text.startswith("R_"):
        text = text[2:]
    return text.lower()


def _to_int(value: object) -> int | None:
    try:
        if value in {None, ""}:
            return None
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None
