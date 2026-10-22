"""Export Omics-GEM interactive maps as SAMMI-native session JSON."""

from __future__ import annotations

import html
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constraints import read_csv_records, relocate_package_path, write_csv, write_json
from .sammi_interactive_render import build_sammi_interactive_render
from .sammi_visualization import sammi_vendor_status


@dataclass(slots=True)
class SammiNativeExportResult:
    """Result returned after a SAMMI-native session export is written."""

    status: str
    message: str
    output_dir: Path
    files: dict[str, str]
    manifest: dict[str, Any]


def build_sammi_native_export(
    package_dir: str | Path,
    *,
    variant_id: str = "",
    grouping_mode: str = "subsystem",
    overlay_source: str = "none",
    reaction_filter: list[str] | str | None = None,
    subsystem_filter: list[str] | str | None = None,
    ml_profile_id: str = "",
    top_n: int = 120,
    include_currency_metabolites: bool = False,
) -> SammiNativeExportResult:
    """Build a SAMMI-native JSON session from the interactive graph output.

    SAMMI standalone loads saved sessions through its "Load SAMMI Model"
    control. The generated JSON mirrors the fields written by SAMMI's own
    download function closely enough for a focused, read-only network session.
    """

    render = build_sammi_interactive_render(
        package_dir,
        variant_id=variant_id,
        grouping_mode=grouping_mode,
        overlay_source=overlay_source,
        reaction_filter=reaction_filter,
        subsystem_filter=subsystem_filter,
        ml_profile_id=ml_profile_id,
        top_n=top_n,
        include_currency_metabolites=include_currency_metabolites,
    )
    output = render.output_dir
    files = native_export_file_paths(output)
    graph_path = output / "network_graph.json"
    graph = _read_json(graph_path)

    if not graph or graph.get("status") not in {"completed", "needs_filtering"}:
        status = str(graph.get("status") or render.status or "skipped")
        message = str(graph.get("message") or render.message or "Interactive graph was not available for native export.")
        session = empty_sammi_session(str(variant_id or graph.get("variant_id") or "sammi_export"))
    else:
        status = str(graph.get("status") or render.status or "completed")
        message = (
            "SAMMI-native session JSON generated. Open local SAMMI and use Load SAMMI Model to select this JSON."
            if status == "completed"
            else str(graph.get("message") or "Graph needs filtering before SAMMI export can show content.")
        )
        session = graph_to_sammi_session(graph)

    return write_native_export_outputs(output, files, graph, session, render.manifest, status=status, message=message)


def list_sammi_native_exports(package_dir: str | Path, *, variant_id: str = "") -> dict[str, Any]:
    """Discover previously generated SAMMI-native sessions for a run package."""

    package = Path(package_dir)
    root = package / "visualization_results" / "sammi"
    if not root.exists():
        return {
            "status": "empty",
            "message": "No SAMMI visualization outputs were found for this run.",
            "variant_id": variant_id,
            "count": 0,
            "latest": None,
            "exports": [],
        }

    rows: list[dict[str, Any]] = []
    for output in sorted(path for path in root.iterdir() if path.is_dir()):
        manifest_path = output / "sammi_native_export_manifest.json"
        session_path = output / "sammi_native_session.json"
        if not manifest_path.exists() and not session_path.exists():
            continue
        manifest = _read_json(manifest_path)
        source_manifest = _read_json(output / "sammi_package_manifest.json")
        graph = _read_json(output / "network_graph.json")
        check = _read_json(output / "sammi_native_export_check.json")
        summary = _first_csv_row(output / "sammi_native_export_summary.csv")
        discovered_variant = str(
            manifest.get("variant_id")
            or source_manifest.get("variant_id")
            or graph.get("variant_id")
            or output.name
        )
        if variant_id and discovered_variant != variant_id:
            continue
        files = manifest.get("files", {}) if isinstance(manifest.get("files"), dict) else {}
        launch_path = relocate_package_path(package, files.get("launch")) or output / "sammi_native_launch.html"
        check_path = relocate_package_path(package, files.get("check_json")) or output / "sammi_native_export_check.json"
        session_file = relocate_package_path(package, files.get("session")) or session_path
        modified_at = _latest_mtime(
            [
                manifest_path,
                session_file,
                launch_path,
                check_path,
                output / "sammi_native_export_summary.csv",
            ]
        )
        graph_filters = graph.get("filters", {}) if isinstance(graph.get("filters"), dict) else {}
        manifest_check = manifest.get("native_export_check", {}) if isinstance(manifest.get("native_export_check"), dict) else {}
        vendor = manifest.get("vendored_sammi", {}) if isinstance(manifest.get("vendored_sammi"), dict) else {}
        checker_status = str(check.get("status") or manifest_check.get("status") or "")
        local_sammi_index = str(check.get("vendored_sammi_index_path") or vendor.get("vendored_index_path") or "")
        rows.append(
            {
                "variant_id": discovered_variant,
                "status": str(manifest.get("status") or summary.get("status") or "unknown"),
                "message": str(manifest.get("message") or summary.get("message") or ""),
                "checker_status": checker_status,
                "checker_message": str(check.get("message") or ""),
                "overlay_source": str(source_manifest.get("overlay_source") or ""),
                "overlay_status": str(source_manifest.get("overlay_status") or manifest.get("source_overlay_status") or ""),
                "reaction_filter": str(source_manifest.get("filter_raw_reaction_ids") or ";".join(graph_filters.get("reaction_filter", []) or [])),
                "subsystem_filter": ";".join(str(item) for item in graph_filters.get("subsystem_filter", []) or []),
                "node_count": _safe_int(check.get("node_count") or summary.get("node_count") or 0),
                "link_count": _safe_int(check.get("link_count") or summary.get("link_count") or 0),
                "reaction_node_count": _safe_int(check.get("reaction_node_count") or 0),
                "metabolite_node_count": _safe_int(check.get("metabolite_node_count") or 0),
                "vendored_sammi_available": _as_bool(check.get("vendored_sammi_available") or summary.get("vendored_sammi_available")),
                "local_sammi_index_path": local_sammi_index,
                "session_path": str(session_file),
                "launch_html_path": str(launch_path),
                "manifest_path": str(manifest_path),
                "check_json_path": str(check_path),
                "check_markdown_path": str(files.get("check_markdown") or output / "sammi_native_export_check.md"),
                "output_dir": str(output),
                "modified_at": modified_at,
                "modified_at_iso": _iso_time(modified_at),
                "session_exists": session_file.exists(),
                "launch_exists": launch_path.exists(),
                "check_exists": check_path.exists(),
            }
        )
    rows.sort(key=lambda row: float(row.get("modified_at") or 0), reverse=True)
    status = "ok" if rows else "empty"
    return {
        "status": status,
        "message": "SAMMI native exports found." if rows else "No SAMMI native session has been exported for this selection yet.",
        "variant_id": variant_id,
        "count": len(rows),
        "latest": rows[0] if rows else None,
        "exports": rows,
    }


def graph_to_sammi_session(graph: dict[str, Any]) -> dict[str, Any]:
    """Convert Omics-GEM graph JSON to a SAMMI saved-session object."""

    variant_id = _safe_session_key(str(graph.get("variant_id") or "omics_gem_map"))
    source_nodes = [dict(node) for node in graph.get("nodes", []) if isinstance(node, dict)]
    source_links = [dict(link) for link in graph.get("links", []) if isinstance(link, dict)]
    id_to_index = {str(node.get("id")): index for index, node in enumerate(source_nodes) if node.get("id")}

    nodes: list[dict[str, Any]] = []
    reaction_values: dict[str, float] = {}
    reaction_sizes: dict[str, float] = {}
    metabolites_by_reaction: dict[str, dict[str, int]] = {}

    for index, node in enumerate(source_nodes):
        node_type = str(node.get("node_type") or "")
        is_reaction = node_type == "reaction"
        value = _to_float(node.get("overlay_value"))
        size = _to_float(node.get("overlay_size"))
        short_label = str(node.get("label") or node.get("id") or f"node_{index}")
        display_name = str(node.get("name") or short_label) if is_reaction else short_label
        sammi_node = {
            "id": short_label,
            "name": display_name,
            "class": short_label,
            "index": index,
            "group": 1 if is_reaction else 2,
            "secondary": False,
            "flux": value if is_reaction and value is not None and not math.isnan(value) else None,
            "size": _scaled_size(size, is_reaction),
            "trap": -1,
            "concentration": None,
            "bezi": [None, None, None, None],
            "labelshift": [0, 0],
            "grouping": [],
            "reversed": 1,
            "width": None,
            "isfixed": False,
            "weight": 1.01,
            "fx": None,
            "fy": None,
            "x": _layout_x(index),
            "y": _layout_y(index),
            "vx": 0,
            "vy": 0,
            "selected": False,
            "previouslySelected": False,
            "labelarr": _label_parts(short_label),
            "compartment": str(node.get("compartment") or ""),
            "subsystem": str(node.get("subsystem") or node.get("group_label") or ""),
            "notes": {
                "omics_gem_node_id": str(node.get("id") or ""),
                "omics_gem_node_type": node_type,
                "overlay_source": str(node.get("overlay_source") or ""),
                "semantic_type": str(node.get("semantic_type") or ""),
                "overlay_color": str(node.get("overlay_color") or ""),
                "warning_flag": _as_bool(node.get("warning_flag")),
                "readiness_label": str(node.get("readiness_label") or ""),
                "candidate_action": str(node.get("candidate_action") or ""),
                "warning_reasons": str(node.get("warning_reasons") or ""),
            },
        }
        if is_reaction:
            sammi_node["metabolites"] = {}
            if value is not None and not math.isnan(value):
                reaction_values[sammi_node["id"]] = value
            if size is not None and not math.isnan(size):
                reaction_sizes[sammi_node["id"]] = max(1.0, size)
        nodes.append(sammi_node)

    links: list[dict[str, Any]] = []
    for link in source_links:
        source_id = str(link.get("source") or "")
        target_id = str(link.get("target") or "")
        if source_id not in id_to_index or target_id not in id_to_index:
            continue
        source_index = id_to_index[source_id]
        target_index = id_to_index[target_id]
        link_type = str(link.get("link_type") or "")
        if link_type == "reactant":
            reaction_index = target_index
            metabolite_id = str(nodes[source_index].get("id") or "")
            coefficient = -1
        elif link_type == "product":
            reaction_index = source_index
            metabolite_id = str(nodes[target_index].get("id") or "")
            coefficient = 1
        else:
            reaction_index = source_index if nodes[source_index].get("group") == 1 else target_index
            metabolite_id = str(nodes[target_index if reaction_index == source_index else source_index].get("id") or "")
            coefficient = 1
        if nodes[reaction_index].get("group") == 1 and metabolite_id:
            reaction_id = str(nodes[reaction_index].get("id") or "")
            metabolites_by_reaction.setdefault(reaction_id, {})[metabolite_id] = coefficient
        links.append(
            {
                "index": len(links),
                "source": {"index": source_index},
                "target": {"index": target_index},
                "flux": None,
                "refx": 0,
                "refy": 0,
                "width": None,
                "reversed": 1,
                "omics_gem_link_type": link_type,
            }
        )

    for node in nodes:
        if node.get("group") == 1:
            node["metabolites"] = metabolites_by_reaction.get(str(node.get("id") or ""), {})

    _apply_readable_layout(nodes, links)

    session = {
        variant_id: {
            "nodes": nodes,
            "links": links,
            "suspended": [],
            "text": [],
            "shapes": [],
        },
        "selected": [],
        "count": 0,
        "currentparsed": variant_id,
        "backups": [],
        "rxncolorbreaks": _color_breaks(list(reaction_values.values())),
        "rxncolor": [[37, 99, 235], [148, 163, 184], [249, 115, 22]],
        "metcolorbreaks": [0, 1],
        "metcolor": [[100, 116, 139], [20, 184, 166]],
        "backupgraph": [],
        "backupgraphcount": -1,
        "backupparsing": False,
        "fluxobj": {},
        "concobj": {},
        "sizerxnobj": _size_object(reaction_sizes),
        "sizemetobj": {},
        "linkwidthobj": {},
        "textsts": _default_text_settings(),
        "numsts": _default_number_settings(),
        "checksts": _default_check_settings(),
    }
    return session


def write_native_export_outputs(
    output: Path,
    files: dict[str, Path],
    graph: dict[str, Any],
    session: dict[str, Any],
    render_manifest: dict[str, Any],
    *,
    status: str,
    message: str,
) -> SammiNativeExportResult:
    output.mkdir(parents=True, exist_ok=True)
    vendor = sammi_vendor_status()
    summary = graph.get("summary", {}) if isinstance(graph.get("summary"), dict) else {}
    session_key = str(session.get("currentparsed") or graph.get("variant_id") or "")
    node_count = len(session.get(session_key, {}).get("nodes", [])) if session_key in session else 0
    link_count = len(session.get(session_key, {}).get("links", [])) if session_key in session else 0
    summary_rows = [
        {
            "variant_id": graph.get("variant_id", ""),
            "status": status,
            "message": message,
            "sammi_session_key": session_key,
            "reaction_count_rendered": summary.get("reaction_count_rendered", 0),
            "metabolite_count_rendered": summary.get("metabolite_count_rendered", 0),
            "node_count": node_count,
            "link_count": link_count,
            "warning_count": summary.get("warning_count", 0),
            "overlay_count_available": summary.get("overlay_count_available", 0),
            "vendored_sammi_available": vendor.get("vendored_assets_available", False),
            "native_session_path": str(files["session"]),
            "launch_html_path": str(files["launch"]),
        }
    ]
    manifest = {
        "schema_version": "0.1.0",
        "status": status,
        "message": message,
        "variant_id": graph.get("variant_id", ""),
        "output_dir": str(output),
        "source_graph_path": str(output / "network_graph.json"),
        "source_interactive_manifest_path": str(output / "interactive_map_manifest.json"),
        "source_interactive_status": render_manifest.get("status", ""),
        "source_overlay_status": render_manifest.get("source_overlay_status", ""),
        "sammi_session_key": session_key,
        "sammi_load_guidance": "Open local SAMMI and choose Load SAMMI Model, then select sammi_native_session.json.",
        "vendored_sammi": vendor,
        "files": {key: str(path) for key, path in files.items()},
        "summary": summary_rows[0],
    }
    write_json(files["session"], session)
    check = check_sammi_native_session(files["session"], output_dir=output)
    if status == "empty_filter":
        check["message"] = message
        check["filter_guidance"] = "Use Preview / Validate Filter and choose existing reaction ids before exporting to SAMMI."
        write_json(output / "sammi_native_export_check.json", check)
        (output / "sammi_native_export_check.md").write_text(_render_check_markdown(check), encoding="utf-8")
    manifest["native_export_check"] = check
    manifest["files"]["check_json"] = str(output / "sammi_native_export_check.json")
    manifest["files"]["check_markdown"] = str(output / "sammi_native_export_check.md")
    summary_rows[0]["check_status"] = check.get("status", "")
    summary_rows[0]["check_message"] = check.get("message", "")
    write_json(files["manifest"], manifest)
    write_csv(files["summary"], summary_rows)
    files["launch"].write_text(build_native_launch_html(manifest), encoding="utf-8")
    return SammiNativeExportResult(
        status=status,
        message=message,
        output_dir=output,
        files={key: str(value) for key, value in files.items()},
        manifest=manifest,
    )


def build_native_launch_html(manifest: dict[str, Any]) -> str:
    files = manifest.get("files", {}) if isinstance(manifest.get("files"), dict) else {}
    vendor = manifest.get("vendored_sammi", {}) if isinstance(manifest.get("vendored_sammi"), dict) else {}
    check = manifest.get("native_export_check", {}) if isinstance(manifest.get("native_export_check"), dict) else {}
    index_path = str(vendor.get("vendored_index_path") or "")
    index_href = _path_href(index_path)
    session_href = _path_href(str(files.get("session", "")))
    check_href = _path_href(str(files.get("check_markdown", "")))
    rows = [
        ("SAMMI native session", files.get("session", "")),
        ("Export manifest", files.get("manifest", "")),
        ("Export summary", files.get("summary", "")),
        ("Checker report", files.get("check_markdown", "")),
        ("Source graph", manifest.get("source_graph_path", "")),
        ("Local SAMMI index", index_path),
    ]
    file_rows = "\n".join(
        f"<tr><th>{html.escape(label)}</th><td><code>{html.escape(str(path))}</code></td></tr>" for label, path in rows
    )
    open_link = (
        f'<a class="button" href="{html.escape(index_href)}" target="_blank" rel="noreferrer">Open Local SAMMI</a>'
        if index_href
        else '<span class="muted">Local SAMMI assets are not configured.</span>'
    )
    session_link = (
        f'<a class="button secondary" href="{html.escape(session_href)}" target="_blank" rel="noreferrer">Open Session JSON</a>'
        if session_href
        else ""
    )
    check_link = (
        f'<a class="button secondary" href="{html.escape(check_href)}" target="_blank" rel="noreferrer">Open Check Report</a>'
        if check_href
        else ""
    )
    check_status = str(check.get("status") or "unknown")
    check_message = str(check.get("message") or "")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>SAMMI native session export</title>
  <style>
    body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; color: #172033; background: #f8fafc; }}
    main {{ max-width: 980px; margin: 0 auto; padding: 32px; }}
    h1 {{ margin: 0 0 8px; }}
    .card {{ background: white; border: 1px solid #d9e2ec; border-radius: 8px; padding: 18px; margin: 18px 0; }}
    .button {{ display: inline-block; background: #0f766e; color: white; padding: 10px 14px; border-radius: 6px; text-decoration: none; font-weight: 700; margin-right: 8px; }}
    .button.secondary {{ background: #334155; }}
    .status {{ display: inline-block; padding: 4px 8px; border-radius: 999px; background: #e2e8f0; font-weight: 700; }}
    .status.passed {{ background: #dcfce7; color: #166534; }}
    .status.failed {{ background: #fee2e2; color: #991b1b; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; border-bottom: 1px solid #e2e8f0; padding: 8px; vertical-align: top; }}
    th {{ width: 220px; color: #475569; }}
    code {{ overflow-wrap: anywhere; }}
    .muted {{ color: #64748b; }}
  </style>
</head>
<body>
  <main>
    <h1>SAMMI native session export</h1>
    <p class="muted">{html.escape(str(manifest.get("message", "")))}</p>
    <div class="card">
      <h2>How to open</h2>
      <ol>
        <li>Open local SAMMI with the button below.</li>
        <li>In SAMMI, choose <strong>Load SAMMI Model</strong>.</li>
        <li>Select <code>sammi_native_session.json</code> from this output folder.</li>
      </ol>
      <p>{open_link}{session_link}{check_link}</p>
      <p><strong>Checker:</strong> <span class="status {html.escape(check_status)}">{html.escape(check_status)}</span> {html.escape(check_message)}</p>
    </div>
    <div class="card">
      <h2>Common failure checks</h2>
      <ul>
        <li>If the checker is <code>failed</code>, re-run Preview / Validate Filter and export a non-empty reaction list.</li>
        <li>If local SAMMI does not open, configure <code>SAMMI_STANDALONE_HOME</code> or use the lightweight viewer.</li>
        <li>If SAMMI opens but the map is empty, confirm you selected this export's <code>sammi_native_session.json</code>.</li>
      </ul>
    </div>
    <div class="card">
      <h2>Export files</h2>
      <table>{file_rows}</table>
    </div>
  </main>
</body>
</html>
"""


def native_export_file_paths(output: Path) -> dict[str, Path]:
    return {
        "session": output / "sammi_native_session.json",
        "manifest": output / "sammi_native_export_manifest.json",
        "summary": output / "sammi_native_export_summary.csv",
        "launch": output / "sammi_native_launch.html",
        "check_json": output / "sammi_native_export_check.json",
        "check_markdown": output / "sammi_native_export_check.md",
    }


def check_sammi_native_session(session_path: str | Path, *, output_dir: str | Path | None = None) -> dict[str, Any]:
    """Validate a SAMMI-native session file without opening SAMMI."""

    path = Path(session_path)
    output = Path(output_dir) if output_dir else path.parent
    check_json = output / "sammi_native_export_check.json"
    check_markdown = output / "sammi_native_export_check.md"
    vendor = sammi_vendor_status()
    failures: list[str] = []
    warnings: list[str] = []
    session: dict[str, Any] = {}
    if not path.exists():
        failures.append(f"Session file does not exist: {path}")
    else:
        try:
            session = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            failures.append(f"Session JSON is invalid: {exc}")
    current = str(session.get("currentparsed", "")) if session else ""
    graph = session.get(current, {}) if current else {}
    nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
    links = graph.get("links", []) if isinstance(graph, dict) else []
    reaction_nodes = [node for node in nodes if isinstance(node, dict) and node.get("group") == 1]
    metabolite_nodes = [node for node in nodes if isinstance(node, dict) and node.get("group") == 2]
    required_top_level = [
        "currentparsed",
        "selected",
        "count",
        "backups",
        "rxncolorbreaks",
        "rxncolor",
        "metcolorbreaks",
        "metcolor",
        "fluxobj",
        "concobj",
        "sizerxnobj",
        "sizemetobj",
        "linkwidthobj",
        "textsts",
        "numsts",
        "checksts",
    ]
    if session:
        for key in required_top_level:
            if key not in session:
                failures.append(f"Missing SAMMI session key: {key}")
        if not current:
            failures.append("Missing currentparsed.")
        elif current not in session:
            failures.append(f"currentparsed model graph not found: {current}")
        if not isinstance(nodes, list):
            failures.append("Current graph nodes must be a list.")
            nodes = []
        if not isinstance(links, list):
            failures.append("Current graph links must be a list.")
            links = []
        if not reaction_nodes:
            failures.append("No reaction nodes with group=1 were found.")
        if not metabolite_nodes:
            warnings.append("No metabolite nodes with group=2 were found.")
        if not links:
            failures.append("No links were found.")
        for index, link in enumerate(links[:50]):
            source = link.get("source") if isinstance(link, dict) else {}
            target = link.get("target") if isinstance(link, dict) else {}
            if not isinstance(source, dict) or "index" not in source or not isinstance(target, dict) or "index" not in target:
                failures.append(f"Link {index} is missing source/target index references.")
                break
    status = "passed" if not failures else "failed"
    message = (
        "SAMMI native session structure looks loadable."
        if status == "passed"
        else "SAMMI native session check found structural issues."
    )
    result = {
        "schema_version": "0.1.0",
        "status": status,
        "load_status": "manual_load_required" if status == "passed" else status,
        "message": message,
        "session_path": str(path),
        "currentparsed": current,
        "node_count": len(nodes) if isinstance(nodes, list) else 0,
        "link_count": len(links) if isinstance(links, list) else 0,
        "reaction_node_count": len(reaction_nodes),
        "metabolite_node_count": len(metabolite_nodes),
        "failures": failures,
        "warnings": warnings,
        "vendored_sammi_status": vendor.get("status", ""),
        "vendored_sammi_available": vendor.get("vendored_assets_available", False),
        "vendored_sammi_index_path": vendor.get("vendored_index_path", ""),
        "load_guidance": "Open local SAMMI, choose Load SAMMI Model, then select sammi_native_session.json.",
        "check_json_path": str(check_json),
        "check_markdown_path": str(check_markdown),
    }
    write_json(check_json, result)
    check_markdown.write_text(_render_check_markdown(result), encoding="utf-8")
    return result


def empty_sammi_session(session_key: str) -> dict[str, Any]:
    key = _safe_session_key(session_key or "omics_gem_map")
    return {
        key: {"nodes": [], "links": [], "suspended": [], "text": [], "shapes": []},
        "selected": [],
        "count": 0,
        "currentparsed": key,
        "backups": [],
        "rxncolorbreaks": [-1, 0, 1],
        "rxncolor": [[37, 99, 235], [148, 163, 184], [249, 115, 22]],
        "metcolorbreaks": [0, 1],
        "metcolor": [[100, 116, 139], [20, 184, 166]],
        "backupgraph": [],
        "backupgraphcount": -1,
        "backupparsing": False,
        "fluxobj": {},
        "concobj": {},
        "sizerxnobj": {},
        "sizemetobj": {},
        "linkwidthobj": {},
        "textsts": _default_text_settings(),
        "numsts": _default_number_settings(),
        "checksts": _default_check_settings(),
    }


def _render_check_markdown(result: dict[str, Any]) -> str:
    failures = result.get("failures") if isinstance(result.get("failures"), list) else []
    warnings = result.get("warnings") if isinstance(result.get("warnings"), list) else []
    failure_text = "\n".join(f"- {item}" for item in failures) if failures else "- none"
    warning_text = "\n".join(f"- {item}" for item in warnings) if warnings else "- none"
    return f"""# SAMMI Native Export Check

Status: `{result.get("status", "")}`

Message: {result.get("message", "")}

## Session

- Session path: `{result.get("session_path", "")}`
- Current model: `{result.get("currentparsed", "")}`
- Nodes: `{result.get("node_count", 0)}`
- Links: `{result.get("link_count", 0)}`
- Reaction nodes: `{result.get("reaction_node_count", 0)}`
- Metabolite nodes: `{result.get("metabolite_node_count", 0)}`

## Local SAMMI

- Vendored SAMMI status: `{result.get("vendored_sammi_status", "")}`
- Vendored SAMMI available: `{result.get("vendored_sammi_available", False)}`
- Vendored SAMMI index: `{result.get("vendored_sammi_index_path", "")}`

## Load Guidance

{result.get("load_guidance", "")}

## Failures

{failure_text}

## Warnings

{warning_text}
"""


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _first_csv_row(path: Path) -> dict[str, str]:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    rows = read_csv_records(path)
    return rows[0] if rows else {}


def _latest_mtime(paths: list[Path]) -> float:
    existing = [path.stat().st_mtime for path in paths if path.exists()]
    return max(existing) if existing else 0.0


def _iso_time(timestamp: float) -> str:
    if not timestamp:
        return ""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _safe_int(value: object) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _safe_session_key(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return cleaned or "omics_gem_map"


def _to_float(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _scaled_size(value: float | None, is_reaction: bool) -> float | None:
    if value is None or math.isnan(value):
        return None
    base = 6.0 if is_reaction else 4.0
    return max(1.0, min(24.0, base + abs(value)))


def _layout_x(index: int) -> float:
    return float((index % 32) * 34 - 520)


def _layout_y(index: int) -> float:
    return float((index // 32) * 34 - 320)


def _label_parts(label: str) -> list[str]:
    parts = [part for part in re.split(r"[_\s-]+", label) if part]
    return parts[:5] if parts else [label]


def _apply_readable_layout(nodes: list[dict[str, Any]], links: list[dict[str, Any]]) -> None:
    """Apply a fixed, readable initial layout for SAMMI pathway sessions.

    SAMMI's own arranging tools are useful for hand-polishing selected nodes,
    but a dense imported graph needs reasonable coordinates first.  The layout
    below keeps reactions on a spacious serpentine grid and places metabolites
    around their connected reactions, so labels are not all initialized at the
    same crowded strip.
    """

    reaction_indices = [index for index, node in enumerate(nodes) if node.get("group") == 1]
    metabolite_indices = [index for index, node in enumerate(nodes) if node.get("group") == 2]
    if not reaction_indices:
        return

    reaction_count = len(reaction_indices)
    columns = max(1, min(12, math.ceil(math.sqrt(reaction_count * 1.45))))
    rows = max(1, math.ceil(reaction_count / columns))
    x_spacing = 260.0
    y_spacing = 190.0
    start_x = -((columns - 1) * x_spacing) / 2.0
    start_y = -((rows - 1) * y_spacing) / 2.0

    for order, node_index in enumerate(reaction_indices):
        row = order // columns
        column = order % columns
        if row % 2 == 1:
            column = columns - 1 - column
        x = start_x + column * x_spacing
        y = start_y + row * y_spacing
        _fix_node_position(nodes[node_index], x, y)

    reaction_neighbor_offsets: dict[tuple[int, str], int] = {}
    metabolite_neighbors: dict[int, list[tuple[int, str]]] = {index: [] for index in metabolite_indices}
    for link in links:
        source = link.get("source") if isinstance(link, dict) else {}
        target = link.get("target") if isinstance(link, dict) else {}
        source_index = source.get("index") if isinstance(source, dict) else None
        target_index = target.get("index") if isinstance(target, dict) else None
        if not isinstance(source_index, int) or not isinstance(target_index, int):
            continue
        if source_index >= len(nodes) or target_index >= len(nodes):
            continue
        source_group = nodes[source_index].get("group")
        target_group = nodes[target_index].get("group")
        link_type = str(link.get("omics_gem_link_type") or "")
        if source_group == 2 and target_group == 1:
            metabolite_neighbors.setdefault(source_index, []).append((target_index, link_type or "reactant"))
        elif source_group == 1 and target_group == 2:
            metabolite_neighbors.setdefault(target_index, []).append((source_index, link_type or "product"))

    floating_metabolites = 0
    for node_index in metabolite_indices:
        neighbors = metabolite_neighbors.get(node_index, [])
        node = nodes[node_index]
        if not neighbors:
            floating_metabolites += 1
            _fix_node_position(node, -520.0 + (floating_metabolites % 8) * 130.0, start_y + rows * y_spacing + 120.0)
            continue
        if len(neighbors) == 1:
            reaction_index, link_type = neighbors[0]
            reaction = nodes[reaction_index]
            side = "left" if link_type == "reactant" else "right"
            offset_key = (reaction_index, side)
            offset_number = reaction_neighbor_offsets.get(offset_key, 0)
            reaction_neighbor_offsets[offset_key] = offset_number + 1
            side_sign = -1.0 if side == "left" else 1.0
            offset_y = ((offset_number % 5) - 2) * 32.0
            offset_x = side_sign * (96.0 + (offset_number // 5) * 42.0)
            _fix_node_position(node, float(reaction.get("x", 0.0)) + offset_x, float(reaction.get("y", 0.0)) + offset_y)
            continue
        xs = [float(nodes[reaction_index].get("x", 0.0)) for reaction_index, _ in neighbors]
        ys = [float(nodes[reaction_index].get("y", 0.0)) for reaction_index, _ in neighbors]
        avg_x = sum(xs) / len(xs)
        avg_y = sum(ys) / len(ys)
        spread = max(xs) - min(xs)
        if spread < 20:
            avg_y += 72.0
        _fix_node_position(node, avg_x, avg_y + 42.0)


def _fix_node_position(node: dict[str, Any], x: float, y: float) -> None:
    node["x"] = float(round(x, 3))
    node["y"] = float(round(y, 3))
    node["fx"] = node["x"]
    node["fy"] = node["y"]
    node["isfixed"] = True
    node["vx"] = 0
    node["vy"] = 0


def _color_breaks(values: list[float]) -> list[float]:
    finite = [value for value in values if value is not None and not math.isnan(value)]
    if not finite:
        return [-1, 0, 1]
    lo = min(finite)
    hi = max(finite)
    if lo == hi:
        lo -= 1
        hi += 1
    return [lo, 0 if lo < 0 < hi else (lo + hi) / 2, hi]


def _size_object(reaction_sizes: dict[str, float]) -> dict[str, Any]:
    if not reaction_sizes:
        return {}
    data: dict[str, Any] = {"ttls": ["Omics-GEM overlay size"]}
    for reaction_id, size in reaction_sizes.items():
        data[reaction_id] = [size]
    return data


def _default_text_settings() -> list[str]:
    return [
        "class",
        "name",
        "subsystem",
        "compartment",
        "#64748b",
        "#2563eb",
        "#94a3b8",
        "#f97316",
        "#94a3b8",
        "#0f766e",
        "#cbd5e1",
        "name",
        "class",
        "class",
        "#2563eb",
        "#64748b",
        "#64748b",
    ]


def _default_number_settings() -> list[float]:
    return [
        5,
        14,
        1,
        1,
        30,
        0,
        30,
        0.4,
        0.02,
        0.1,
        3,
        0,
        40,
        4,
        1,
        2,
        1,
        5,
        2,
        1,
        5,
        1,
        0,
        5,
    ]


def _default_check_settings() -> list[bool]:
    return [True, True, False, True, False, False]


def _path_href(path: str) -> str:
    if not path:
        return ""
    try:
        return Path(path).resolve().as_uri()
    except ValueError:
        return ""
