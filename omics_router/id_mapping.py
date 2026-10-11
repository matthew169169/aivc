"""Identifier compatibility review for staged user upload packages."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .constraints import SbmlModelIndex, parse_sbml_index, read_csv_records, write_csv, write_json


@dataclass(slots=True)
class IdMappingReviewResult:
    """Summary returned after reviewing staged input identifiers."""

    status: str
    output_dir: str
    message: str
    files: dict[str, str]
    summary_rows: list[dict[str, object]]
    detail_rows: list[dict[str, object]]


@dataclass(frozen=True, slots=True)
class AliasEntry:
    """One user-supplied identifier alias."""

    source_id: str
    model_id: str
    target_type: str
    source_file: str
    source_row_index: int


@dataclass(frozen=True, slots=True)
class MappingResolution:
    """Resolved identifier plus optional alias provenance."""

    model_id: str
    status: str
    alias_model_id: str = ""
    alias_source: str = ""
    note: str = ""


ID_ALIAS_TABLE_ROLE = "id_alias_table"
ALIAS_SOURCE_COLUMNS = ("source_id", "alias_id", "external_id", "input_id", "from_id", "uniprot_id", "protein_id", "gene_id")
ALIAS_MODEL_COLUMNS = (
    "model_id",
    "to_id",
    "target_id",
    "model_gene_id",
    "model_reaction_id",
    "model_metabolite_id",
    "cobra_id",
)
NORMALIZED_INPUT_MAP = "normalized_input_map.csv"


def run_id_mapping_review(
    package_dir: str | Path,
    output_dir: str | Path | None = None,
) -> IdMappingReviewResult:
    """Review whether staged user-input identifiers can be resolved in the GEM."""

    package = Path(package_dir)
    output = Path(output_dir) if output_dir else package / "id_mapping_results"
    output.mkdir(parents=True, exist_ok=True)

    input_rows = _read_input_map(package)
    model_path = _find_model_path(package, input_rows)
    model_index = None
    model_status = "missing_model"
    model_message = "No staged GEM model was found; identifiers were not checked against a model."
    if model_path is not None:
        try:
            model_index = parse_sbml_index(model_path)
            model_status = "indexed"
            model_message = (
                f"Indexed model identifiers: reactions={len(model_index.reactions)}, "
                f"metabolites={len(model_index.metabolites)}, genes={len(model_index.genes)}."
            )
        except Exception as exc:  # pragma: no cover - exact parser failures are format-dependent.
            model_status = "parse_failed"
            model_message = f"Could not parse model identifiers: {type(exc).__name__}: {exc}"

    alias_index, alias_summary_rows = build_alias_index(input_rows, package)
    detail_rows = build_id_mapping_detail(input_rows, package, model_index, alias_index)
    summary_rows = build_id_mapping_summary(detail_rows)
    normalized_rows = write_normalized_inputs(input_rows, package, model_index, alias_index)

    files = {
        "summary": str(output / "id_mapping_summary.csv"),
        "detail": str(output / "id_mapping_detail.csv"),
        "alias_summary": str(output / "id_alias_table_summary.csv"),
        "normalized_input_map": str(package / "normalized_inputs" / NORMALIZED_INPUT_MAP),
        "manifest": str(output / "id_mapping_manifest.json"),
    }
    write_csv(files["summary"], summary_rows)
    write_csv(files["detail"], detail_rows)
    write_csv(files["alias_summary"], alias_summary_rows)
    manifest = {
        "schema_version": "0.1.0",
        "status": "completed",
        "model_status": model_status,
        "model_path": str(model_path or ""),
        "message": model_message,
        "summary_count": len(summary_rows),
        "detail_count": len(detail_rows),
        "alias_table_count": len(alias_summary_rows),
        "alias_entry_count": len(alias_index),
        "normalized_table_count": len(normalized_rows),
        "files": files,
    }
    write_json(files["manifest"], manifest)

    mapped = sum(1 for row in detail_rows if row.get("mapping_status") in {"mapped", "alias_mapped"})
    alias_mapped = sum(1 for row in detail_rows if row.get("mapping_status") == "alias_mapped")
    checked = sum(
        1
        for row in detail_rows
        if row.get("mapping_status") in {"mapped", "alias_mapped", "not_found", "alias_target_not_found"}
    )
    message = (
        f"ID mapping review completed: mapped={mapped}, alias_mapped={alias_mapped}, "
        f"checked={checked}, inputs={len(summary_rows)}. {model_message}"
    )
    return IdMappingReviewResult(
        status="completed",
        output_dir=str(output),
        message=message,
        files=files,
        summary_rows=summary_rows,
        detail_rows=detail_rows,
    )


def build_id_mapping_detail(
    input_rows: list[dict[str, str]],
    package_dir: str | Path,
    model_index: SbmlModelIndex | None,
    alias_index: dict[tuple[str, str], AliasEntry] | None = None,
) -> list[dict[str, object]]:
    """Build one row per mappable identifier found in staged inputs."""

    package = Path(package_dir)
    aliases = alias_index or {}
    detail_rows: list[dict[str, object]] = []
    for input_row in input_rows:
        for spec in _mapping_specs_for_input(input_row):
            table_path = _resolve_input_path(package, input_row)
            source_file = input_row.get("relative_path") or input_row.get("path", "")
            if table_path is None:
                detail_rows.append(
                    _detail_row(input_row, source_file, 0, spec.entity_type, spec.source_column, "", spec.target_type, "", "not_checked", "input_file_missing")
                )
                continue
            try:
                records = _read_table_records(table_path)
            except Exception as exc:
                detail_rows.append(
                    _detail_row(
                        input_row,
                        source_file,
                        0,
                        spec.entity_type,
                        spec.source_column,
                        "",
                        spec.target_type,
                        "",
                        "not_checked",
                        f"read_failed: {type(exc).__name__}: {exc}",
                    )
                )
                continue
            if not records:
                detail_rows.append(
                    _detail_row(input_row, source_file, 0, spec.entity_type, spec.source_column, "", spec.target_type, "", "not_checked", "no_rows")
                )
                continue
            for row_index, record in enumerate(records, start=1):
                if spec.condition:
                    if not spec.condition(record):
                        continue
                raw_id = _pick_value(record, spec.source_columns)
                if not raw_id:
                    if spec.optional:
                        continue
                    detail_rows.append(
                        _detail_row(input_row, source_file, row_index, spec.entity_type, spec.source_column, "", spec.target_type, "", "missing_id", "missing source identifier")
                    )
                    continue
                resolution = _resolve_identifier(raw_id, spec.target_type, model_index, aliases)
                note = "; ".join(part for part in (spec.note, resolution.note) if part)
                detail_rows.append(
                    _detail_row(
                        input_row,
                        source_file,
                        row_index,
                        spec.entity_type,
                        spec.source_column,
                        raw_id,
                        spec.target_type,
                        resolution.model_id,
                        resolution.status,
                        note,
                        alias_model_id=resolution.alias_model_id,
                        alias_source=resolution.alias_source,
                    )
                )
    return detail_rows


def build_alias_index(
    input_rows: list[dict[str, str]],
    package_dir: str | Path,
) -> tuple[dict[tuple[str, str], AliasEntry], list[dict[str, object]]]:
    """Read staged alias tables and build a lookup index."""

    package = Path(package_dir)
    alias_index: dict[tuple[str, str], AliasEntry] = {}
    summary_rows: list[dict[str, object]] = []
    for input_row in input_rows:
        if input_row.get("role") != ID_ALIAS_TABLE_ROLE:
            continue
        table_path = _resolve_input_path(package, input_row)
        source_file = input_row.get("relative_path") or input_row.get("path", "")
        if table_path is None:
            summary_rows.append(_alias_summary_row(input_row, source_file, 0, 0, 0, 0, "", "input_file_missing"))
            continue
        try:
            records = _read_table_records(table_path)
        except Exception as exc:
            summary_rows.append(
                _alias_summary_row(input_row, source_file, 0, 0, 0, 0, "", f"read_failed: {type(exc).__name__}: {exc}")
            )
            continue

        usable = 0
        skipped = 0
        duplicates = 0
        target_counts: dict[str, int] = {}
        for row_index, record in enumerate(records, start=1):
            source_id = _pick_value(record, ALIAS_SOURCE_COLUMNS)
            model_id = _pick_value(record, ALIAS_MODEL_COLUMNS)
            target_type = _alias_target_type(record)
            if not source_id or not model_id:
                skipped += 1
                continue
            key = (target_type or "any", _normalize_id(source_id))
            if key in alias_index:
                duplicates += 1
                continue
            alias_index[key] = AliasEntry(
                source_id=source_id,
                model_id=model_id,
                target_type=target_type or "any",
                source_file=source_file,
                source_row_index=row_index,
            )
            usable += 1
            target_counts[target_type or "any"] = target_counts.get(target_type or "any", 0) + 1
        target_types = ";".join(f"{name}:{count}" for name, count in sorted(target_counts.items()))
        summary_rows.append(
            _alias_summary_row(input_row, source_file, len(records), usable, skipped, duplicates, target_types, "loaded")
        )
    return alias_index, summary_rows


def write_normalized_inputs(
    input_rows: list[dict[str, str]],
    package_dir: str | Path,
    model_index: SbmlModelIndex | None,
    alias_index: dict[tuple[str, str], AliasEntry] | None = None,
) -> list[dict[str, object]]:
    """Write alias-normalized copies of supported staged input tables."""

    package = Path(package_dir)
    normalized_root = package / "normalized_inputs"
    normalized_map: list[dict[str, object]] = []
    for input_row in input_rows:
        specs = _mapping_specs_for_input(input_row)
        if not specs:
            continue
        source_path = _resolve_input_path(package, input_row)
        source_file = input_row.get("relative_path") or input_row.get("path", "")
        if source_path is None:
            normalized_map.append(_normalized_map_row(input_row, source_file, "", 0, 0, 0, 0, "input_file_missing"))
            continue
        try:
            records = _read_table_records(source_path)
        except Exception as exc:
            normalized_map.append(
                _normalized_map_row(input_row, source_file, "", 0, 0, 0, 0, f"read_failed: {type(exc).__name__}: {exc}")
            )
            continue
        normalized_records, counts = normalize_records_for_input(input_row, records, model_index, alias_index or {})
        if not normalized_records:
            normalized_map.append(_normalized_map_row(input_row, source_file, "", 0, 0, 0, 0, "no_rows"))
            continue
        group = "condition" if input_row.get("kind") == "condition_table" else "omics"
        output_dir = normalized_root / group
        saved_name = input_row.get("saved_name") or source_path.name
        output_path = output_dir / saved_name
        write_csv(output_path, _align_rows(normalized_records))
        normalized_map.append(
            _normalized_map_row(
                input_row,
                source_file,
                str(output_path.relative_to(package)),
                len(normalized_records),
                counts["direct_mapped"],
                counts["alias_mapped"],
                counts["not_found"],
                "normalized",
            )
        )

    map_path = normalized_root / NORMALIZED_INPUT_MAP
    write_csv(map_path, normalized_map)
    return normalized_map


def normalize_records_for_input(
    input_row: dict[str, str],
    records: list[dict[str, str]],
    model_index: SbmlModelIndex | None,
    alias_index: dict[tuple[str, str], AliasEntry],
) -> tuple[list[dict[str, object]], dict[str, int]]:
    """Normalize supported identifier columns in a staged input table."""

    specs = _mapping_specs_for_input(input_row)
    counts = {"direct_mapped": 0, "alias_mapped": 0, "not_found": 0}
    normalized_records: list[dict[str, object]] = []
    for record in records:
        normalized = dict(record)
        statuses: list[str] = []
        alias_sources: list[str] = []
        notes: list[str] = []
        for spec in specs:
            if spec.condition and not spec.condition(record):
                continue
            source_column, raw_id = _pick_column_value(record, spec.source_columns)
            if not raw_id:
                continue
            resolution = _resolve_identifier(raw_id, spec.target_type, model_index, alias_index)
            statuses.append(resolution.status)
            if resolution.status == "mapped":
                counts["direct_mapped"] += 1
                _apply_normalized_identifier(normalized, input_row, spec, source_column, raw_id, resolution.model_id)
            elif resolution.status == "alias_mapped":
                counts["alias_mapped"] += 1
                _apply_normalized_identifier(normalized, input_row, spec, source_column, raw_id, resolution.model_id)
                if resolution.alias_source:
                    alias_sources.append(resolution.alias_source)
                if resolution.note:
                    notes.append(resolution.note)
            elif resolution.status in {"not_found", "alias_target_not_found"}:
                counts["not_found"] += 1
                if resolution.note:
                    notes.append(resolution.note)
        if statuses:
            normalized["id_mapping_statuses"] = ";".join(statuses)
        if alias_sources:
            normalized["alias_sources"] = ";".join(alias_sources)
        if notes:
            existing_note = str(normalized.get("note", ""))
            normalized["note"] = "; ".join(part for part in (existing_note, *notes) if part)
        normalized_records.append(normalized)
    return normalized_records, counts


def build_id_mapping_summary(detail_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Aggregate ID mapping detail rows into package-level review rows."""

    grouped: dict[tuple[str, str, str, str], list[dict[str, object]]] = {}
    for row in detail_rows:
        key = (
            str(row.get("input_role", "")),
            str(row.get("input_kind", "")),
            str(row.get("entity_type", "")),
            str(row.get("source_file", "")),
        )
        grouped.setdefault(key, []).append(row)

    summary_rows: list[dict[str, object]] = []
    for (input_role, input_kind, entity_type, source_file), rows in sorted(grouped.items()):
        total = len(rows)
        direct_mapped = _count_status(rows, "mapped")
        alias_mapped = _count_status(rows, "alias_mapped")
        alias_target_not_found = _count_status(rows, "alias_target_not_found")
        mapped = direct_mapped + alias_mapped
        not_found = _count_status(rows, "not_found") + alias_target_not_found
        missing = _count_status(rows, "missing_id")
        not_checked = _count_status(rows, "not_checked")
        denominator = mapped + not_found
        before_mapped_fraction = direct_mapped / denominator if denominator else 0.0
        mapped_fraction = mapped / denominator if denominator else 0.0
        label = _mapping_label(total, denominator, mapped_fraction, missing, not_checked)
        summary_rows.append(
            {
                "input_role": input_role,
                "input_kind": input_kind,
                "entity_type": entity_type,
                "source_file": source_file,
                "total_count": total,
                "mapped_count": mapped,
                "direct_mapped_count": direct_mapped,
                "alias_mapped_count": alias_mapped,
                "not_found_count": not_found,
                "alias_target_not_found_count": alias_target_not_found,
                "missing_id_count": missing,
                "not_checked_count": not_checked,
                "before_mapped_count": direct_mapped,
                "after_mapped_count": mapped,
                "before_mapped_fraction": round(before_mapped_fraction, 4),
                "after_mapped_fraction": round(mapped_fraction, 4),
                "mapped_fraction": round(mapped_fraction, 4),
                "mapping_label": label,
                "guidance": _mapping_guidance(label),
            }
        )
    return summary_rows


@dataclass(frozen=True, slots=True)
class MappingSpec:
    """Column-to-model mapping rule for one staged input role."""

    entity_type: str
    target_type: str
    source_columns: tuple[str, ...]
    source_column: str
    note: str = ""
    optional: bool = False
    condition: Callable[[dict[str, str]], bool] | None = None


def _mapping_specs_for_input(input_row: dict[str, str]) -> list[MappingSpec]:
    kind = input_row.get("kind", "")
    role = input_row.get("role", "")
    if kind == "model":
        return []
    if role == ID_ALIAS_TABLE_ROLE:
        return []
    if kind == "omics_table":
        return _omics_mapping_specs(role)
    if kind == "condition_table":
        return _condition_mapping_specs(role)
    return []


def _omics_mapping_specs(role: str) -> list[MappingSpec]:
    if role == "transcriptomics":
        return [MappingSpec("gene", "gene", ("gene_id",), "gene_id")]
    if role in {"absolute_proteomics", "relative_proteomics"}:
        return [MappingSpec("protein_or_gene", "gene", ("gene_id", "protein_id"), "gene_id|protein_id")]
    if role in {"extracellular_metabolomics", "intracellular_metabolomics"}:
        return [MappingSpec("metabolite", "metabolite", ("metabolite_id",), "metabolite_id")]
    if role == "fluxomics":
        return [MappingSpec("reaction", "reaction", ("model_reaction_id", "reaction_id"), "model_reaction_id|reaction_id")]
    if role == "ml_priors":
        return [
            MappingSpec("ml_prior_gene", "gene", ("target_id",), "target_id", condition=lambda row: _target_type(row) == "gene"),
            MappingSpec("ml_prior_reaction", "reaction", ("target_id",), "target_id", condition=lambda row: _target_type(row) == "reaction"),
            MappingSpec("ml_prior_metabolite", "metabolite", ("target_id",), "target_id", condition=lambda row: _target_type(row) == "metabolite"),
        ]
    return []


def _condition_mapping_specs(role: str) -> list[MappingSpec]:
    if role == "condition_exchange_bounds":
        return [MappingSpec("reaction", "reaction", ("model_reaction_id", "reaction_id"), "model_reaction_id|reaction_id")]
    if role == "condition_environment":
        return [
            MappingSpec("substrate_exchange", "reaction", ("substrate_rxn",), "substrate_rxn", optional=True),
            MappingSpec("oxygen_exchange", "reaction", ("oxygen_rxn",), "oxygen_rxn", optional=True),
            MappingSpec("co2_exchange", "reaction", ("co2_rxn",), "co2_rxn", optional=True),
        ]
    return []


def _resolve_identifier(
    raw_id: str,
    target_type: str,
    model_index: SbmlModelIndex | None,
    alias_index: dict[tuple[str, str], AliasEntry] | None = None,
) -> MappingResolution:
    if model_index is None:
        return MappingResolution(raw_id.strip(), "not_checked")
    resolver = _resolver_for_target(model_index, target_type)
    if resolver is None:
        return MappingResolution(raw_id.strip(), "not_checked")

    direct_model_id, direct_status = resolver(raw_id)
    if direct_status == "mapped":
        return MappingResolution(direct_model_id, "mapped")

    alias = _lookup_alias(alias_index or {}, target_type, raw_id)
    if alias is None:
        return MappingResolution(direct_model_id, direct_status)

    alias_model_id, alias_status = resolver(alias.model_id)
    alias_source = f"{alias.source_file}:{alias.source_row_index}"
    if alias_status == "mapped":
        return MappingResolution(
            alias_model_id,
            "alias_mapped",
            alias_model_id=alias.model_id,
            alias_source=alias_source,
            note=f"resolved by alias table from {raw_id} to {alias.model_id}",
        )
    return MappingResolution(
        alias_model_id,
        "alias_target_not_found",
        alias_model_id=alias.model_id,
        alias_source=alias_source,
        note=f"alias target did not resolve in GEM: {alias.model_id}",
    )


def _resolver_for_target(model_index: SbmlModelIndex, target_type: str):
    if target_type == "gene":
        return model_index.resolve_gene
    if target_type == "reaction":
        return model_index.resolve_reaction
    if target_type == "metabolite":
        return model_index.resolve_metabolite
    return None


def _lookup_alias(alias_index: dict[tuple[str, str], AliasEntry], target_type: str, raw_id: str) -> AliasEntry | None:
    normalized = _normalize_id(raw_id)
    return alias_index.get((target_type, normalized)) or alias_index.get(("any", normalized))


def _detail_row(
    input_row: dict[str, str],
    source_file: str,
    row_index: int,
    entity_type: str,
    source_column: str,
    source_id: str,
    target_type: str,
    model_id: str,
    mapping_status: str,
    note: str,
    alias_model_id: str = "",
    alias_source: str = "",
) -> dict[str, object]:
    return {
        "input_role": input_row.get("role", ""),
        "input_kind": input_row.get("kind", ""),
        "source_file": source_file,
        "source_row_index": row_index,
        "entity_type": entity_type,
        "source_column": source_column,
        "source_id": source_id,
        "target_type": target_type,
        "model_id": model_id,
        "mapping_status": mapping_status,
        "alias_model_id": alias_model_id,
        "alias_source": alias_source,
        "note": note,
    }


def _normalized_map_row(
    input_row: dict[str, str],
    source_file: str,
    relative_path: str,
    row_count: int,
    direct_mapped_count: int,
    alias_mapped_count: int,
    not_found_count: int,
    status: str,
) -> dict[str, object]:
    return {
        "kind": input_row.get("kind", ""),
        "role": input_row.get("role", ""),
        "original_name": input_row.get("original_name", ""),
        "saved_name": input_row.get("saved_name", ""),
        "source_relative_path": source_file,
        "relative_path": relative_path,
        "path": "",
        "row_count": row_count,
        "direct_mapped_count": direct_mapped_count,
        "alias_mapped_count": alias_mapped_count,
        "not_found_count": not_found_count,
        "status": status,
    }


def _alias_summary_row(
    input_row: dict[str, str],
    source_file: str,
    total_rows: int,
    usable_alias_count: int,
    skipped_count: int,
    duplicate_count: int,
    target_types: str,
    status: str,
) -> dict[str, object]:
    return {
        "input_role": input_row.get("role", ""),
        "input_kind": input_row.get("kind", ""),
        "source_file": source_file,
        "total_rows": total_rows,
        "usable_alias_count": usable_alias_count,
        "skipped_count": skipped_count,
        "duplicate_count": duplicate_count,
        "target_types": target_types,
        "status": status,
    }


def _read_input_map(package: Path) -> list[dict[str, str]]:
    path = package / "input_file_map.csv"
    if not path.exists() or path.stat().st_size == 0:
        return []
    return read_csv_records(path)


def _find_model_path(package: Path, input_rows: list[dict[str, str]]) -> Path | None:
    for row in input_rows:
        if row.get("kind") != "model":
            continue
        return _resolve_input_path(package, row)
    return None


def _resolve_input_path(package: Path, row: dict[str, str]) -> Path | None:
    direct_text = row.get("path", "")
    if direct_text:
        direct = Path(direct_text)
        if direct.exists():
            return direct
    relative = row.get("relative_path", "")
    if relative:
        candidate = package / relative
        if candidate.exists():
            return candidate
    return None


def _read_table_records(path: Path) -> list[dict[str, str]]:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=delimiter))


def _pick_value(row: dict[str, str], columns: tuple[str, ...]) -> str:
    _column, value = _pick_column_value(row, columns)
    return value


def _pick_column_value(row: dict[str, str], columns: tuple[str, ...]) -> tuple[str, str]:
    normalized = {_normalize_column(key): value for key, value in row.items()}
    for column in columns:
        value = normalized.get(_normalize_column(column), "")
        if value and value.strip():
            return column, value.strip()
    return "", ""


def _apply_normalized_identifier(
    record: dict[str, object],
    input_row: dict[str, str],
    spec: MappingSpec,
    source_column: str,
    raw_id: str,
    model_id: str,
) -> None:
    role = input_row.get("role", "")
    _preserve_original(record, source_column, raw_id)
    if spec.target_type == "gene":
        record["gene_id"] = model_id
        if role in {"absolute_proteomics", "relative_proteomics"} and "protein_id" in record:
            _preserve_original(record, "protein_id", str(record.get("protein_id", "")))
    elif spec.target_type == "reaction":
        if role == "condition_environment" and source_column in {"substrate_rxn", "oxygen_rxn", "co2_rxn"}:
            record[source_column] = model_id
        else:
            record["model_reaction_id"] = model_id
            if source_column == "reaction_id":
                record["reaction_id"] = model_id
    elif spec.target_type == "metabolite":
        record["model_metabolite_id"] = model_id
        if source_column == "metabolite_id":
            record["metabolite_id"] = model_id


def _preserve_original(record: dict[str, object], source_column: str, raw_id: str) -> None:
    if not source_column or not raw_id:
        return
    original_column = f"original_{source_column}"
    if original_column not in record:
        record[original_column] = raw_id


def _align_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    headers: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in headers:
                headers.append(key)
    return [{header: row.get(header, "") for header in headers} for row in rows]


def _normalize_column(column: str) -> str:
    return column.strip().lower().replace("-", "_").replace(" ", "_")


def _normalize_id(value: str) -> str:
    return value.strip().lower()


def _target_type(row: dict[str, str]) -> str:
    value = _pick_value(row, ("target_type", "entity_type", "type"))
    normalized = value.strip().lower()
    aliases = {
        "rxn": "reaction",
        "reaction_id": "reaction",
        "gene_id": "gene",
        "protein": "gene",
        "protein_id": "gene",
        "metabolite_id": "metabolite",
        "met": "metabolite",
    }
    return aliases.get(normalized, normalized)


def _alias_target_type(row: dict[str, str]) -> str:
    explicit = _target_type(row)
    if explicit:
        return explicit
    normalized_columns = {_normalize_column(key) for key in row.keys()}
    if "model_reaction_id" in normalized_columns:
        return "reaction"
    if "model_metabolite_id" in normalized_columns:
        return "metabolite"
    if "model_gene_id" in normalized_columns:
        return "gene"
    return ""


def _count_status(rows: list[dict[str, object]], status: str) -> int:
    return sum(1 for row in rows if row.get("mapping_status") == status)


def _mapping_label(total: int, denominator: int, mapped_fraction: float, missing: int = 0, not_checked: int = 0) -> str:
    if total == 0:
        return "no_mappable_ids"
    if denominator == 0:
        if missing and missing >= not_checked:
            return "mapping_review_needed"
        return "not_checked"
    if mapped_fraction >= 0.8:
        return "strong_mapping"
    if mapped_fraction >= 0.5:
        return "usable_with_caution"
    return "mapping_review_needed"


def _mapping_guidance(label: str) -> str:
    return {
        "strong_mapping": "Most checked IDs resolve to the GEM; downstream constraints are likely interpretable.",
        "usable_with_caution": "A useful fraction of IDs resolves, but unmatched IDs may bias omics-derived constraints.",
        "mapping_review_needed": "Most checked IDs do not resolve; review identifier namespaces before interpreting results.",
        "not_checked": "IDs were staged but not checked, usually because the GEM could not be indexed.",
        "no_mappable_ids": "No supported identifier columns were found for this input.",
    }.get(label, "Review the input identifier mapping before interpreting downstream results.")
