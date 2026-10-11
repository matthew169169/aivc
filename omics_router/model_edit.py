"""Model-generation edit provenance helpers.

This module builds a lightweight reaction-level edit index from existing
workflow artifacts. It does not run model-generation algorithms; it only
standardizes what was already generated or staged.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from .constraints import read_csv_records, write_csv, write_json
from .variant_comparison import _compare_model_structures, _parse_model_structure


EDIT_INDEX_SCHEMA_VERSION = "0.1.0"
EDIT_TYPE_PRIORITY = {
    "added": 90,
    "removed": 90,
    "bounds_changed": 80,
    "gpr_changed": 75,
    "evidence_mapped": 50,
    "package_ready_only": 35,
    "unchanged": 0,
}


def safe_edit_variant_segment(value: str) -> str:
    return (
        str(value or "variant")
        .strip()
        .replace("\\", "_")
        .replace("/", "_")
        .replace(":", "_")
        .replace(" ", "_")
        or "variant"
    )[:120]


def normalize_reaction_key(value: Any) -> str:
    text = str(value or "").strip()
    return (
        text.lower()
        .replace("-", "_")
        .replace("__", "_")
        .replace("r_", "", 1)
        .replace("rxn_", "rxn", 1)
    )


def write_model_edit_artifacts(
    *,
    package_dir: str | Path,
    registry_rows: list[dict[str, Any]],
    output_dir: str | Path | None = None,
    edit_record_mode: str = "direct",
) -> dict[str, Any]:
    """Write run-level and per-variant edit provenance artifacts."""

    package = Path(package_dir)
    output = Path(output_dir) if output_dir else package / "workflow_results"
    output.mkdir(parents=True, exist_ok=True)
    manifest_dir = output / "model_edit_manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)

    rows = build_model_edit_reaction_index(package_dir=package, registry_rows=registry_rows)
    for row in rows:
        row["edit_record_mode"] = edit_record_mode
    index_path = output / "model_edit_reaction_index.csv"
    write_csv(index_path, rows)

    by_variant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_variant[str(row.get("variant_id") or "")].append(row)

    manifest_paths: dict[str, str] = {}
    for registry_row in registry_rows:
        variant_id = str(registry_row.get("variant_id") or "")
        variant_rows = by_variant.get(variant_id, [])
        summary = _edit_summary(variant_rows)
        manifest_path = manifest_dir / f"{safe_edit_variant_segment(variant_id)}.json"
        write_json(
            manifest_path,
            {
                "schema_version": EDIT_INDEX_SCHEMA_VERSION,
                "variant_id": variant_id,
                "reference_variant_id": _reference_variant_id(registry_rows),
                "generation_method": registry_row.get("generation_method") or registry_row.get("method") or "",
                "condition": registry_row.get("condition") or "",
                "source_model_path": registry_row.get("source_model_path") or "",
                "target_model_path": _active_model_path(registry_row),
                "evidence_files": _split_semicolon(registry_row.get("supporting_files")),
                "edit_record_mode": edit_record_mode if variant_rows else "unavailable",
                "edit_summary": summary,
                "edit_reaction_index": str(index_path),
            },
        )
        manifest_paths[variant_id] = str(manifest_path)

    return {
        "index_path": str(index_path),
        "manifest_dir": str(manifest_dir),
        "manifest_paths": manifest_paths,
        "row_count": len(rows),
        "edit_record_mode": edit_record_mode if rows else "unavailable",
    }


def attach_edit_artifact_paths(
    registry_rows: list[dict[str, Any]],
    edit_result: dict[str, Any],
    *,
    edit_record_status: str | None = None,
) -> list[dict[str, Any]]:
    manifest_paths = edit_result.get("manifest_paths") if isinstance(edit_result.get("manifest_paths"), dict) else {}
    index_path = str(edit_result.get("index_path") or "")
    output: list[dict[str, Any]] = []
    for row in registry_rows:
        item = dict(row)
        variant_id = str(item.get("variant_id") or "")
        manifest_path = str(manifest_paths.get(variant_id) or "")
        item["edit_manifest_path"] = manifest_path
        item["edit_reaction_index_path"] = index_path
        item["edit_record_status"] = str(edit_record_status or edit_result.get("edit_record_mode") or "direct") if manifest_path else "unavailable"
        output.append(item)
    return output


def refresh_model_edit_artifacts_for_package(
    package_dir: str | Path,
    *,
    edit_record_mode: str = "inferred_legacy",
    update_registry: bool = True,
) -> dict[str, Any]:
    """Refresh edit provenance artifacts for an existing run package.

    This is intentionally metadata-only: it reads existing registry/model/evidence
    files and writes edit provenance for display. It does not run model
    generation, GECKO, solvers, or external network queries.
    """

    package = Path(package_dir)
    workflow = package / "workflow_results"
    registry_path = workflow / "model_variant_registry.csv"
    if not registry_path.exists() or registry_path.stat().st_size == 0:
        return {
            "status": "missing_registry",
            "package_dir": str(package),
            "registry_path": str(registry_path),
            "guidance": "model_variant_registry.csv is missing; edit provenance could not be refreshed.",
            "row_count": 0,
        }
    registry_rows = read_csv_records(registry_path)
    if not registry_rows:
        return {
            "status": "missing_registry_rows",
            "package_dir": str(package),
            "registry_path": str(registry_path),
            "guidance": "model_variant_registry.csv has no rows; edit provenance could not be refreshed.",
            "row_count": 0,
        }
    result = write_model_edit_artifacts(
        package_dir=package,
        registry_rows=registry_rows,
        output_dir=workflow,
        edit_record_mode=edit_record_mode,
    )
    if update_registry:
        updated_rows = attach_edit_artifact_paths(registry_rows, result, edit_record_status=edit_record_mode)
        write_csv(registry_path, updated_rows)
    refresh_manifest = {
        "status": "ready" if int(result.get("row_count") or 0) else "partial",
        "package_dir": str(package),
        "registry_path": str(registry_path),
        "edit_record_mode": edit_record_mode,
        "edit_reaction_index_path": result.get("index_path", ""),
        "edit_manifest_dir": result.get("manifest_dir", ""),
        "row_count": int(result.get("row_count") or 0),
        "guidance": (
            "Edit provenance refreshed from existing run artifacts."
            if int(result.get("row_count") or 0)
            else "No reaction-level edit rows could be inferred from existing artifacts."
        ),
    }
    write_json(workflow / "model_edit_refresh_manifest.json", refresh_manifest)
    return refresh_manifest


def read_model_edit_reaction_index(package_dir: str | Path) -> list[dict[str, str]]:
    path = Path(package_dir) / "workflow_results" / "model_edit_reaction_index.csv"
    if not path.exists() or path.stat().st_size == 0:
        return []
    return read_csv_records(path)


def build_model_edit_reaction_index(
    *,
    package_dir: str | Path,
    registry_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    package = Path(package_dir)
    reference_row = _reference_registry_row(registry_rows)
    reference_model = _path_from_text(_active_model_path(reference_row), package)
    parsed_reference = _parse_model_structure(reference_model)

    kcat_rows = _read_rows(package / "generated_constraints" / "kcat_priors.csv")
    if not kcat_rows:
        kcat_rows = _read_rows(package / "dlkcat_results" / "dlkcat_reaction_kcat_priors.csv")
    capacity_rows = _read_rows(package / "enzyme_results" / "reaction_enzyme_capacity.csv")
    if not capacity_rows:
        capacity_rows = _read_rows(package / "gecko_package" / "reaction_enzyme_capacity.csv")
    expression_rows = _read_rows(package / "generated_constraints" / "reaction_expression_evidence.csv")
    bounds_rows = _read_rows(package / "generated_constraints" / "exchange_bounds.csv")
    consensus_rows = _read_rows(package / "generated_constraints" / "multi_omics_consensus_reaction_evidence.csv")

    kcat_by_key = _index_rows_by_reaction(kcat_rows, alias_map=_kegg_reaction_alias_map(package))
    capacity_by_key = _index_rows_by_reaction(capacity_rows)
    expression_by_key = _index_rows_by_reaction(expression_rows)
    bounds_by_key = _index_rows_by_reaction(bounds_rows)
    consensus_by_key = _index_rows_by_reaction(consensus_rows)

    output: list[dict[str, Any]] = []
    for registry_row in registry_rows:
        variant_id = str(registry_row.get("variant_id") or "")
        if not variant_id or variant_id == "no_model_generation_selected":
            continue
        target_model = _path_from_text(_active_model_path(registry_row), package)
        parsed_target = _parse_model_structure(target_model)
        comparison = _compare_model_structures(variant_id, parsed_reference, parsed_target)
        reaction_ids = sorted(set(parsed_reference.reactions) | set(parsed_target.reactions))
        if not reaction_ids and parsed_reference.reactions:
            reaction_ids = sorted(parsed_reference.reactions)
        method = str(registry_row.get("generation_method") or registry_row.get("method") or "")
        is_baseline = method == "baseline_gem" or variant_id == str(reference_row.get("variant_id") or "")
        condition = str(registry_row.get("condition") or "")
        variant_artifacts = _variant_artifact_rows(package, registry_row)
        variant_artifacts_by_key = _index_variant_artifact_rows(variant_artifacts)
        for reaction_id in reaction_ids:
            key = normalize_reaction_key(reaction_id)
            reference_reaction = parsed_reference.reactions.get(reaction_id, {})
            target_reaction = parsed_target.reactions.get(reaction_id, {})
            edit_type = _structural_edit_type(reaction_id, comparison)
            evidence_files: set[str] = set()
            evidence_count = 0
            transcriptomics_rows = [] if is_baseline else _matching_condition_rows(expression_by_key.get(key, []), condition, "expression")
            transcriptomics = bool(transcriptomics_rows)
            if transcriptomics:
                edit_type = _raise_edit_type(edit_type, "evidence_mapped")
                evidence_files.add("generated_constraints/reaction_expression_evidence.csv")
                evidence_count += len(transcriptomics_rows)
            bounds_matches = [] if is_baseline else _matching_condition_rows(bounds_by_key.get(key, []), condition, "bounds")
            condition_bounds = bool(bounds_matches)
            if condition_bounds:
                edit_type = _raise_edit_type(edit_type, "bounds_changed")
                evidence_files.add("generated_constraints/exchange_bounds.csv")
                evidence_count += len(bounds_matches)
            consensus_rows_for_key = [] if is_baseline else _matching_condition_rows(consensus_by_key.get(key, []), condition, "consensus")
            variant_artifact_matches = [] if is_baseline else variant_artifacts_by_key.get(key, [])
            consensus = bool(consensus_rows_for_key or variant_artifact_matches)
            annotation_mapped = bool(variant_artifact_matches) or any(_valid_annotation_evidence_row(row) for row in consensus_rows_for_key)
            if consensus:
                edit_type = _raise_edit_type(edit_type, "evidence_mapped")
                evidence_files.add("generated_constraints/multi_omics_consensus_reaction_evidence.csv")
                evidence_count += len(consensus_rows_for_key) + len(variant_artifact_matches)
            kcat_rows_for_key = [] if is_baseline else kcat_by_key.get(key, [])
            kcat = bool(kcat_rows_for_key)
            if kcat:
                edit_type = _raise_edit_type(edit_type, "package_ready_only" if method == "enzyme_gecko" else "evidence_mapped")
                evidence_files.add("generated_constraints/kcat_priors.csv")
                evidence_count += len(kcat_rows_for_key)
            capacity = capacity_by_key.get(key, [])
            proteomics_mapped = bool(capacity)
            if proteomics_mapped:
                edit_type = _raise_edit_type(edit_type, "package_ready_only" if method == "enzyme_gecko" and not capacity else "evidence_mapped")
                if capacity:
                    evidence_files.add("enzyme_results/reaction_enzyme_capacity.csv")
                evidence_count += len(capacity)
            capacity_status = "available" if capacity else ("package-ready only" if method == "enzyme_gecko" and kcat else "")
            row = {
                "variant_id": variant_id,
                "reaction_id": reaction_id,
                "normalized_reaction_id": key,
                "edit_type": edit_type,
                "reference_present": reaction_id in parsed_reference.reactions,
                "target_present": reaction_id in parsed_target.reactions,
                "lower_bound_before": reference_reaction.get("lower_bound", ""),
                "lower_bound_after": target_reaction.get("lower_bound", ""),
                "upper_bound_before": reference_reaction.get("upper_bound", ""),
                "upper_bound_after": target_reaction.get("upper_bound", ""),
                "proteomics_mapped": proteomics_mapped,
                "kcat_mapped": kcat,
                "transcriptomics_mapped": transcriptomics,
                "condition_bounds_applied": condition_bounds,
                "annotation_mapped": annotation_mapped,
                "capacity_status": (capacity_status or "reaction-level unavailable") if method == "enzyme_gecko" else capacity_status,
                "evidence_source_files": ";".join(sorted(evidence_files)),
                "evidence_row_count": evidence_count,
                "mapping_status": "mapped" if evidence_count or edit_type != "unchanged" else "not mapped",
            }
            output.append(row)
    _apply_case_paper_evidence_overlay(package, output)
    return output


def _apply_case_paper_evidence_overlay(package: Path, edit_rows: list[dict[str, Any]]) -> None:
    """Merge paper-reported gene-to-reaction evidence into display edit rows.

    The overlay is an evidence layer only. It must never create structural
    changes, condition bounds, kcat, proteomics, or enzyme-capacity values.
    """

    overlay_path = package / "case_study" / "paper_evidence_reaction_overlay.csv"
    if not overlay_path.exists() or overlay_path.stat().st_size == 0:
        return
    overlay_rows = [
        row
        for row in _read_rows(overlay_path)
        if str(row.get("mapping_status") or "").strip().lower() in {"mapped", "paper_evidence_mapped"}
        and str(row.get("reaction_id") or "").strip()
    ]
    if not overlay_rows:
        return
    overlay_by_variant_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in overlay_rows:
        variant_id = str(row.get("target_variant_id") or row.get("variant_id") or "paper_evidence_context__lac_transition").strip()
        key = normalize_reaction_key(row.get("reaction_id"))
        if variant_id and key:
            overlay_by_variant_key[(variant_id, key)].append(row)
    for row in edit_rows:
        variant_id = str(row.get("variant_id") or "").strip()
        key = str(row.get("normalized_reaction_id") or normalize_reaction_key(row.get("reaction_id")))
        evidence_rows = overlay_by_variant_key.get((variant_id, key), [])
        if not evidence_rows:
            continue
        row["transcriptomics_mapped"] = True
        row["annotation_mapped"] = True
        if str(row.get("edit_type") or "unchanged") == "unchanged":
            row["edit_type"] = "evidence_mapped"
        source_files = set(_split_semicolon(row.get("evidence_source_files")))
        source_files.add("case_study/paper_evidence_reaction_overlay.csv")
        row["evidence_source_files"] = ";".join(sorted(source_files))
        row["evidence_row_count"] = _safe_int(row.get("evidence_row_count")) + len(evidence_rows)
        row["mapping_status"] = "paper_evidence_mapped"


def build_model_edit_diff_index(
    *,
    reference_variant_id: str,
    target_variant_id: str,
    edit_rows: list[dict[str, Any]],
    fallback_reaction_diff_index: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    by_variant: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in edit_rows:
        variant_id = str(row.get("variant_id") or "")
        key = str(row.get("normalized_reaction_id") or normalize_reaction_key(row.get("reaction_id")))
        if variant_id and key:
            by_variant[variant_id][key] = dict(row)
    ref_rows = by_variant.get(reference_variant_id, {})
    target_rows = by_variant.get(target_variant_id, {})
    keys = set(ref_rows) | set(target_rows)
    mode = _edit_record_mode_from_rows(list(ref_rows.values()) + list(target_rows.values()))
    if not keys:
        for row in fallback_reaction_diff_index or []:
            key = str(row.get("normalized_reaction_id") or normalize_reaction_key(row.get("reaction_id")))
            if key:
                keys.add(key)
                target_rows[key] = _fallback_edit_row(target_variant_id, row)
        mode = "inferred_legacy"
    output: list[dict[str, Any]] = []
    for key in sorted(keys):
        reference = ref_rows.get(key, {})
        target = target_rows.get(key, {})
        reaction_id = str(target.get("reaction_id") or reference.get("reaction_id") or key)
        edit_type = _pair_edit_type(reference, target)
        evidence_flags = _evidence_flags(reference, target)
        reference_evidence_flags = _row_evidence_flags(reference)
        target_evidence_flags = _row_evidence_flags(target)
        bounds_change = {
            "lower_before": reference.get("lower_bound_before") or target.get("lower_bound_before") or "",
            "lower_after": target.get("lower_bound_after") or reference.get("lower_bound_after") or "",
            "upper_before": reference.get("upper_bound_before") or target.get("upper_bound_before") or "",
            "upper_after": target.get("upper_bound_after") or reference.get("upper_bound_after") or "",
        }
        output.append(
            {
                "reaction_id": reaction_id,
                "normalized_reaction_id": key,
                "edit_type": edit_type,
                "reference_edit_type": reference.get("edit_type") or "unchanged",
                "target_edit_type": target.get("edit_type") or "unchanged",
                "reference_variant_id": reference_variant_id,
                "target_variant_id": target_variant_id,
                "reference_present": _truthy(reference.get("target_present") if reference else reference.get("reference_present")),
                "target_present": _truthy(target.get("target_present")) if target else False,
                "evidence_flags": evidence_flags,
                "reference_evidence_flags": reference_evidence_flags,
                "target_evidence_flags": target_evidence_flags,
                "bounds_change": bounds_change,
                "capacity_status": _display_capacity_status(target.get("capacity_status") or reference.get("capacity_status") or ""),
                "reference_capacity_status": _display_capacity_status(reference.get("capacity_status") or ""),
                "target_capacity_status": _display_capacity_status(target.get("capacity_status") or ""),
                "edit_record_mode": mode,
                "evidence_source_files": ";".join(
                    sorted(set(_split_semicolon(reference.get("evidence_source_files")) + _split_semicolon(target.get("evidence_source_files"))))
                ),
                "evidence_row_count": _safe_int(reference.get("evidence_row_count")) + _safe_int(target.get("evidence_row_count")),
                "mapping_status": target.get("mapping_status") or reference.get("mapping_status") or "",
            }
        )
    return output


def overlay_edit_graph(
    graph: dict[str, Any],
    *,
    side: str,
    diff_index: list[dict[str, Any]],
) -> dict[str, Any]:
    diff_by_key = {str(row.get("normalized_reaction_id") or ""): row for row in diff_index if row.get("normalized_reaction_id")}
    output = dict(graph or {})
    nodes = []
    for raw in graph.get("nodes") if isinstance(graph.get("nodes"), list) else []:
        if not isinstance(raw, dict):
            continue
        node = dict(raw)
        node_type = str(node.get("node_type") or node.get("type") or "").lower()
        reaction_key = normalize_reaction_key(node.get("reaction_id") or node.get("id") or node.get("label"))
        diff = diff_by_key.get(reaction_key, {}) if node_type == "reaction" else {}
        if diff:
            node.update(
                {
                    "edit_type": _side_edit_type(diff, side),
                    "evidence_flags": _side_evidence_flags(diff, side),
                    "bounds_change": diff.get("bounds_change", {}),
                    "is_ghost": _side_is_ghost(diff, side),
                    "capacity_status": _side_capacity_status(diff, side),
                    "edit_tooltip": _edit_tooltip(diff, side),
                    "source_variant_id": diff.get("reference_variant_id") if side == "reference" else diff.get("target_variant_id"),
                }
            )
        nodes.append(node)
    links = []
    for raw in graph.get("links") if isinstance(graph.get("links"), list) else []:
        if not isinstance(raw, dict):
            continue
        link = dict(raw)
        reaction_key = normalize_reaction_key(link.get("reaction_id"))
        diff = diff_by_key.get(reaction_key, {}) if reaction_key else {}
        if not diff:
            source_key = normalize_reaction_key(link.get("source"))
            target_key = normalize_reaction_key(link.get("target"))
            diff = diff_by_key.get(source_key, {}) or diff_by_key.get(target_key, {})
        if diff:
            link.update(
                {
                    "edit_type": _side_edit_type(diff, side),
                    "evidence_flags": _side_evidence_flags(diff, side),
                    "is_ghost": _side_is_ghost(diff, side),
                }
            )
        links.append(link)
    output["nodes"] = nodes
    output["links"] = links
    output["legend"] = _edit_graph_legend()
    summary = output.get("summary") if isinstance(output.get("summary"), dict) else {}
    output["summary"] = {**summary, "edit_overlay": "model_edit", "edit_record_count": len(diff_index)}
    return output


def edit_context_summary(diff_index: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = defaultdict(int)
    evidence_counts: dict[str, int] = defaultdict(int)
    modes: dict[str, int] = defaultdict(int)
    for row in diff_index:
        counts[str(row.get("edit_type") or "unchanged")] += 1
        modes[str(row.get("edit_record_mode") or "unknown")] += 1
        for flag in row.get("evidence_flags") if isinstance(row.get("evidence_flags"), list) else []:
            evidence_counts[str(flag)] += 1
    return {
        "status": "ready" if diff_index else "not generated",
        "edit_type_counts": dict(counts),
        "evidence_counts": dict(evidence_counts),
        "edit_record_modes": dict(modes),
        "reaction_count": len(diff_index),
    }


def _edit_record_mode_from_rows(rows: list[dict[str, Any]]) -> str:
    modes = {str(row.get("edit_record_mode") or "").strip() for row in rows if str(row.get("edit_record_mode") or "").strip()}
    if not modes:
        return "direct" if rows else "inferred_legacy"
    if "direct" in modes and len(modes) == 1:
        return "direct"
    if "direct" in modes:
        return "mixed"
    if "inferred_legacy" in modes:
        return "inferred_legacy"
    return sorted(modes)[0]


def _reference_registry_row(registry_rows: list[dict[str, Any]]) -> dict[str, Any]:
    return next((row for row in registry_rows if "baseline" in str(row.get("variant_id") or "").lower()), registry_rows[0] if registry_rows else {})


def _reference_variant_id(registry_rows: list[dict[str, Any]]) -> str:
    return str(_reference_registry_row(registry_rows).get("variant_id") or "")


def _active_model_path(row: dict[str, Any]) -> str:
    for key in ("context_model_sbml", "primary_model_path", "source_model_path"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _path_from_text(value: str, package: Path) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    path = Path(text)
    if not path.is_absolute():
        path = package / path
    return path


def _split_semicolon(value: Any) -> list[str]:
    return [part.strip() for part in str(value or "").split(";") if part.strip()]


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    return read_csv_records(path)


def _reaction_id_from_row(row: dict[str, Any]) -> str:
    for key in (
        "reaction_id",
        "model_reaction_id",
        "target_reaction_id",
        "reference_reaction_id",
        "reaction",
        "bigg_reaction",
        "kegg_reaction",
        "target_id",
        "id",
    ):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _index_rows_by_reaction(
    rows: list[dict[str, Any]],
    *,
    alias_map: dict[str, list[str]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = defaultdict(list)
    aliases = alias_map or {}
    for row in rows:
        reaction_id = _reaction_id_from_row(row)
        key = normalize_reaction_key(reaction_id)
        keys = [key] if key else []
        keys.extend(aliases.get(key, []))
        seen: set[str] = set()
        for item_key in keys:
            if item_key and item_key not in seen:
                output[item_key].append(row)
                seen.add(item_key)
    return output


def _kegg_reaction_alias_map(package: Path) -> dict[str, list[str]]:
    """Map KEGG reaction ids to model reaction keys when a curated sidecar exists."""

    candidates = [
        package / "visualization" / "kegg_pathway_maps" / "reaction_kegg_pathway_assignment.csv",
        package / "case_study" / "reaction_kegg_pathway_assignment.csv",
    ]
    if "shewanella" in str(package).lower():
        candidates.append(
            package.parent.parent
            / "case_studies"
            / "shewanella_gecko_case_study"
            / "visualization"
            / "kegg_pathway_maps"
            / "reaction_kegg_pathway_assignment.csv"
        )
    mapping: dict[str, list[str]] = defaultdict(list)
    for path in candidates:
        if not path.exists() or path.stat().st_size == 0:
            continue
        for row in _read_rows(path):
            kegg_key = normalize_reaction_key(row.get("kegg_reaction_id") or row.get("target_id"))
            model_key = normalize_reaction_key(row.get("reaction_id") or row.get("model_reaction_id") or row.get("cobra_reaction_id"))
            if kegg_key and model_key and model_key not in mapping[kegg_key]:
                mapping[kegg_key].append(model_key)
    return dict(mapping)


def _condition_matches(row: dict[str, Any], condition: str) -> bool:
    wanted = str(condition or "").strip().lower()
    if not wanted or wanted == "all":
        return True
    row_condition = str(row.get("condition") or row.get("target_condition") or row.get("condition_group") or "").strip().lower()
    return not row_condition or row_condition == "all" or row_condition == wanted


def _numeric_positive(value: Any) -> bool:
    try:
        return float(str(value or "").strip()) > 0
    except Exception:
        return False


def _valid_expression_evidence_row(row: dict[str, Any]) -> bool:
    status_text = " ".join(
        str(row.get(key) or "").strip().lower()
        for key in ("status", "evidence", "transcript_evidence", "protein_evidence", "evidence_source")
    )
    blocked_tokens = {"no_gpr", "no data", "no_data", "none", "unknown", "not_mapped", "unmapped"}
    if any(token in status_text for token in blocked_tokens):
        return False
    return (
        _numeric_positive(row.get("measured_gene_count"))
        or _numeric_positive(row.get("gene_coverage"))
        or _numeric_positive(row.get("reaction_score"))
        or bool(str(row.get("measured_genes") or "").strip())
    )


def _valid_annotation_evidence_row(row: dict[str, Any]) -> bool:
    status_text = " ".join(
        str(row.get(key) or "").strip().lower()
        for key in ("status", "evidence", "transcript_evidence", "protein_evidence", "evidence_source", "recommendation")
    )
    blocked_tokens = {"no_gpr", "no data", "no_data", "none", "unknown", "not_mapped", "unmapped"}
    if any(token in status_text for token in blocked_tokens):
        return False
    return (
        _numeric_positive(row.get("measured_gene_count"))
        or _numeric_positive(row.get("gene_coverage"))
        or _numeric_positive(row.get("reaction_score"))
        or bool(str(row.get("measured_genes") or "").strip())
        or bool(str(row.get("gpr_rule") or "").strip())
    )


def _valid_bounds_row(row: dict[str, Any]) -> bool:
    return any(str(row.get(key) or "").strip() for key in ("lower_bound", "upper_bound", "lower_bound_after", "upper_bound_after", "bound_type"))


def _matching_condition_rows(rows: list[dict[str, Any]], condition: str, evidence_kind: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        if not _condition_matches(row, condition):
            continue
        if evidence_kind == "bounds":
            if _valid_bounds_row(row):
                output.append(row)
        elif evidence_kind == "consensus":
            if _valid_annotation_evidence_row(row):
                output.append(row)
        else:
            if _valid_expression_evidence_row(row):
                output.append(row)
    return output


def _variant_artifact_rows(package: Path, registry_row: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path_text in _split_semicolon(registry_row.get("supporting_files")) + _split_semicolon(registry_row.get("generated_files")):
        path = _path_from_text(path_text, package)
        if not path or not path.exists() or path.suffix.lower() != ".csv":
            continue
        name = path.name.lower()
        if any(token in name for token in ("context_keep", "context_delete", "context_penalize", "context_core", "reaction_policy")):
            for row in _read_rows(path):
                item = dict(row)
                item["__source_file"] = str(path)
                rows.append(item)
    return rows


def _index_variant_artifact_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return _index_rows_by_reaction(rows)


def _has_condition_row(rows: list[dict[str, Any]], condition: str) -> bool:
    if not rows:
        return False
    wanted = str(condition or "").strip().lower()
    if not wanted or wanted == "all":
        return True
    for row in rows:
        row_condition = str(row.get("condition") or row.get("target_condition") or row.get("condition_group") or "").strip().lower()
        if not row_condition or row_condition == "all" or row_condition == wanted:
            return True
    return False


def _structural_edit_type(reaction_id: str, comparison: dict[str, Any]) -> str:
    if reaction_id in comparison.get("added_reactions", set()):
        return "added"
    if reaction_id in comparison.get("removed_reactions", set()):
        return "removed"
    if reaction_id in comparison.get("changed_bounds", set()):
        return "bounds_changed"
    if reaction_id in comparison.get("changed_gpr", set()):
        return "gpr_changed"
    return "unchanged"


def _raise_edit_type(current: str, candidate: str) -> str:
    return candidate if EDIT_TYPE_PRIORITY.get(candidate, 0) > EDIT_TYPE_PRIORITY.get(current, 0) else current


def _edit_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = defaultdict(int)
    evidence_rows = 0
    for row in rows:
        counts[str(row.get("edit_type") or "unchanged")] += 1
        evidence_rows += _safe_int(row.get("evidence_row_count"))
    return {"reaction_count": len(rows), "edit_type_counts": dict(counts), "evidence_row_count": evidence_rows}


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"} or value is True


def _safe_int(value: Any) -> int:
    try:
        return int(float(str(value or "").strip()))
    except Exception:
        return 0


def _fallback_edit_row(variant_id: str, row: dict[str, Any]) -> dict[str, Any]:
    change_type = str(row.get("change_type") or "unchanged").replace("-", "_")
    return {
        "variant_id": variant_id,
        "reaction_id": row.get("reaction_id") or row.get("target_reaction_id") or row.get("reference_reaction_id") or "",
        "normalized_reaction_id": row.get("normalized_reaction_id") or normalize_reaction_key(row.get("reaction_id")),
        "edit_type": change_type if change_type in EDIT_TYPE_PRIORITY else "evidence_mapped" if row.get("evidence_badges") else "unchanged",
        "reference_present": (row.get("definition_diff") or {}).get("reference_present") if isinstance(row.get("definition_diff"), dict) else row.get("reference_present", ""),
        "target_present": (row.get("definition_diff") or {}).get("target_present") if isinstance(row.get("definition_diff"), dict) else row.get("target_present", ""),
        "proteomics_mapped": "proteomics" in (row.get("evidence_badges") if isinstance(row.get("evidence_badges"), list) else []),
        "kcat_mapped": "kcat" in (row.get("evidence_badges") if isinstance(row.get("evidence_badges"), list) else []),
        "capacity_status": (row.get("constraint_evidence") or {}).get("enzyme_capacity_status", "") if isinstance(row.get("constraint_evidence"), dict) else "",
        "mapping_status": "inferred",
    }


def _pair_edit_type(reference: dict[str, Any], target: dict[str, Any]) -> str:
    target_type = str(target.get("edit_type") or "")
    reference_type = str(reference.get("edit_type") or "")
    if target_type and target_type != "unchanged":
        return target_type
    if reference_type in {"removed", "added", "bounds_changed", "gpr_changed"}:
        return reference_type
    if target.get("target_present") is False or str(target.get("target_present")).lower() == "false":
        return "removed"
    return target_type or reference_type or "unchanged"


def _evidence_flags(reference: dict[str, Any], target: dict[str, Any]) -> list[str]:
    flags = []
    reference_flags = set(_row_evidence_flags(reference))
    target_flags = set(_row_evidence_flags(target))
    for name, key in (
        ("proteomics", "proteomics_mapped"),
        ("kcat", "kcat_mapped"),
        ("transcriptomics", "transcriptomics_mapped"),
        ("condition_bounds", "condition_bounds_applied"),
        ("annotation", "annotation_mapped"),
    ):
        if name in reference_flags or name in target_flags:
            flags.append(name)
    if _capacity_is_reaction_level_available(reference.get("capacity_status")) or _capacity_is_reaction_level_available(target.get("capacity_status")):
        flags.append("capacity")
    return flags


def _row_evidence_flags(row: dict[str, Any]) -> list[str]:
    flags = []
    for name, key in (
        ("proteomics", "proteomics_mapped"),
        ("kcat", "kcat_mapped"),
        ("transcriptomics", "transcriptomics_mapped"),
        ("condition_bounds", "condition_bounds_applied"),
        ("annotation", "annotation_mapped"),
    ):
        if _truthy(row.get(key)):
            flags.append(name)
    if _capacity_is_reaction_level_available(row.get("capacity_status")):
        flags.append("capacity")
    return flags


def _capacity_is_reaction_level_available(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    unavailable_tokens = (
        "reaction-level unavailable",
        "unavailable",
        "not available",
        "not_available",
        "not generated",
        "not_generated",
        "external pending",
        "external ecmodel pending",
        "package-ready",
        "package ready",
        "package_ready",
        "pending",
        "missing",
        "none",
        "not applicable",
        "not_applicable",
    )
    if any(token in text for token in unavailable_tokens):
        return False
    return text in {"available", "ready", "capacity_available", "reaction_level_available"} or "available" in text


def _display_capacity_status(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if _capacity_is_reaction_level_available(text):
        return text
    lowered = text.lower()
    if "package" in lowered:
        return "package-ready only"
    if "external" in lowered or "pending" in lowered:
        return "external pending"
    if "not applicable" in lowered or "not_applicable" in lowered:
        return "not applicable"
    if "reaction-level" in lowered or "unavailable" in lowered or "not available" in lowered:
        return "reaction-level unavailable"
    if "not generated" in lowered or "not_generated" in lowered or "missing" in lowered:
        return "not generated"
    return text


def _side_edit_type(diff: dict[str, Any], side: str) -> str:
    edit_type = str(diff.get("target_edit_type" if side == "target" else "reference_edit_type") or diff.get("edit_type") or "unchanged")
    pair_edit_type = str(diff.get("edit_type") or "unchanged")
    if edit_type == "removed" and side == "target":
        return "removed"
    if edit_type == "added" and side == "reference":
        return "removed"
    if pair_edit_type == "added" and side == "reference":
        return "removed"
    if pair_edit_type == "removed" and side == "target":
        return "removed"
    return edit_type


def _side_is_ghost(diff: dict[str, Any], side: str) -> bool:
    if side == "reference" and str(diff.get("edit_type")) == "added":
        return True
    if side == "target" and str(diff.get("edit_type")) == "removed":
        return True
    return False


def _edit_tooltip(diff: dict[str, Any]) -> str:
    flags = diff.get("evidence_flags") if isinstance(diff.get("evidence_flags"), list) else []
    parts = [str(diff.get("edit_type") or "unchanged")]
    if flags:
        parts.append("evidence: " + ", ".join(map(str, flags)))
    capacity = str(diff.get("capacity_status") or "").strip()
    if capacity:
        parts.append("capacity: " + capacity)
    return " · ".join(parts)


def _side_evidence_flags(diff: dict[str, Any], side: str) -> list[str]:
    key = "target_evidence_flags" if side == "target" else "reference_evidence_flags"
    flags = diff.get(key)
    if isinstance(flags, list):
        return [str(flag) for flag in flags if str(flag).strip()]
    return []


def _side_capacity_status(diff: dict[str, Any], side: str) -> str:
    key = "target_capacity_status" if side == "target" else "reference_capacity_status"
    return str(diff.get(key) or "").strip()


def _edit_tooltip(diff: dict[str, Any], side: str) -> str:  # type: ignore[no-redef]
    flags = _side_evidence_flags(diff, side)
    parts = [str(_side_edit_type(diff, side) or "unchanged")]
    if flags:
        parts.append("evidence: " + ", ".join(map(str, flags)))
    capacity = _side_capacity_status(diff, side)
    if capacity:
        parts.append("capacity: " + capacity)
    return " | ".join(parts)


def _edit_graph_legend() -> list[dict[str, Any]]:
    return [
        {"status": "added", "label": "added reaction", "color": "#22c55e"},
        {"status": "removed", "label": "removed / ghost reaction", "color": "#cbd5e1"},
        {"status": "bounds_changed", "label": "bounds changed", "color": "#f97316"},
        {"status": "evidence_mapped", "label": "proteomics / kcat evidence", "color": "#2563eb"},
        {"status": "package_ready_only", "label": "package-ready only", "color": "#8b5cf6"},
        {"status": "unchanged", "label": "unchanged", "color": "#64748b"},
    ]
