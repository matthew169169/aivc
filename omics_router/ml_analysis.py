"""Lightweight ML analysis and ML-prior bridge for GEM workflows."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from .constraints import read_csv_records, write_csv, write_json


@dataclass(slots=True)
class MlAnalysisResult:
    """Summary returned after running lightweight ML analysis."""

    status: str
    output_dir: str
    message: str
    files: dict[str, str]
    summary_rows: list[dict[str, object]]
    correlation_rows: list[dict[str, object]]
    prior_rows: list[dict[str, object]]


@dataclass(slots=True)
class MlDiagnosticsTables:
    """Exploratory diagnostics derived from the ML feature matrix."""

    summary_rows: list[dict[str, object]]
    pca_rows: list[dict[str, object]]
    loading_rows: list[dict[str, object]]
    cluster_rows: list[dict[str, object]]
    lasso_lite_rows: list[dict[str, object]]


def run_ml_analysis(
    package_dir: str | Path,
    output_dir: str | Path | None = None,
    min_overlap: int = 2,
    prior_threshold: float = 0.5,
    max_clusters: int = 2,
    max_lasso_features: int = 5,
) -> MlAnalysisResult:
    """Run correlation ranking and build soft ML priors from the feature matrix."""

    package = Path(package_dir)
    output = Path(output_dir) if output_dir else package / "ml_results"
    output.mkdir(parents=True, exist_ok=True)
    matrix_path = output / "ml_feature_matrix.csv"
    files = {
        "correlations": str(output / "feature_phenotype_correlations.csv"),
        "prior_scores": str(output / "ml_prior_scores.csv"),
        "context_policy": str(output / "ml_context_policy.csv"),
        "summary": str(output / "ml_analysis_summary.csv"),
        "diagnostic_summary": str(output / "ml_diagnostic_summary.csv"),
        "pca_scores": str(output / "ml_pca_scores.csv"),
        "feature_loadings": str(output / "ml_feature_loadings.csv"),
        "condition_clusters": str(output / "ml_condition_clusters.csv"),
        "lasso_lite_coefficients": str(output / "ml_lasso_lite_coefficients.csv"),
        "manifest": str(output / "ml_analysis_manifest.json"),
    }

    if not matrix_path.exists() or matrix_path.stat().st_size == 0:
        summary_rows = [_summary_row("missing_matrix", 0, 0, 0, 0, "No ml_feature_matrix.csv was found.")]
        diagnostics = _empty_diagnostics("missing_matrix", "No ml_feature_matrix.csv was found.")
        _write_outputs(
            files,
            [],
            [],
            [],
            summary_rows,
            diagnostics,
            parameters={
                "min_overlap": min_overlap,
                "prior_threshold": prior_threshold,
                "max_clusters": max_clusters,
                "max_lasso_features": max_lasso_features,
            },
        )
        return _result(output, files, "completed_no_matrix", "No ML feature matrix was available.", summary_rows, [], [])

    matrix_rows = read_csv_records(matrix_path)
    target_features = [column for column in _feature_columns(matrix_rows) if column.startswith("phenotype_")]
    candidate_features = [
        column
        for column in _feature_columns(matrix_rows)
        if column not in target_features and _feature_entity_type(column) in {"gene", "reaction"}
    ]
    correlation_rows = build_feature_correlations(matrix_rows, target_features, candidate_features, min_overlap=min_overlap)
    prior_rows = build_ml_prior_scores(correlation_rows, threshold=prior_threshold)
    context_rows = build_ml_context_policy(prior_rows)
    diagnostics = build_ml_diagnostics(
        matrix_rows,
        target_features,
        candidate_features,
        correlation_rows,
        max_clusters=max_clusters,
        max_lasso_features=max_lasso_features,
    )
    summary_rows = [
        _summary_row(
            "correlation_ranking",
            len(target_features),
            len(candidate_features),
            len(correlation_rows),
            len(prior_rows),
            _analysis_guidance(matrix_rows, target_features, correlation_rows),
        )
    ]
    _write_outputs(
        files,
        correlation_rows,
        prior_rows,
        context_rows,
        summary_rows,
        diagnostics,
        parameters={
            "min_overlap": min_overlap,
            "prior_threshold": prior_threshold,
            "max_clusters": max_clusters,
            "max_lasso_features": max_lasso_features,
        },
    )
    status = "completed" if correlation_rows else "completed_no_correlations"
    message = (
        f"ML analysis built {len(correlation_rows)} feature-target correlations and "
        f"{len(prior_rows)} soft ML prior rows."
    )
    if not correlation_rows:
        message = "ML analysis found no target/candidate feature pairs with enough overlapping numeric values."
    return _result(output, files, status, message, summary_rows, correlation_rows, prior_rows)


def build_feature_correlations(
    matrix_rows: list[dict[str, str]],
    target_features: list[str],
    candidate_features: list[str],
    min_overlap: int = 2,
) -> list[dict[str, object]]:
    """Compute Pearson correlations between candidate features and phenotype targets."""

    rows: list[dict[str, object]] = []
    for target in target_features:
        for feature in candidate_features:
            pairs = _paired_numeric_values(matrix_rows, feature, target)
            if len(pairs) < min_overlap:
                continue
            xs = [pair[0] for pair in pairs]
            ys = [pair[1] for pair in pairs]
            corr = pearson_correlation(xs, ys)
            if corr is None:
                continue
            feature_type, entity_id = _split_feature_id(feature)
            target_type, target_entity_id = _split_feature_id(target)
            rows.append(
                {
                    "target_feature_id": target,
                    "target_feature_type": target_type,
                    "target_entity_id": target_entity_id,
                    "feature_id": feature,
                    "feature_type": feature_type,
                    "entity_type": _feature_entity_type(feature),
                    "entity_id": entity_id,
                    "overlap_count": len(pairs),
                    "pearson_r": round(corr, 6),
                    "abs_pearson_r": round(abs(corr), 6),
                    "direction": "positive" if corr > 0 else "negative" if corr < 0 else "zero",
                    "association_strength": _association_strength(abs(corr)),
                    "sample_status": "low_n_exploratory" if len(pairs) < 4 else "usable",
                    "status": "completed",
                }
            )
    rows.sort(key=lambda row: (-float(row["abs_pearson_r"]), row["target_feature_id"], row["feature_id"]))
    return rows


def build_ml_prior_scores(
    correlation_rows: list[dict[str, object]],
    threshold: float = 0.5,
) -> list[dict[str, object]]:
    """Convert correlations into soft gene/reaction ML prior scores."""

    rows: list[dict[str, object]] = []
    for row in correlation_rows:
        score = _to_float(row.get("pearson_r"))
        abs_score = _to_float(row.get("abs_pearson_r"))
        if score is None or abs_score is None or abs_score < threshold:
            continue
        entity_type = str(row.get("entity_type", ""))
        if entity_type not in {"gene", "reaction"}:
            continue
        entity_id = str(row.get("entity_id", ""))
        model_target_id = _model_target_id(entity_type, entity_id)
        rows.append(
            {
                "target_feature_id": row.get("target_feature_id", ""),
                "source_feature_id": row.get("feature_id", ""),
                "target_type": entity_type,
                "target_id": entity_id,
                "model_target_id": model_target_id,
                "score": round(score, 6),
                "abs_score": round(abs_score, 6),
                "direction": row.get("direction", ""),
                "ml_evidence": _ml_evidence(score, abs_score),
                "context_action": _context_action(score, abs_score),
                "reaction_penalty": _reaction_penalty(score, abs_score) if entity_type == "reaction" else "",
                "confidence": row.get("association_strength", ""),
                "sample_status": row.get("sample_status", ""),
                "status": "soft_prior",
                "note": "Correlation-derived ML prior; use as soft evidence, not as a hard knockout.",
            }
        )
    return rows


def build_ml_context_policy(prior_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Create a reaction-level soft policy table from ML priors."""

    rows = []
    for row in prior_rows:
        if row.get("target_type") != "reaction":
            continue
        reaction_id = str(row.get("model_target_id") or row.get("target_id") or "")
        rows.append(
            {
                "condition": "ALL",
                "reaction_id": reaction_id,
                "cobra_reaction_id": reaction_id[2:] if reaction_id.startswith("R_") else reaction_id,
                "decision": row.get("context_action", ""),
                "penalty": row.get("reaction_penalty", ""),
                "ml_score": row.get("score", ""),
                "source_feature_id": row.get("source_feature_id", ""),
                "target_feature_id": row.get("target_feature_id", ""),
                "status": "soft_ml_policy",
                "note": row.get("note", ""),
            }
        )
    return rows


def build_ml_diagnostics(
    matrix_rows: list[dict[str, str]],
    target_features: list[str],
    candidate_features: list[str],
    correlation_rows: list[dict[str, object]],
    max_clusters: int = 2,
    max_lasso_features: int = 5,
) -> MlDiagnosticsTables:
    """Build PCA, k-means, and LASSO-lite exploratory diagnostics.

    The LASSO-lite table is a sparse correlation screen, not a full penalized
    regression fit. It gives users an interpretable first-pass feature shortlist
    without adding a scikit-learn dependency.
    """

    conditions, feature_ids, standardized = _standardized_feature_matrix(matrix_rows, candidate_features)
    pca_rows, loading_rows = _build_pca_tables(conditions, feature_ids, standardized)
    cluster_rows = _build_cluster_rows(pca_rows, max_clusters=max_clusters)
    lasso_lite_rows = _build_lasso_lite_rows(correlation_rows, max_features_per_target=max_lasso_features)
    summary_rows = [
        {
            "status": _diagnostic_status(matrix_rows, feature_ids, pca_rows, lasso_lite_rows),
            "condition_count": len(matrix_rows),
            "numeric_feature_count": len(feature_ids),
            "target_count": len(target_features),
            "pca_component_count": _pca_component_count(pca_rows),
            "cluster_count": len({str(row.get("cluster_id", "")) for row in cluster_rows if row.get("cluster_id")}),
            "lasso_lite_feature_count": len(lasso_lite_rows),
            "sample_status": _sample_status(len(matrix_rows)),
            "guidance": _diagnostic_guidance(matrix_rows, feature_ids, target_features, pca_rows, lasso_lite_rows),
        }
    ]
    return MlDiagnosticsTables(summary_rows, pca_rows, loading_rows, cluster_rows, lasso_lite_rows)


def pearson_correlation(xs: list[float], ys: list[float]) -> float | None:
    """Return Pearson r, or None if variance is zero."""

    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    dx = [value - mean_x for value in xs]
    dy = [value - mean_y for value in ys]
    denom = math.sqrt(sum(value * value for value in dx) * sum(value * value for value in dy))
    if denom == 0:
        return None
    return sum(x * y for x, y in zip(dx, dy)) / denom


def _write_outputs(
    files: dict[str, str],
    correlation_rows: list[dict[str, object]],
    prior_rows: list[dict[str, object]],
    context_rows: list[dict[str, object]],
    summary_rows: list[dict[str, object]],
    diagnostics: MlDiagnosticsTables,
    parameters: dict[str, object] | None = None,
) -> None:
    write_csv(files["correlations"], correlation_rows)
    write_csv(files["prior_scores"], prior_rows)
    write_csv(files["context_policy"], context_rows)
    write_csv(files["summary"], summary_rows)
    write_csv(files["diagnostic_summary"], diagnostics.summary_rows)
    write_csv(files["pca_scores"], diagnostics.pca_rows)
    write_csv(files["feature_loadings"], diagnostics.loading_rows)
    write_csv(files["condition_clusters"], diagnostics.cluster_rows)
    write_csv(files["lasso_lite_coefficients"], diagnostics.lasso_lite_rows)
    write_json(
        files["manifest"],
        {
            "schema_version": "0.1.0",
            "status": summary_rows[0].get("status", "") if summary_rows else "",
            "correlation_count": len(correlation_rows),
            "prior_count": len(prior_rows),
            "context_policy_count": len(context_rows),
            "pca_score_count": len(diagnostics.pca_rows),
            "condition_cluster_count": len(diagnostics.cluster_rows),
            "lasso_lite_feature_count": len(diagnostics.lasso_lite_rows),
            "parameters": parameters or {},
            "files": files,
        },
    )


def _result(
    output: Path,
    files: dict[str, str],
    status: str,
    message: str,
    summary_rows: list[dict[str, object]],
    correlation_rows: list[dict[str, object]],
    prior_rows: list[dict[str, object]],
) -> MlAnalysisResult:
    return MlAnalysisResult(status, str(output), message, files, summary_rows, correlation_rows, prior_rows)


def _feature_columns(matrix_rows: list[dict[str, str]]) -> list[str]:
    if not matrix_rows:
        return []
    return [column for column in matrix_rows[0].keys() if column != "condition"]


def _paired_numeric_values(
    matrix_rows: list[dict[str, str]],
    feature: str,
    target: str,
) -> list[tuple[float, float]]:
    pairs = []
    for row in matrix_rows:
        feature_value = _to_float(row.get(feature))
        target_value = _to_float(row.get(target))
        if feature_value is not None and target_value is not None:
            pairs.append((feature_value, target_value))
    return pairs


def _standardized_feature_matrix(
    matrix_rows: list[dict[str, str]],
    candidate_features: list[str],
) -> tuple[list[str], list[str], list[list[float]]]:
    conditions = [
        str(row.get("condition") or f"condition_{index + 1}")
        for index, row in enumerate(matrix_rows)
    ]
    retained_features: list[str] = []
    stats: dict[str, tuple[float, float]] = {}
    for feature in candidate_features:
        values = [_to_float(row.get(feature)) for row in matrix_rows]
        numeric = [value for value in values if value is not None]
        if len(numeric) < 2:
            continue
        mean = sum(numeric) / len(numeric)
        variance = sum((value - mean) ** 2 for value in numeric) / max(1, len(numeric) - 1)
        sd = math.sqrt(variance)
        if sd == 0:
            continue
        retained_features.append(feature)
        stats[feature] = (mean, sd)

    standardized: list[list[float]] = []
    for row in matrix_rows:
        standardized_row = []
        for feature in retained_features:
            mean, sd = stats[feature]
            value = _to_float(row.get(feature))
            standardized_row.append(((value if value is not None else mean) - mean) / sd)
        standardized.append(standardized_row)
    return conditions, retained_features, standardized


def _build_pca_tables(
    conditions: list[str],
    feature_ids: list[str],
    standardized: list[list[float]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if len(conditions) < 2 or not feature_ids or not standardized:
        return [], []
    covariance = _covariance_matrix(standardized, len(feature_ids))
    total_variance = sum(covariance[index][index] for index in range(len(feature_ids)))
    if total_variance <= 0:
        return [], []

    pc1, eigen1 = _first_component(covariance)
    pc2: list[float] = [0.0 for _ in feature_ids]
    eigen2 = 0.0
    if len(feature_ids) > 1 and eigen1 > 0:
        deflated = _deflate_matrix(covariance, pc1, eigen1)
        pc2, eigen2 = _first_component(deflated)
        if eigen2 < 1e-12:
            pc2 = [0.0 for _ in feature_ids]
            eigen2 = 0.0

    pc1_var = eigen1 / total_variance if total_variance else 0.0
    pc2_var = eigen2 / total_variance if total_variance else 0.0
    pca_rows = []
    for condition, values in zip(conditions, standardized):
        pca_rows.append(
            {
                "condition": condition,
                "pc1": round(_dot(values, pc1), 6),
                "pc2": round(_dot(values, pc2), 6),
                "explained_variance_pc1": round(pc1_var, 6),
                "explained_variance_pc2": round(pc2_var, 6),
                "sample_status": _sample_status(len(conditions)),
                "status": "exploratory_pca",
            }
        )
    loading_rows = []
    for feature_id, pc1_value, pc2_value in zip(feature_ids, pc1, pc2):
        feature_type, entity_id = _split_feature_id(feature_id)
        loading_rows.append(
            {
                "feature_id": feature_id,
                "feature_type": feature_type,
                "entity_type": _feature_entity_type(feature_id),
                "entity_id": entity_id,
                "pc1_loading": round(pc1_value, 6),
                "pc2_loading": round(pc2_value, 6),
            }
        )
    return pca_rows, loading_rows


def _build_cluster_rows(
    pca_rows: list[dict[str, object]],
    max_clusters: int = 2,
) -> list[dict[str, object]]:
    if len(pca_rows) < 2:
        return []
    points = [(_to_float(row.get("pc1")) or 0.0, _to_float(row.get("pc2")) or 0.0) for row in pca_rows]
    cluster_count = min(max(1, max_clusters), len(points))
    if cluster_count < 2:
        return []
    centroids = _initial_centroids(points, cluster_count)
    assignments = [0 for _ in points]
    for _iteration in range(25):
        new_assignments = [_nearest_centroid(point, centroids) for point in points]
        if new_assignments == assignments:
            break
        assignments = new_assignments
        centroids = _update_centroids(points, assignments, centroids)

    rows = []
    for row, point, assignment in zip(pca_rows, points, assignments):
        distance = _euclidean(point, centroids[assignment])
        rows.append(
            {
                "condition": row.get("condition", ""),
                "cluster_id": f"cluster_{assignment + 1}",
                "pc1": row.get("pc1", ""),
                "pc2": row.get("pc2", ""),
                "distance_to_centroid": round(distance, 6),
                "method": "kmeans_on_pca",
                "sample_status": _sample_status(len(pca_rows)),
                "status": "exploratory_cluster",
            }
        )
    return rows


def _build_lasso_lite_rows(
    correlation_rows: list[dict[str, object]],
    max_features_per_target: int = 5,
    min_abs_coefficient: float = 0.35,
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in correlation_rows:
        abs_coefficient = _to_float(row.get("abs_pearson_r"))
        if abs_coefficient is None or abs_coefficient < min_abs_coefficient:
            continue
        grouped.setdefault(str(row.get("target_feature_id", "")), []).append(row)

    rows: list[dict[str, object]] = []
    for target, candidates in sorted(grouped.items()):
        ranked = sorted(
            candidates,
            key=lambda row: (-float(row.get("abs_pearson_r", 0)), str(row.get("feature_id", ""))),
        )[:max_features_per_target]
        for rank, row in enumerate(ranked, start=1):
            feature_id = str(row.get("feature_id", ""))
            feature_type, entity_id = _split_feature_id(feature_id)
            rows.append(
                {
                    "target_feature_id": target,
                    "target_entity_id": row.get("target_entity_id", ""),
                    "feature_id": feature_id,
                    "feature_type": feature_type,
                    "entity_type": row.get("entity_type", ""),
                    "entity_id": entity_id,
                    "coefficient": row.get("pearson_r", ""),
                    "abs_coefficient": row.get("abs_pearson_r", ""),
                    "selection_rank": rank,
                    "selection_status": "selected_sparse_proxy",
                    "sample_status": row.get("sample_status", ""),
                    "note": "LASSO-lite sparse screen based on standardized univariate association; exploratory only.",
                }
            )
    return rows


def _covariance_matrix(standardized: list[list[float]], width: int) -> list[list[float]]:
    denom = max(1, len(standardized) - 1)
    return [
        [
            sum(row[i] * row[j] for row in standardized) / denom
            for j in range(width)
        ]
        for i in range(width)
    ]


def _first_component(matrix: list[list[float]]) -> tuple[list[float], float]:
    width = len(matrix)
    if width == 0:
        return [], 0.0
    seed = [1.0 / (index + 1) for index in range(width)]
    seed_norm = math.sqrt(sum(value * value for value in seed))
    vector = [value / seed_norm for value in seed]
    for _iteration in range(60):
        next_vector = [_dot(row, vector) for row in matrix]
        norm = math.sqrt(sum(value * value for value in next_vector))
        if norm == 0:
            return [0.0 for _ in range(width)], 0.0
        next_vector = [value / norm for value in next_vector]
        if sum(abs(a - b) for a, b in zip(next_vector, vector)) < 1e-10:
            vector = next_vector
            break
        vector = next_vector
    eigenvalue = _dot(vector, [_dot(row, vector) for row in matrix])
    return vector, max(0.0, eigenvalue)


def _deflate_matrix(matrix: list[list[float]], vector: list[float], eigenvalue: float) -> list[list[float]]:
    return [
        [
            matrix[i][j] - eigenvalue * vector[i] * vector[j]
            for j in range(len(vector))
        ]
        for i in range(len(vector))
    ]


def _dot(xs: list[float], ys: list[float]) -> float:
    return sum(x * y for x, y in zip(xs, ys))


def _initial_centroids(points: list[tuple[float, float]], cluster_count: int) -> list[tuple[float, float]]:
    ranked = sorted(points)
    if cluster_count == 2:
        return [ranked[0], ranked[-1]]
    return [ranked[round(index * (len(ranked) - 1) / (cluster_count - 1))] for index in range(cluster_count)]


def _nearest_centroid(point: tuple[float, float], centroids: list[tuple[float, float]]) -> int:
    distances = [_euclidean(point, centroid) for centroid in centroids]
    return min(range(len(distances)), key=lambda index: distances[index])


def _update_centroids(
    points: list[tuple[float, float]],
    assignments: list[int],
    previous: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    centroids: list[tuple[float, float]] = []
    for cluster_index, old_centroid in enumerate(previous):
        members = [point for point, assignment in zip(points, assignments) if assignment == cluster_index]
        if not members:
            centroids.append(old_centroid)
            continue
        centroids.append(
            (
                sum(point[0] for point in members) / len(members),
                sum(point[1] for point in members) / len(members),
            )
        )
    return centroids


def _euclidean(left: tuple[float, float], right: tuple[float, float]) -> float:
    return math.sqrt((left[0] - right[0]) ** 2 + (left[1] - right[1]) ** 2)


def _split_feature_id(feature_id: str) -> tuple[str, str]:
    if "::" not in feature_id:
        return feature_id, ""
    feature_type, entity_id = feature_id.split("::", 1)
    return feature_type, entity_id


def _feature_entity_type(feature_id: str) -> str:
    feature_type, _entity_id = _split_feature_id(feature_id)
    if feature_type.endswith("_gene"):
        return "gene"
    if feature_type.endswith("_reaction") or feature_type.endswith("_flux"):
        return "reaction"
    return ""


def _model_target_id(entity_type: str, entity_id: str) -> str:
    if entity_type == "reaction" and entity_id and not entity_id.startswith("R_"):
        return f"R_{entity_id}"
    return entity_id


def _association_strength(abs_score: float) -> str:
    if abs_score >= 0.8:
        return "strong"
    if abs_score >= 0.5:
        return "moderate"
    return "weak"


def _ml_evidence(score: float, abs_score: float) -> str:
    if abs_score < 0.5:
        return "weak_association"
    return "positive_association" if score > 0 else "negative_association"


def _context_action(score: float, abs_score: float) -> str:
    if abs_score < 0.5:
        return "neutral"
    return "support" if score > 0 else "penalize"


def _reaction_penalty(score: float, abs_score: float) -> float:
    if abs_score < 0.5:
        return 0.0
    return round(1.0 - abs_score if score > 0 else abs_score, 6)


def _analysis_guidance(
    matrix_rows: list[dict[str, str]],
    target_features: list[str],
    correlation_rows: list[dict[str, object]],
) -> str:
    if not matrix_rows:
        return "No matrix rows were available."
    if not target_features:
        return "No phenotype target features were found. Add flux/growth/yield targets for supervised ML analysis."
    if len(matrix_rows) < 4:
        return "Very few conditions are available; treat correlations as exploratory soft evidence only."
    if not correlation_rows:
        return "No feature-target pairs had enough numeric overlap."
    return "Correlation ranking is available; use ML priors as soft evidence alongside omics and FBA results."


def _empty_diagnostics(status: str, guidance: str) -> MlDiagnosticsTables:
    return MlDiagnosticsTables(
        summary_rows=[
            {
                "status": status,
                "condition_count": 0,
                "numeric_feature_count": 0,
                "target_count": 0,
                "pca_component_count": 0,
                "cluster_count": 0,
                "lasso_lite_feature_count": 0,
                "sample_status": "missing",
                "guidance": guidance,
            }
        ],
        pca_rows=[],
        loading_rows=[],
        cluster_rows=[],
        lasso_lite_rows=[],
    )


def _diagnostic_status(
    matrix_rows: list[dict[str, str]],
    feature_ids: list[str],
    pca_rows: list[dict[str, object]],
    lasso_lite_rows: list[dict[str, object]],
) -> str:
    if not matrix_rows:
        return "missing_matrix"
    if not feature_ids:
        return "insufficient_numeric_features"
    if pca_rows or lasso_lite_rows:
        return "completed"
    return "completed_no_diagnostics"


def _pca_component_count(pca_rows: list[dict[str, object]]) -> int:
    if not pca_rows:
        return 0
    first = pca_rows[0]
    pc2 = _to_float(first.get("explained_variance_pc2")) or 0.0
    return 2 if pc2 > 0 else 1


def _sample_status(condition_count: int) -> str:
    if condition_count < 2:
        return "insufficient_n"
    if condition_count < 6:
        return "low_n_exploratory"
    return "exploratory"


def _diagnostic_guidance(
    matrix_rows: list[dict[str, str]],
    feature_ids: list[str],
    target_features: list[str],
    pca_rows: list[dict[str, object]],
    lasso_lite_rows: list[dict[str, object]],
) -> str:
    if not matrix_rows:
        return "No matrix rows were available."
    if not feature_ids:
        return "No non-constant numeric ML features were available for PCA or clustering."
    if len(matrix_rows) < 6:
        return "PCA, k-means, and LASSO-lite outputs are exploratory because the condition count is small."
    if not target_features:
        return "PCA and k-means are available, but no phenotype target was available for LASSO-lite screening."
    if pca_rows and lasso_lite_rows:
        return "Exploratory PCA, k-means clusters, and sparse feature screening are available for review."
    return "Exploratory ML diagnostics were generated where enough numeric overlap was available."


def _summary_row(
    status: str,
    target_count: int,
    candidate_feature_count: int,
    correlation_count: int,
    prior_count: int,
    guidance: str,
) -> dict[str, object]:
    return {
        "status": status,
        "target_count": target_count,
        "candidate_feature_count": candidate_feature_count,
        "correlation_count": correlation_count,
        "prior_count": prior_count,
        "guidance": guidance,
    }


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
