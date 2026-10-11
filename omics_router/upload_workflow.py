"""User upload staging workflow for custom Omics-GEM Router runs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import to_json, to_yaml
from .constraints import write_csv, write_json
from .validators import EXPECTED_COLUMNS, FLEXIBLE_COLUMN_HINTS


UPLOAD_SCHEMA_VERSION = "0.2.0"
OMICS_ROLES = tuple(EXPECTED_COLUMNS.keys())
IGNORE_ROLE = "ignore"
ID_ALIAS_TABLE_ROLE = "id_alias_table"


@dataclass(slots=True)
class UploadFilePayload:
    """A file payload staged into a user run package."""

    filename: str
    data: bytes
    kind: str
    role: str
    columns: list[str]
    status: str = "pending"
    details: list[str] | None = None


@dataclass(slots=True)
class UserRunPackage:
    """Summary returned after staging user-uploaded files."""

    run_id: str
    output_dir: str
    status: str
    message: str
    files: dict[str, str]
    input_rows: list[dict[str, object]]


def infer_omics_role_candidates(
    filename: str,
    columns: list[str],
    selected_omics: list[str] | tuple[str, ...] | None = None,
) -> list[str]:
    """Infer likely omics roles from filename keywords and table columns."""

    selected = list(selected_omics or [])
    normalized_columns = {_normalize_column(column) for column in columns}
    filename_hits = set(_infer_roles_from_filename(filename))
    scored: list[tuple[float, str]] = []
    for role, expected in EXPECTED_COLUMNS.items():
        hints = FLEXIBLE_COLUMN_HINTS.get(role)
        expected_or_hints = expected or hints or set()
        overlap = len(expected_or_hints & normalized_columns)
        completeness = overlap / len(expected_or_hints) if expected_or_hints else 0.0
        score = completeness
        if role in filename_hits:
            score += 1.0
        if role in selected:
            score += 0.25
        if score > 0:
            scored.append((score, role))

    scored.sort(key=lambda item: (-item[0], selected.index(item[1]) if item[1] in selected else 999, item[1]))
    candidates = [role for _score, role in scored]
    if candidates:
        return candidates
    return selected or list(OMICS_ROLES)


def choose_default_role(
    filename: str,
    columns: list[str],
    selected_omics: list[str] | tuple[str, ...] | None = None,
) -> str:
    """Choose the first role candidate for a table, falling back to ignore."""

    candidates = infer_omics_role_candidates(filename, columns, selected_omics)
    return candidates[0] if candidates else IGNORE_ROLE


def stage_user_run_package(
    output_root: str | Path,
    run_config: dict[str, Any],
    model_file: UploadFilePayload | None,
    omics_files: list[UploadFilePayload],
    condition_files: list[UploadFilePayload] | None = None,
    run_id: str | None = None,
) -> UserRunPackage:
    """Write uploaded files plus manifest/config into a reusable run directory."""

    current_run_id = run_id or build_run_id()
    output = Path(output_root) / current_run_id
    inputs_dir = output / "inputs"
    model_dir = inputs_dir / "model"
    omics_dir = inputs_dir / "omics"
    condition_dir = inputs_dir / "condition"
    output.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)
    omics_dir.mkdir(parents=True, exist_ok=True)
    condition_dir.mkdir(parents=True, exist_ok=True)

    input_rows: list[dict[str, object]] = []
    staged_model = None
    if model_file and model_file.data:
        staged_model = _stage_payload(model_file, model_dir, prefix="model")
        input_rows.append(staged_model)

    for payload in omics_files:
        if payload.role == IGNORE_ROLE:
            continue
        staged = _stage_payload(payload, omics_dir, prefix=payload.role)
        input_rows.append(staged)

    staged_condition_files = []
    for payload in condition_files or []:
        if payload.role == IGNORE_ROLE:
            continue
        staged = _stage_payload(payload, condition_dir, prefix=payload.role)
        input_rows.append(staged)
        staged_condition_files.append(staged)

    files = {
        "manifest": str(output / "upload_manifest.json"),
        "input_file_map": str(output / "input_file_map.csv"),
        "run_config_json": str(output / "run_config.json"),
        "run_config_yaml": str(output / "run_config.yaml"),
        "next_steps": str(output / "NEXT_STEPS.md"),
    }
    config_with_inputs = dict(run_config)
    config_with_inputs["upload_package"] = {
        "run_id": current_run_id,
        "input_file_map": files["input_file_map"],
        "input_rows": input_rows,
        "condition_files": staged_condition_files,
    }
    manifest = {
        "schema_version": UPLOAD_SCHEMA_VERSION,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "run_id": current_run_id,
        "status": classify_upload_package(input_rows),
        "model": staged_model,
        "omics_files": [row for row in input_rows if row.get("kind") == "omics_table"],
        "condition_files": staged_condition_files,
        "files": files,
    }
    write_csv(files["input_file_map"], input_rows)
    write_json(files["manifest"], manifest)
    Path(files["run_config_json"]).write_text(to_json(config_with_inputs), encoding="utf-8")
    Path(files["run_config_yaml"]).write_text(to_yaml(config_with_inputs), encoding="utf-8")
    Path(files["next_steps"]).write_text(build_next_steps_text(manifest), encoding="utf-8")

    status = str(manifest["status"])
    return UserRunPackage(
        run_id=current_run_id,
        output_dir=str(output),
        status=status,
        message=build_upload_message(status, input_rows),
        files=files,
        input_rows=input_rows,
    )


def build_run_id(prefix: str = "user_run") -> str:
    """Build a filesystem-safe run id."""

    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def classify_upload_package(input_rows: list[dict[str, object]]) -> str:
    """Classify whether staged inputs are ready for manual review or execution."""

    has_model = any(row.get("kind") == "model" for row in input_rows)
    omics_count = sum(1 for row in input_rows if row.get("kind") == "omics_table")
    warning_count = sum(1 for row in input_rows if row.get("inspection_status") not in {"ok", "not_checked"})
    if not has_model:
        return "missing_model"
    if omics_count == 0:
        return "missing_omics_tables"
    if warning_count:
        return "ready_with_warnings"
    return "ready_for_review"


def build_upload_message(status: str, input_rows: list[dict[str, object]]) -> str:
    """Build a compact user-facing status message."""

    model_count = sum(1 for row in input_rows if row.get("kind") == "model")
    omics_count = sum(1 for row in input_rows if row.get("kind") == "omics_table")
    condition_count = sum(1 for row in input_rows if row.get("kind") == "condition_table")
    return f"Upload package {status}: model={model_count}, omics_tables={omics_count}, condition_tables={condition_count}."


def build_next_steps_text(manifest: dict[str, Any]) -> str:
    """Write a small run-package guide."""

    run_id = manifest.get("run_id", "")
    status = manifest.get("status", "")
    return "\n".join(
        [
            f"# User Run Package: {run_id}",
            "",
            f"Status: `{status}`",
            "",
            "This directory contains the staged model, uploaded omics tables,",
            "`input_file_map.csv`, and exported run configuration files.",
            "",
            "Recommended next checks:",
            "",
            "1. Confirm each omics table role in `input_file_map.csv`.",
            "2. Confirm gene, protein, metabolite, and reaction identifier columns.",
            "3. Review `inputs/condition` if condition setup tables are attached.",
            "4. Add organism-specific mapping tables if the IDs do not match the GEM.",
            "5. Run model QC before applying omics-derived constraints.",
            "",
            "The packaged files are intentionally staged before execution so that",
            "column mapping and identifier compatibility can be reviewed first.",
            "",
        ]
    )


def _stage_payload(payload: UploadFilePayload, target_dir: Path, prefix: str) -> dict[str, object]:
    safe_name = sanitize_filename(payload.filename)
    saved_name = f"{sanitize_filename(prefix)}__{safe_name}" if prefix else safe_name
    path = target_dir / saved_name
    path.write_bytes(payload.data)
    return {
        "kind": payload.kind,
        "role": payload.role,
        "original_name": payload.filename,
        "saved_name": saved_name,
        "path": str(path),
        "relative_path": str(path.relative_to(target_dir.parents[1])),
        "size_bytes": len(payload.data),
        "columns": ";".join(payload.columns),
        "inspection_status": payload.status,
        "details": " | ".join(payload.details or []),
    }


def sanitize_filename(filename: str) -> str:
    """Return a conservative filename that preserves the extension."""

    path = Path(filename or "uploaded_file")
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", path.stem).strip("._-") or "uploaded_file"
    suffix = re.sub(r"[^A-Za-z0-9.]+", "", path.suffix)
    return f"{stem}{suffix}"


def _infer_roles_from_filename(filename: str) -> list[str]:
    name = filename.lower()
    keyword_map = [
        ("uniprot_annotation", ["uniprot_annotation", "uniprot_annot", "protein_annotation", "ec_annotation"]),
        ("dlkcat_annotation", ["dlkcat_annotation", "dlkcat_input_annotation", "sequence_smiles", "substrate_smiles"]),
        ("production_targets", ["production_target", "production_targets", "product_target", "product_exchange"]),
        (ID_ALIAS_TABLE_ROLE, ["alias", "mapping", "id_map", "identifier_map", "xref"]),
        ("transcriptomics", ["transcript", "rna", "rnaseq", "expression", "tpm"]),
        ("absolute_proteomics", ["absolute_proteomics", "proteomics_absolute", "protein_absolute"]),
        ("relative_proteomics", ["relative_proteomics", "proteomics_relative", "protein_relative"]),
        ("extracellular_metabolomics", ["extracellular", "exchange", "exometabol", "secret"]),
        ("intracellular_metabolomics", ["intracellular", "concentration", "thermo"]),
        ("fluxomics", ["fluxomics", "13c", "mfa", "flux"]),
        ("lipidomics_glycomics", ["lipid", "glycan", "glycomics"]),
        ("ml_priors", ["kcat", "prior", "ml"]),
    ]
    return [role for role, keywords in keyword_map if any(keyword in name for keyword in keywords)]


def _normalize_column(column: str) -> str:
    return column.strip().lower().replace("-", "_").replace(" ", "_")
