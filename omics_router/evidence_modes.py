"""Shared evidence-mode path selection for downstream reconstruction steps."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


EVIDENCE_MODES = ("transcriptomics", "relative_proteomics", "consensus", "ml_derived")


@dataclass(frozen=True, slots=True)
class EvidenceModePaths:
    """Constraint-table paths selected for a downstream evidence mode."""

    context_policy: Path
    core_reactions: Path
    reaction_evidence: Path
    gene_evidence: Path


def evidence_mode_paths(constraints_dir: str | Path, evidence_mode: str) -> EvidenceModePaths:
    """Return constraint-table paths for a named evidence mode."""

    constraints = Path(constraints_dir)
    mode = normalize_evidence_mode(evidence_mode)

    if mode == "transcriptomics":
        return EvidenceModePaths(
            context_policy=constraints / "context_reaction_policy.csv",
            core_reactions=constraints / "fastcore_core_reactions.csv",
            reaction_evidence=constraints / "reaction_expression_evidence.csv",
            gene_evidence=constraints / "gene_expression_evidence.csv",
        )
    if mode == "relative_proteomics":
        return EvidenceModePaths(
            context_policy=constraints / "relative_protein_context_reaction_policy.csv",
            core_reactions=constraints / "relative_protein_fastcore_core_reactions.csv",
            reaction_evidence=constraints / "relative_protein_reaction_evidence.csv",
            gene_evidence=constraints / "relative_protein_evidence.csv",
        )
    if mode == "consensus":
        return EvidenceModePaths(
            context_policy=constraints / "consensus_context_reaction_policy.csv",
            core_reactions=constraints / "consensus_fastcore_core_reactions.csv",
            reaction_evidence=constraints / "multi_omics_consensus_reaction_evidence.csv",
            gene_evidence=constraints / "gene_expression_evidence.csv",
        )
    return EvidenceModePaths(
        context_policy=constraints / "ml_derived_context_reaction_policy.csv",
        core_reactions=constraints / "ml_derived_fastcore_core_reactions.csv",
        reaction_evidence=constraints / "ml_derived_reaction_evidence.csv",
        gene_evidence=constraints / "ml_derived_gene_evidence.csv",
    )


def normalize_evidence_mode(evidence_mode: str) -> str:
    """Validate and normalize an evidence-mode name."""

    mode = str(evidence_mode or "").strip().lower()
    if mode not in EVIDENCE_MODES:
        allowed = ", ".join(EVIDENCE_MODES)
        raise ValueError(f"Unknown evidence mode: {evidence_mode!r}. Expected one of: {allowed}.")
    return mode
