"""Lightweight input inspection for uploaded model and omics files."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


EXPECTED_COLUMNS: dict[str, set[str]] = {
    "transcriptomics": {"gene_id", "sample", "value"},
    "absolute_proteomics": {"protein_id", "sample", "value", "unit"},
    "relative_proteomics": {"protein_id", "sample", "value"},
    "extracellular_metabolomics": {"metabolite_id", "sample", "value", "unit"},
    "intracellular_metabolomics": {"metabolite_id", "compartment", "sample", "value", "unit"},
    "fluxomics": {"reaction_id", "sample", "flux", "unit"},
    "lipidomics_glycomics": {"component_id", "sample", "value", "unit"},
    "ml_priors": {"target_id", "target_type", "value", "confidence"},
    "uniprot_annotation": set(),
    "dlkcat_annotation": set(),
    "production_targets": {"reaction_id"},
    "id_alias_table": {"source_id", "model_id"},
}

FLEXIBLE_COLUMN_HINTS: dict[str, set[str]] = {
    "uniprot_annotation": {
        "gene_id",
        "model_gene_id",
        "reaction_id",
        "model_reaction_id",
        "uniprot_id",
        "uniprot",
        "ec_number",
        "ec",
    },
    "dlkcat_annotation": {
        "gene_id",
        "model_gene_id",
        "protein_sequence",
        "sequence",
        "substrate_id",
        "substrate_name",
        "smiles",
        "substrate_smiles",
    },
}

MODEL_EXTENSIONS = {".xml", ".sbml", ".json", ".mat", ".yml", ".yaml"}
TABLE_EXTENSIONS = {".csv", ".tsv", ".txt"}


@dataclass(slots=True)
class FileInspection:
    """Human-readable file inspection result."""

    name: str
    kind: str
    status: str
    details: list[str]
    columns: list[str]


def inspect_model_filename(filename: str | None) -> FileInspection:
    if not filename:
        return FileInspection(
            name="",
            kind="GEM",
            status="missing",
            details=["未上传模型文件。"],
            columns=[],
        )

    suffix = Path(filename).suffix.lower()
    if suffix in MODEL_EXTENSIONS:
        return FileInspection(
            name=filename,
            kind="GEM",
            status="ok",
            details=[f"识别到模型格式 {suffix}。后续可交给 COBRApy/MEMOTE 解析。"],
            columns=[],
        )
    return FileInspection(
        name=filename,
        kind="GEM",
        status="warning",
        details=[f"文件扩展名 {suffix or '(none)'} 不在推荐模型格式中。"],
        columns=[],
    )


def inspect_table_file(file: BinaryIO, filename: str, selected_omics: list[str]) -> FileInspection:
    """Inspect a small uploaded text table without consuming the stream."""

    suffix = Path(filename).suffix.lower()
    if suffix not in TABLE_EXTENSIONS:
        return FileInspection(
            name=filename,
            kind="table",
            status="warning",
            details=[f"扩展名 {suffix or '(none)'} 不是推荐表格格式。"],
            columns=[],
        )

    position = file.tell() if hasattr(file, "tell") else None
    raw = file.read(8192)
    if position is not None and hasattr(file, "seek"):
        file.seek(position)

    if isinstance(raw, str):
        text = raw
    else:
        text = raw.decode("utf-8-sig", errors="replace")

    delimiter = "\t" if suffix == ".tsv" else ","
    try:
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        columns = next(reader)
    except StopIteration:
        columns = []
    except csv.Error as exc:
        return FileInspection(
            name=filename,
            kind="table",
            status="error",
            details=[f"无法解析表头：{exc}"],
            columns=[],
        )

    normalized = {_normalize_column(col) for col in columns}
    details = [f"识别到 {len(columns)} 个列。"]
    missing_by_type: list[str] = []

    omics_to_check = _infer_omics_from_filename(filename) or selected_omics

    for omics_type in omics_to_check:
        expected = EXPECTED_COLUMNS.get(omics_type)
        if not expected:
            hints = FLEXIBLE_COLUMN_HINTS.get(omics_type)
            if hints and not (hints & normalized):
                missing_by_type.append(f"{omics_type}: needs one of {', '.join(sorted(hints))}")
            continue
        missing = expected - normalized
        if missing:
            missing_by_type.append(f"{omics_type}: 缺少 {', '.join(sorted(missing))}")

    if missing_by_type:
        details.extend(missing_by_type[:5])
        return FileInspection(
            name=filename,
            kind="table",
            status="warning",
            details=details,
            columns=columns,
        )

    details.append("表头满足当前所选组学类型的最小字段要求。")
    return FileInspection(
        name=filename,
        kind="table",
        status="ok",
        details=details,
        columns=columns,
    )


def _normalize_column(column: str) -> str:
    return column.strip().lower().replace("-", "_").replace(" ", "_")


def _infer_omics_from_filename(filename: str) -> list[str]:
    """Infer table type from common filename keywords."""

    name = filename.lower()
    inferred: list[str] = []
    keyword_map = [
        ("uniprot_annotation", ["uniprot_annotation", "uniprot_annot", "protein_annotation", "ec_annotation"]),
        ("dlkcat_annotation", ["dlkcat_annotation", "dlkcat_input_annotation", "sequence_smiles", "substrate_smiles"]),
        ("production_targets", ["production_target", "production_targets", "product_target", "product_exchange"]),
        ("id_alias_table", ["alias", "mapping", "id_map", "identifier_map", "xref"]),
        ("transcriptomics", ["transcript", "rna", "rnaseq", "expression", "tpm"]),
        ("absolute_proteomics", ["absolute_proteomics", "proteomics_absolute", "protein_absolute"]),
        ("relative_proteomics", ["relative_proteomics", "proteomics_relative", "protein_relative"]),
        ("extracellular_metabolomics", ["extracellular", "exchange", "exometabol", "secret"]),
        ("intracellular_metabolomics", ["intracellular", "concentration", "thermo"]),
        ("fluxomics", ["fluxomics", "13c", "mfa", "flux"]),
        ("lipidomics_glycomics", ["lipid", "glycan", "glycomics"]),
        ("ml_priors", ["kcat", "prior", "ml"]),
    ]
    for omics_type, keywords in keyword_map:
        if any(keyword in name for keyword in keywords):
            inferred.append(omics_type)
    return inferred
