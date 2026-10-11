"""Multi-omics conflict diagnostics and conservative consensus evidence."""

from __future__ import annotations

from pathlib import Path

from .cobra_runner import group_by_condition
from .constraints import read_csv_records, write_csv, write_json


EVIDENCE_VALUES = {"high", "medium", "low"}


def build_multi_omics_conflict_tables(
    transcript_reaction_rows: list[dict[str, object]],
    protein_reaction_rows: list[dict[str, object]],
) -> dict[str, list[dict[str, object]]]:
    """Build conflict detail, summary, and consensus reaction evidence."""

    detail_rows = build_conflict_detail_rows(transcript_reaction_rows, protein_reaction_rows)
    consensus_rows = build_consensus_reaction_evidence(transcript_reaction_rows, protein_reaction_rows)
    return {
        "multi_omics_conflict_detail": detail_rows,
        "multi_omics_conflict_summary": summarize_conflicts(detail_rows),
        "multi_omics_consensus_reaction_evidence": consensus_rows,
    }


def run_multi_omics_conflict_qc(
    transcript_reaction_evidence_path: str | Path,
    protein_reaction_evidence_path: str | Path,
    output_dir: str | Path,
) -> dict[str, str]:
    """Write multi-omics conflict diagnostics from existing evidence tables."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "detail": str(output / "multi_omics_conflict_detail.csv"),
        "summary": str(output / "multi_omics_conflict_summary.csv"),
        "consensus": str(output / "multi_omics_consensus_reaction_evidence.csv"),
        "manifest": str(output / "multi_omics_conflict_manifest.json"),
    }
    tables = build_multi_omics_conflict_tables(
        read_csv_records(transcript_reaction_evidence_path),
        read_csv_records(protein_reaction_evidence_path),
    )
    write_csv(files["detail"], tables["multi_omics_conflict_detail"])
    write_csv(files["summary"], tables["multi_omics_conflict_summary"])
    write_csv(files["consensus"], tables["multi_omics_consensus_reaction_evidence"])
    write_json(
        files["manifest"],
        {
            "status": "completed",
            "transcript_reaction_evidence_path": str(transcript_reaction_evidence_path),
            "protein_reaction_evidence_path": str(protein_reaction_evidence_path),
            "files": files,
        },
    )
    return files


def build_conflict_detail_rows(
    transcript_reaction_rows: list[dict[str, object]],
    protein_reaction_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Return comparable reaction rows with agreement/conflict labels."""

    transcript_lookup = _lookup_by_condition_reaction(transcript_reaction_rows)
    protein_lookup = _lookup_by_condition_reaction(protein_reaction_rows)
    rows = []
    for key in sorted(set(transcript_lookup) & set(protein_lookup)):
        transcript = transcript_lookup[key]
        protein = protein_lookup[key]
        transcript_evidence = str(transcript.get("evidence", ""))
        protein_evidence = str(protein.get("evidence", ""))
        if transcript_evidence not in EVIDENCE_VALUES or protein_evidence not in EVIDENCE_VALUES:
            continue
        conflict_type = classify_conflict(transcript_evidence, protein_evidence)
        rows.append(
            {
                "condition": transcript.get("condition") or protein.get("condition") or "",
                "reaction_id": transcript.get("reaction_id") or protein.get("reaction_id") or "",
                "cobra_reaction_id": transcript.get("cobra_reaction_id") or protein.get("cobra_reaction_id") or "",
                "reaction_name": transcript.get("reaction_name") or protein.get("reaction_name") or "",
                "transcript_evidence": transcript_evidence,
                "protein_evidence": protein_evidence,
                "transcript_score": transcript.get("reaction_score", ""),
                "protein_score": protein.get("reaction_score", ""),
                "transcript_gene_coverage": transcript.get("gene_coverage", ""),
                "protein_gene_coverage": protein.get("gene_coverage", ""),
                "transcript_measured_genes": transcript.get("measured_genes", ""),
                "protein_measured_genes": protein.get("measured_genes", ""),
                "conflict_type": conflict_type,
                "recommendation": conflict_recommendation(conflict_type),
                "status": "conflict" if conflict_type in {"transcript_low_protein_high", "transcript_high_protein_low"} else "agreement_or_partial",
            }
        )
    return rows


def classify_conflict(transcript_evidence: str, protein_evidence: str) -> str:
    """Classify transcript/protein evidence relationship."""

    if transcript_evidence == "low" and protein_evidence == "high":
        return "transcript_low_protein_high"
    if transcript_evidence == "high" and protein_evidence == "low":
        return "transcript_high_protein_low"
    if transcript_evidence == protein_evidence:
        return f"agreement_{transcript_evidence}"
    if transcript_evidence == "medium":
        return f"protein_specific_{protein_evidence}"
    if protein_evidence == "medium":
        return f"transcript_specific_{transcript_evidence}"
    return "partial_disagreement"


def conflict_recommendation(conflict_type: str) -> str:
    """Return a short recommendation for one conflict type."""

    if conflict_type == "transcript_low_protein_high":
        return "Do not delete solely from transcriptomics; inspect protein evidence, reference condition, and flux/phenotype support."
    if conflict_type == "transcript_high_protein_low":
        return "Keep with caution; protein evidence weakens enzyme availability and may indicate post-transcriptional regulation."
    if conflict_type.startswith("agreement_"):
        return "Modalities agree; suitable for downstream context evidence with normal validation."
    return "Treat as moderate evidence; avoid hard keep/delete decisions without validation."


def build_consensus_reaction_evidence(
    transcript_reaction_rows: list[dict[str, object]],
    protein_reaction_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Build conservative consensus reaction evidence from transcript/protein rows."""

    transcript_lookup = _lookup_by_condition_reaction(transcript_reaction_rows)
    protein_lookup = _lookup_by_condition_reaction(protein_reaction_rows)
    rows = []
    for key in sorted(set(transcript_lookup) | set(protein_lookup)):
        transcript = transcript_lookup.get(key, {})
        protein = protein_lookup.get(key, {})
        transcript_evidence = str(transcript.get("evidence", ""))
        protein_evidence = str(protein.get("evidence", ""))
        conflict_type = (
            classify_conflict(transcript_evidence, protein_evidence)
            if transcript_evidence in EVIDENCE_VALUES and protein_evidence in EVIDENCE_VALUES
            else "single_modality"
        )
        consensus_evidence = choose_consensus_evidence(transcript_evidence, protein_evidence, conflict_type)
        template = transcript or protein
        status = str(template.get("status", ""))
        if conflict_type in {"transcript_low_protein_high", "transcript_high_protein_low"}:
            status = "multi_omics_conflict"
        rows.append(
            {
                "condition": template.get("condition", ""),
                "reaction_id": template.get("reaction_id", ""),
                "cobra_reaction_id": template.get("cobra_reaction_id", ""),
                "reaction_name": template.get("reaction_name", ""),
                "reaction_score": consensus_score(consensus_evidence),
                "evidence": consensus_evidence,
                "gene_count": template.get("gene_count", ""),
                "measured_gene_count": max_int(transcript.get("measured_gene_count"), protein.get("measured_gene_count")),
                "gene_coverage": max_float(transcript.get("gene_coverage"), protein.get("gene_coverage")),
                "imat_weight": imat_weight(consensus_evidence),
                "fastcore_core": consensus_evidence == "high",
                "corda_confidence": corda_confidence(consensus_evidence),
                "gpr_rule": template.get("gpr_rule", ""),
                "measured_genes": merge_measured_genes(transcript.get("measured_genes", ""), protein.get("measured_genes", "")),
                "transcript_evidence": transcript_evidence,
                "protein_evidence": protein_evidence,
                "conflict_type": conflict_type,
                "evidence_source": evidence_source(transcript_evidence, protein_evidence, conflict_type),
                "recommendation": conflict_recommendation(conflict_type),
                "status": status,
            }
        )
    return rows


def choose_consensus_evidence(transcript_evidence: str, protein_evidence: str, conflict_type: str) -> str:
    """Choose a conservative consensus evidence label."""

    if conflict_type in {"transcript_low_protein_high", "transcript_high_protein_low", "partial_disagreement"}:
        return "medium"
    if transcript_evidence in EVIDENCE_VALUES and protein_evidence in EVIDENCE_VALUES:
        if transcript_evidence == protein_evidence:
            return transcript_evidence
        if "medium" in {transcript_evidence, protein_evidence}:
            return "medium"
    if transcript_evidence in EVIDENCE_VALUES:
        return transcript_evidence
    if protein_evidence in EVIDENCE_VALUES:
        return protein_evidence
    if transcript_evidence == "no_gpr" or protein_evidence == "no_gpr":
        return "no_gpr"
    return "unknown"


def summarize_conflicts(detail_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Summarize conflict counts by condition and overall."""

    grouped = group_by_condition([{key: str(value) for key, value in row.items()} for row in detail_rows])
    rows = [_summarize_condition(condition, rows_for_condition) for condition, rows_for_condition in sorted(grouped.items())]
    if detail_rows:
        rows.append(_summarize_condition("ALL", [{key: str(value) for key, value in row.items()} for row in detail_rows]))
    return rows


def _summarize_condition(condition: str, rows: list[dict[str, str]]) -> dict[str, object]:
    comparable_count = len(rows)
    strong_conflicts = [row for row in rows if row.get("conflict_type") in {"transcript_low_protein_high", "transcript_high_protein_low"}]
    return {
        "condition": condition,
        "comparable_reaction_count": comparable_count,
        "agreement_count": sum(1 for row in rows if row.get("conflict_type", "").startswith("agreement_")),
        "partial_disagreement_count": sum(1 for row in rows if "specific" in row.get("conflict_type", "")),
        "conflict_count": len(strong_conflicts),
        "conflict_fraction": _fraction(len(strong_conflicts), comparable_count),
        "transcript_low_protein_high_count": sum(1 for row in rows if row.get("conflict_type") == "transcript_low_protein_high"),
        "transcript_high_protein_low_count": sum(1 for row in rows if row.get("conflict_type") == "transcript_high_protein_low"),
        "status": "summary",
    }


def evidence_source(transcript_evidence: str, protein_evidence: str, conflict_type: str) -> str:
    """Describe which modality drives the consensus evidence."""

    if conflict_type == "single_modality":
        if transcript_evidence in EVIDENCE_VALUES:
            return "transcriptomics"
        if protein_evidence in EVIDENCE_VALUES:
            return "relative_proteomics"
        return "none"
    if conflict_type.startswith("agreement_"):
        return "transcriptomics+relative_proteomics"
    if "protein" in conflict_type and "transcript" not in conflict_type:
        return "relative_proteomics"
    if "transcript" in conflict_type and "protein" not in conflict_type:
        return "transcriptomics"
    return "conflict_consensus"


def consensus_score(evidence: str) -> int | None:
    return {"high": 1, "medium": 0, "low": -1}.get(evidence)


def imat_weight(evidence: str) -> int:
    return {"high": 1, "low": -1}.get(evidence, 0)


def corda_confidence(evidence: str) -> str:
    return {
        "high": "high",
        "medium": "medium",
        "low": "negative",
        "unknown": "unknown",
        "no_gpr": "unknown",
    }.get(evidence, "unknown")


def merge_measured_genes(left: object, right: object) -> str:
    genes = set()
    for value in (left, right):
        for gene in str(value or "").split(";"):
            if gene:
                genes.add(gene)
    return ";".join(sorted(genes))


def max_int(left: object, right: object) -> int | None:
    values = [_to_int(left), _to_int(right)]
    values = [value for value in values if value is not None]
    return max(values) if values else None


def max_float(left: object, right: object) -> float | None:
    values = [_to_float(left), _to_float(right)]
    values = [value for value in values if value is not None]
    return max(values) if values else None


def _lookup_by_condition_reaction(rows: list[dict[str, object]]) -> dict[tuple[str, str], dict[str, object]]:
    lookup = {}
    for row in rows:
        condition = str(row.get("condition") or "default")
        reaction_id = normalize_reaction_id(str(row.get("reaction_id") or row.get("cobra_reaction_id") or ""))
        if reaction_id:
            lookup[(condition, reaction_id)] = row
    return lookup


def normalize_reaction_id(reaction_id: str) -> str:
    text = reaction_id.strip()
    return text[2:] if text.startswith("R_") else text


def _fraction(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _to_int(value: object) -> int | None:
    try:
        if value in {None, ""}:
            return None
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _to_float(value: object) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(str(value))
    except (TypeError, ValueError):
        return None
