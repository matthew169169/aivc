"""Interactive reaction-network renderer for SAMMI-compatible packages."""

from __future__ import annotations

import html
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constraints import write_csv, write_json
from .model_generation import safe_variant_dir_name
from .sammi_visualization import build_sammi_visualization_package


DEFAULT_TOP_N = 120
DEFAULT_MAX_NODES = 900
DEFAULT_MAX_LINKS = 1800
CURRENCY_METABOLITES = {
    "h",
    "h2o",
    "atp",
    "adp",
    "amp",
    "pi",
    "ppi",
    "nad",
    "nadh",
    "nadp",
    "nadph",
    "coa",
    "co2",
    "o2",
    "nh4",
    "hco3",
    "q8",
    "q8h2",
}


@dataclass(slots=True)
class SammiInteractiveRenderResult:
    """Result returned after an interactive map render package is written."""

    status: str
    message: str
    output_dir: Path
    files: dict[str, str]
    manifest: dict[str, Any]


def build_sammi_interactive_render(
    package_dir: str | Path,
    *,
    variant_id: str = "",
    grouping_mode: str = "subsystem",
    overlay_source: str = "none",
    reaction_filter: list[str] | str | None = None,
    subsystem_filter: list[str] | str | None = None,
    ml_profile_id: str = "",
    output_dir: str | Path | None = None,
    top_n: int = DEFAULT_TOP_N,
    include_currency_metabolites: bool = False,
    max_nodes: int = DEFAULT_MAX_NODES,
    max_links: int = DEFAULT_MAX_LINKS,
) -> SammiInteractiveRenderResult:
    """Build graph JSON and a standalone interactive HTML map.

    The renderer is intentionally lightweight and local. It reuses the
    existing SAMMI-compatible package builder, then converts reaction rows and
    overlay rows into a reaction-metabolite bipartite graph.
    """

    package = Path(package_dir)
    package_result = build_sammi_visualization_package(
        package,
        variant_id=variant_id,
        grouping_mode=grouping_mode,
        overlay_source=overlay_source,
        reaction_filter=reaction_filter,
        ml_profile_id=ml_profile_id,
        output_dir=output_dir,
    )
    output = package_result.output_dir
    files = interactive_file_paths(output)
    package_json_path = output / "sammi_map_package.json"
    package_json = _read_json(package_json_path)
    selected_variant_id = str(package_result.manifest.get("variant_id") or variant_id or "baseline_gem__all")

    if package_result.status != "completed":
        graph = empty_graph(
            status=package_result.status,
            message=package_result.message,
            package_json=package_json,
            variant_id=selected_variant_id,
        )
        return write_interactive_outputs(output, files, graph, package_result.manifest)

    graph = build_network_graph(
        package_json=package_json,
        reaction_filter=reaction_filter,
        subsystem_filter=subsystem_filter,
        top_n=top_n,
        include_currency_metabolites=include_currency_metabolites,
        max_nodes=max_nodes,
        max_links=max_links,
    )
    return write_interactive_outputs(output, files, graph, package_result.manifest)


def build_network_graph(
    *,
    package_json: dict[str, Any],
    reaction_filter: list[str] | str | None = None,
    subsystem_filter: list[str] | str | None = None,
    top_n: int = DEFAULT_TOP_N,
    include_currency_metabolites: bool = False,
    max_nodes: int = DEFAULT_MAX_NODES,
    max_links: int = DEFAULT_MAX_LINKS,
) -> dict[str, Any]:
    reactions = [dict(row) for row in package_json.get("reactions", []) if isinstance(row, dict)]
    overlays = [dict(row) for row in package_json.get("overlays", []) if isinstance(row, dict)]
    overlay_by_reaction = best_overlay_by_reaction(overlays)
    reaction_ids = normalize_filter(reaction_filter)
    subsystem_terms = {term.lower() for term in normalize_filter(subsystem_filter)}

    filtered = filter_reactions(reactions, overlay_by_reaction, reaction_ids, subsystem_terms, top_n)
    graph_status = "completed"
    message = "Interactive reaction network graph generated."

    nodes, links = reaction_metabolite_graph(
        filtered,
        overlay_by_reaction,
        include_currency_metabolites=include_currency_metabolites,
    )
    if (len(nodes) > max_nodes or len(links) > max_links) and not (reaction_ids or subsystem_terms):
        graph_status = "needs_filtering"
        message = (
            "The requested graph is too large for the default interactive viewer. "
            "Choose a subsystem, reaction list, or lower top_n."
        )
        nodes = []
        links = []

    warning_count = sum(1 for node in nodes if node.get("node_type") == "reaction" and _as_bool(node.get("warning_flag")))
    reaction_node_count = sum(1 for node in nodes if node.get("node_type") == "reaction")
    metabolite_node_count = sum(1 for node in nodes if node.get("node_type") == "metabolite")
    production_nodes = [node for node in nodes if node.get("node_type") == "reaction" and node.get("semantic_type") == "production"]
    top_production_nodes = sorted(production_nodes, key=lambda node: overlay_rank(node), reverse=True)[:10]
    warning_nodes = [node for node in production_nodes if _as_bool(node.get("warning_flag"))]
    return {
        "schema_version": "0.1.0",
        "format": "omics_gem_interactive_network_graph",
        "status": graph_status,
        "message": message,
        "variant_id": package_json.get("variant_id", ""),
        "generation_method": package_json.get("generation_method", ""),
        "grouping_mode": package_json.get("grouping_mode", ""),
        "overlay_semantic_types": package_json.get("overlay_semantic_types", []),
        "filters": {
            "reaction_filter": sorted(reaction_ids),
            "subsystem_filter": sorted(subsystem_terms),
            "top_n": top_n,
            "include_currency_metabolites": include_currency_metabolites,
            "max_nodes": max_nodes,
            "max_links": max_links,
        },
        "legend": build_legend(nodes),
        "nodes": nodes,
        "links": links,
        "summary": {
            "status": graph_status,
            "message": message,
            "reaction_count_available": len(reactions),
            "reaction_count_rendered": reaction_node_count,
            "metabolite_count_rendered": metabolite_node_count,
            "node_count": len(nodes),
            "link_count": len(links),
            "overlay_count_available": len(overlays),
            "warning_count": warning_count,
            "production_candidate_count": len(production_nodes),
            "ko_candidate_count": sum(1 for node in production_nodes if str(node.get("candidate_action", "")).upper() == "KO"),
            "kd_candidate_count": sum(1 for node in production_nodes if str(node.get("candidate_action", "")).upper() == "KD"),
            "oe_candidate_count": sum(1 for node in production_nodes if str(node.get("candidate_action", "")).upper() == "OE"),
            "top_production_reactions": ";".join(str(node.get("id", "")) for node in top_production_nodes if node.get("id")),
            "production_warning_reactions": ";".join(str(node.get("id", "")) for node in warning_nodes if node.get("id")),
            "needs_filtering": graph_status == "needs_filtering",
        },
        "notes": [
            "This graph is generated by the Omics-GEM lightweight interactive viewer.",
            "SAMMI standalone assets are not vendored by this renderer.",
        ],
    }


def filter_reactions(
    reactions: list[dict[str, Any]],
    overlay_by_reaction: dict[str, dict[str, Any]],
    reaction_ids: set[str],
    subsystem_terms: set[str],
    top_n: int,
) -> list[dict[str, Any]]:
    rows = reactions
    if reaction_ids:
        rows = [
            row
            for row in rows
            if str(row.get("reaction_id", "")) in reaction_ids or str(row.get("cobra_reaction_id", "")) in reaction_ids
        ]
    if subsystem_terms:
        rows = [
            row
            for row in rows
            if any(
                term in " ".join(
                    [
                        str(row.get("group_id", "")),
                        str(row.get("group_label", "")),
                        str(row.get("subsystem", "")),
                    ]
                ).lower()
                for term in subsystem_terms
            )
        ]
    if not reaction_ids and not subsystem_terms and top_n > 0 and overlay_by_reaction:
        ranked = sorted(
            rows,
            key=lambda row: overlay_rank(overlay_by_reaction.get(str(row.get("reaction_id", ""))) or overlay_by_reaction.get(str(row.get("cobra_reaction_id", "")))),
            reverse=True,
        )
        rows = ranked[:top_n]
    return rows


def reaction_metabolite_graph(
    reactions: list[dict[str, Any]],
    overlay_by_reaction: dict[str, dict[str, Any]],
    *,
    include_currency_metabolites: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes_by_id: dict[str, dict[str, Any]] = {}
    links: list[dict[str, Any]] = []
    for reaction in reactions:
        reaction_id = str(reaction.get("reaction_id", ""))
        if not reaction_id:
            continue
        overlay = overlay_by_reaction.get(reaction_id) or overlay_by_reaction.get(str(reaction.get("cobra_reaction_id", ""))) or {}
        reaction_node = {
            "id": reaction_id,
            "label": reaction.get("cobra_reaction_id") or reaction_id,
            "name": reaction.get("reaction_name", ""),
            "node_type": "reaction",
            "group_id": reaction.get("group_id", ""),
            "group_label": reaction.get("group_label", ""),
            "subsystem": reaction.get("subsystem", ""),
            "compartment": reaction.get("compartment", ""),
            "selected_reaction": reaction.get("selected_reaction", False),
            "reactants": reaction.get("reactants", ""),
            "products": reaction.get("products", ""),
            "overlay_source": overlay.get("overlay_source", ""),
            "semantic_type": overlay.get("semantic_type", ""),
            "overlay_value": overlay.get("overlay_value", ""),
            "overlay_color": overlay.get("overlay_color") or "#2563eb",
            "overlay_size": _to_float(overlay.get("overlay_size")) or 1.0,
            "warning_flag": _as_bool(overlay.get("warning_flag")),
            "readiness_label": overlay.get("readiness_label", ""),
            "candidate_type": overlay.get("candidate_type", ""),
            "candidate_action": overlay.get("candidate_action", ""),
            "production_score": overlay.get("production_score", overlay.get("overlay_value", "")),
            "product_reaction_id": overlay.get("product_reaction_id", ""),
            "product_name": overlay.get("product_name", ""),
            "warning_reasons": overlay.get("warning_reasons", ""),
            "source_status": overlay.get("source_status", ""),
        }
        nodes_by_id[reaction_id] = reaction_node
        for metabolite in split_species(str(reaction.get("reactants", ""))):
            add_metabolite_link(nodes_by_id, links, metabolite, reaction_id, "reactant", include_currency_metabolites)
        for metabolite in split_species(str(reaction.get("products", ""))):
            add_metabolite_link(nodes_by_id, links, reaction_id, metabolite, "product", include_currency_metabolites)
    return list(nodes_by_id.values()), links


def add_metabolite_link(
    nodes_by_id: dict[str, dict[str, Any]],
    links: list[dict[str, Any]],
    source: str,
    target: str,
    link_type: str,
    include_currency_metabolites: bool,
) -> None:
    metabolite = source if link_type == "reactant" else target
    if not metabolite:
        return
    if not include_currency_metabolites and is_currency_metabolite(metabolite):
        return
    nodes_by_id.setdefault(
        metabolite,
        {
            "id": metabolite,
            "label": clean_metabolite_label(metabolite),
            "name": metabolite,
            "node_type": "metabolite",
            "group_id": "metabolite",
            "group_label": "Metabolites",
            "overlay_color": "#64748b",
            "overlay_size": 0.8,
            "warning_flag": False,
        },
    )
    if source in nodes_by_id and target in nodes_by_id:
        links.append(
            {
                "id": f"{source}->{target}:{link_type}:{len(links)}",
                "source": source,
                "target": target,
                "link_type": link_type,
            }
        )


def best_overlay_by_reaction(overlays: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for row in overlays:
        for key in (str(row.get("reaction_id", "")), str(row.get("cobra_reaction_id", ""))):
            if not key:
                continue
            current = best.get(key)
            if current is None or overlay_rank(row) > overlay_rank(current):
                best[key] = row
    return best


def overlay_rank(row: dict[str, Any] | None) -> float:
    if not row:
        return -1.0
    value = _to_float(row.get("overlay_value"))
    size = _to_float(row.get("overlay_size"))
    if value is not None and not math.isnan(value):
        return abs(value)
    if size is not None and not math.isnan(size):
        return abs(size)
    if _as_bool(row.get("warning_flag")):
        return 10.0
    return 0.0


def write_interactive_outputs(
    output: Path,
    files: dict[str, Path],
    graph: dict[str, Any],
    source_manifest: dict[str, Any],
) -> SammiInteractiveRenderResult:
    output.mkdir(parents=True, exist_ok=True)
    summary = graph.get("summary", {})
    manifest = {
        "schema_version": "0.1.0",
        "status": graph.get("status", "completed"),
        "message": graph.get("message", ""),
        "variant_id": graph.get("variant_id", ""),
        "grouping_mode": source_manifest.get("grouping_mode", graph.get("grouping_mode", "")),
        "overlay_source": source_manifest.get("overlay_source", ""),
        "output_dir": str(output),
        "source_sammi_manifest_path": str(output / "sammi_package_manifest.json"),
        "source_overlay_status": source_manifest.get("overlay_status", ""),
        "files": {key: str(path) for key, path in files.items()},
        "summary": summary,
    }
    summary_rows = [
        {
            "variant_id": graph.get("variant_id", ""),
            "status": graph.get("status", ""),
            "message": graph.get("message", ""),
            "reaction_count_rendered": summary.get("reaction_count_rendered", 0),
            "metabolite_count_rendered": summary.get("metabolite_count_rendered", 0),
            "node_count": summary.get("node_count", 0),
            "link_count": summary.get("link_count", 0),
            "overlay_count_available": summary.get("overlay_count_available", 0),
            "warning_count": summary.get("warning_count", 0),
            "production_candidate_count": summary.get("production_candidate_count", 0),
            "ko_candidate_count": summary.get("ko_candidate_count", 0),
            "kd_candidate_count": summary.get("kd_candidate_count", 0),
            "oe_candidate_count": summary.get("oe_candidate_count", 0),
            "top_production_reactions": summary.get("top_production_reactions", ""),
            "production_warning_reactions": summary.get("production_warning_reactions", ""),
            "needs_filtering": summary.get("needs_filtering", False),
        }
    ]
    write_json(files["graph"], graph)
    write_json(files["manifest"], manifest)
    write_csv(files["summary"], summary_rows)
    files["html"].write_text(build_interactive_html(graph, manifest), encoding="utf-8")
    return SammiInteractiveRenderResult(
        status=str(manifest["status"]),
        message=str(manifest["message"]),
        output_dir=output,
        files={key: str(value) for key, value in files.items()},
        manifest=manifest,
    )


def empty_graph(*, status: str, message: str, package_json: dict[str, Any], variant_id: str) -> dict[str, Any]:
    return {
        "schema_version": "0.1.0",
        "format": "omics_gem_interactive_network_graph",
        "status": status,
        "message": message,
        "variant_id": variant_id,
        "generation_method": package_json.get("generation_method", ""),
        "grouping_mode": package_json.get("grouping_mode", ""),
        "overlay_semantic_types": [],
        "filters": {},
        "legend": [],
        "nodes": [],
        "links": [],
        "summary": {
            "status": status,
            "message": message,
            "reaction_count_available": 0,
            "reaction_count_rendered": 0,
            "metabolite_count_rendered": 0,
            "node_count": 0,
            "link_count": 0,
            "overlay_count_available": 0,
            "warning_count": 0,
            "needs_filtering": status == "needs_filtering",
        },
        "notes": [],
    }


def interactive_file_paths(output: Path) -> dict[str, Path]:
    return {
        "graph": output / "network_graph.json",
        "html": output / "interactive_map.html",
        "manifest": output / "interactive_map_manifest.json",
        "summary": output / "interactive_map_summary.csv",
    }


def build_legend(nodes: list[dict[str, Any]]) -> list[dict[str, str]]:
    seen: dict[str, str] = {}
    for node in nodes:
        if node.get("node_type") != "reaction":
            continue
        semantic = str(node.get("semantic_type") or "reaction")
        if semantic == "production":
            action = str(node.get("candidate_action") or "").upper()
            semantic = f"production_{action.lower()}" if action in {"KO", "KD", "OE"} else "production_candidate"
        if _as_bool(node.get("warning_flag")):
            semantic = "warning"
        seen.setdefault(semantic, str(node.get("overlay_color") or "#2563eb"))
    if "metabolite" not in seen:
        seen["metabolite"] = "#64748b"
    return [{"semantic_type": key, "label": key.replace("_", " "), "color": value} for key, value in sorted(seen.items())]


def build_interactive_html(graph: dict[str, Any], manifest: dict[str, Any]) -> str:
    graph_json = json.dumps(graph, ensure_ascii=False).replace("</", "<\\/")
    title = f"Interactive map - {graph.get('variant_id', '')}"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
    body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; color: #172033; background: #f8fafc; }}
    header {{ padding: 16px 20px; background: white; border-bottom: 1px solid #d9e2ec; }}
    main {{ display: grid; grid-template-columns: 1fr 320px; min-height: calc(100vh - 74px); }}
    svg {{ width: 100%; height: calc(100vh - 74px); background: white; }}
    aside {{ border-left: 1px solid #d9e2ec; padding: 16px; background: #f8fafc; overflow: auto; }}
    .node text {{ font-size: 10px; pointer-events: none; fill: #334155; }}
    .link {{ stroke: #94a3b8; stroke-opacity: .55; }}
    .reaction {{ stroke: #0f172a; stroke-width: 1.2; }}
    .metabolite {{ stroke: #475569; stroke-width: .8; }}
    code {{ background: #e2e8f0; padding: 1px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
  <header>
    <strong>{html.escape(title)}</strong>
    <span id="summary"></span>
  </header>
  <main>
    <svg id="map" viewBox="-500 -360 1000 720" role="img" aria-label="Interactive metabolic reaction map"></svg>
    <aside>
      <h3>Map details</h3>
      <div id="details">Click a node to inspect it.</div>
      <h3>Legend</h3>
      <div id="legend"></div>
      <h3>Files</h3>
      <p><code>network_graph.json</code><br><code>interactive_map_manifest.json</code></p>
    </aside>
  </main>
  <script>
    const graph = {graph_json};
    const svg = document.getElementById("map");
    const details = document.getElementById("details");
    const summary = graph.summary || {{}};
    document.getElementById("summary").textContent = ` | ${{summary.node_count || 0}} nodes, ${{summary.link_count || 0}} links`;
    const legend = document.getElementById("legend");
    (graph.legend || []).forEach(item => {{
      const row = document.createElement("div");
      row.innerHTML = `<span style="display:inline-block;width:12px;height:12px;background:${{item.color}};border-radius:50%;margin-right:6px"></span>${{item.semantic_type}}`;
      legend.appendChild(row);
    }});
    const width = 1000, height = 720;
    const nodes = (graph.nodes || []).map((node, index) => ({{
      ...node,
      x: (index % 30) * 28 - 420,
      y: Math.floor(index / 30) * 28 - 300
    }}));
    const byId = new Map(nodes.map(node => [node.id, node]));
    const links = (graph.links || []).filter(link => byId.has(link.source) && byId.has(link.target));
    const ns = "http://www.w3.org/2000/svg";
    const root = document.createElementNS(ns, "g");
    svg.appendChild(root);
    links.forEach(link => {{
      const source = byId.get(link.source), target = byId.get(link.target);
      const line = document.createElementNS(ns, "line");
      line.setAttribute("class", "link");
      line.setAttribute("x1", source.x); line.setAttribute("y1", source.y);
      line.setAttribute("x2", target.x); line.setAttribute("y2", target.y);
      root.appendChild(line);
    }});
    nodes.forEach(node => {{
      const group = document.createElementNS(ns, "g");
      group.setAttribute("class", `node ${{node.node_type}}`);
      group.setAttribute("transform", `translate(${{node.x}},${{node.y}})`);
      const circle = document.createElementNS(ns, "circle");
      circle.setAttribute("r", node.node_type === "reaction" ? 7 + Math.min(8, Number(node.overlay_size || 1) * 1.2) : 4);
      circle.setAttribute("fill", node.overlay_color || (node.node_type === "reaction" ? "#2563eb" : "#64748b"));
      circle.setAttribute("class", node.node_type || "node");
      const label = document.createElementNS(ns, "text");
      label.setAttribute("x", 9); label.setAttribute("y", 3);
      label.textContent = node.label || node.id;
      const title = document.createElementNS(ns, "title");
      title.textContent = `${{node.id}}\\n${{node.name || ""}}\\n${{node.subsystem || ""}}`;
      group.appendChild(title); group.appendChild(circle); group.appendChild(label);
      group.addEventListener("click", () => {{
        details.innerHTML = `<p><strong>${{node.id}}</strong></p><p>${{node.name || ""}}</p><p>type: ${{node.node_type}}</p><p>subsystem: ${{node.subsystem || ""}}</p><p>overlay: ${{node.overlay_value || ""}}</p><p>readiness: ${{node.readiness_label || ""}}</p>`;
      }});
      root.appendChild(group);
    }});
  </script>
</body>
</html>
"""


def normalize_filter(value: list[str] | str | None) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, list):
        tokens = value
    else:
        tokens = re.split(r"[;,\s]+", str(value))
    cleaned = {token.strip() for token in tokens if token and token.strip()}
    expanded: set[str] = set()
    for token in cleaned:
        expanded.add(token)
        expanded.add(token[2:] if token.startswith("R_") else f"R_{token}")
    return expanded


def split_species(value: str) -> list[str]:
    return [item.strip() for item in value.split(";") if item.strip()]


def clean_metabolite_label(species_id: str) -> str:
    label = species_id[2:] if species_id.startswith("M_") else species_id
    return label


def is_currency_metabolite(species_id: str) -> bool:
    label = clean_metabolite_label(species_id)
    base = label.rsplit("_", 1)[0] if "_" in label else label
    return base.lower() in CURRENCY_METABOLITES


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _to_float(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}
