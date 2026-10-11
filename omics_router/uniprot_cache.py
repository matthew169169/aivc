"""Small UniProt REST cache used by the optional semantic-QC enrichment layer."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable


UNIPROT_REST_URL = "https://rest.uniprot.org/uniprotkb/{accession}.json"
EC_RE = re.compile(r"\b\d+\.(?:\d+|-)\.(?:\d+|-)\.(?:\d+|-)\b")
FetchFunc = Callable[[str], dict[str, Any]]


def load_or_fetch_uniprot_records(
    accessions: list[str] | set[str],
    cache_dir: str | Path,
    enable_network: bool = False,
    timeout_seconds: int = 10,
    fetcher: FetchFunc | None = None,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, object]]]:
    """Load parsed UniProt records from cache, optionally fetching missing accessions."""

    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    records: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, object]] = []
    for accession in sorted({normalize_accession(value) for value in accessions if normalize_accession(value)}):
        cache_path = cache_path_for_accession(cache, accession)
        error = ""
        record: dict[str, Any] | None = None
        status = "missing_not_fetched"
        if cache_path.exists() and cache_path.stat().st_size > 0:
            try:
                record = json.loads(cache_path.read_text(encoding="utf-8"))
                status = "cache_hit"
            except json.JSONDecodeError as exc:
                error = f"cache_decode_error: {exc}"
                record = None
                status = "cache_error"
        if record is None and enable_network:
            try:
                raw = fetcher(accession) if fetcher else fetch_uniprot_json(accession, timeout_seconds=timeout_seconds)
                record = parse_uniprot_json(raw, fallback_accession=accession)
                cache_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
                status = "fetched"
            except Exception as exc:  # pragma: no cover - real network path varies by platform
                error = str(exc)
                status = "fetch_failed"
        if record is not None:
            record = {**record, "_source_status": status}
            records[accession] = record
        rows.append(record_status_row(accession, status, record, cache_path, error))
    return records, rows


def fetch_uniprot_json(accession: str, timeout_seconds: int = 10) -> dict[str, Any]:
    """Fetch one UniProtKB JSON record by accession using the public REST endpoint."""

    url = UNIPROT_REST_URL.format(accession=normalize_accession(accession))
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Omics-GEM-Router/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"UniProt REST returned HTTP {exc.code} for {accession}") from exc


def parse_uniprot_json(raw: dict[str, Any], fallback_accession: str = "") -> dict[str, Any]:
    """Normalize the subset of UniProtKB JSON needed by semantic model QC."""

    protein_description = raw.get("proteinDescription") if isinstance(raw.get("proteinDescription"), dict) else {}
    protein_name = first_protein_name(protein_description)
    ec_numbers = sorted(extract_ec_numbers_from_json(raw) | ec_numbers_from_protein_description(protein_description))
    gene_names = sorted(extract_gene_names(raw.get("genes", [])))
    organism = ""
    if isinstance(raw.get("organism"), dict):
        organism = str(raw["organism"].get("scientificName") or raw["organism"].get("commonName") or "")
    entry_type = str(raw.get("entryType", ""))
    return {
        "accession": normalize_accession(raw.get("primaryAccession") or fallback_accession),
        "reviewed_status": reviewed_status_from_entry_type(entry_type),
        "entry_type": entry_type,
        "protein_name": protein_name,
        "ec_numbers": ec_numbers,
        "gene_names": gene_names,
        "organism": organism,
    }


def record_status_row(
    accession: str,
    status: str,
    record: dict[str, Any] | None,
    cache_path: Path,
    error: str = "",
) -> dict[str, object]:
    record = record or {}
    return {
        "accession": accession,
        "cache_status": status,
        "reviewed_status": record.get("reviewed_status", ""),
        "protein_name": record.get("protein_name", ""),
        "ec_numbers": ";".join(record.get("ec_numbers", [])),
        "gene_names": ";".join(record.get("gene_names", [])),
        "organism": record.get("organism", ""),
        "cache_path": str(cache_path),
        "error": error,
    }


def enrichment_summary_row(
    record_rows: list[dict[str, object]],
    cache_dir: str | Path,
    enable_network: bool,
) -> dict[str, object]:
    """Summarize cache/REST enrichment for UI, report, and manifest."""

    counts = {status: sum(1 for row in record_rows if row.get("cache_status") == status) for status in [
        "cache_hit",
        "fetched",
        "missing_not_fetched",
        "cache_error",
        "fetch_failed",
    ]}
    requested = len(record_rows)
    if not requested:
        status = "no_accessions"
        guidance = "No UniProt accessions were available for cache or REST enrichment."
    elif enable_network and counts["fetch_failed"]:
        status = "rest_completed_with_failures"
        guidance = "UniProt REST enrichment was enabled, but some accessions could not be fetched."
    elif enable_network:
        status = "rest_enabled"
        guidance = "UniProt cache was used and missing accessions were fetched when possible."
    else:
        status = "cache_only"
        guidance = "UniProt REST enrichment was disabled; only existing cache records were used."
    return {
        "status": status,
        "network_access": "enabled" if enable_network else "disabled",
        "requested_accession_count": requested,
        "cache_hit_count": counts["cache_hit"],
        "fetched_count": counts["fetched"],
        "missing_not_fetched_count": counts["missing_not_fetched"],
        "cache_error_count": counts["cache_error"],
        "fetch_failed_count": counts["fetch_failed"],
        "reviewed_count": sum(1 for row in record_rows if row.get("reviewed_status") == "reviewed"),
        "with_ec_count": sum(1 for row in record_rows if row.get("ec_numbers")),
        "cache_dir": str(cache_dir),
        "guidance": guidance,
    }


def cache_path_for_accession(cache_dir: Path, accession: str) -> Path:
    return cache_dir / f"{normalize_accession(accession)}.json"


def normalize_accession(value: object) -> str:
    return str(value or "").strip().upper()


def first_protein_name(protein_description: dict[str, Any]) -> str:
    for key in ("recommendedName", "submissionNames", "alternativeNames"):
        block = protein_description.get(key)
        if isinstance(block, list):
            for item in block:
                name = full_name_value(item)
                if name:
                    return name
        elif isinstance(block, dict):
            name = full_name_value(block)
            if name:
                return name
    return ""


def full_name_value(block: dict[str, Any]) -> str:
    full_name = block.get("fullName") if isinstance(block, dict) else None
    if isinstance(full_name, dict):
        return str(full_name.get("value", ""))
    return ""


def ec_numbers_from_protein_description(protein_description: dict[str, Any]) -> set[str]:
    numbers: set[str] = set()
    for block in iter_name_blocks(protein_description):
        for ec_number in block.get("ecNumbers", []) if isinstance(block, dict) else []:
            if isinstance(ec_number, dict) and ec_number.get("value"):
                numbers.add(str(ec_number["value"]))
    return numbers


def iter_name_blocks(protein_description: dict[str, Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for key in ("recommendedName", "submissionNames", "alternativeNames"):
        value = protein_description.get(key)
        if isinstance(value, dict):
            blocks.append(value)
        elif isinstance(value, list):
            blocks.extend(item for item in value if isinstance(item, dict))
    return blocks


def extract_ec_numbers_from_json(raw: dict[str, Any]) -> set[str]:
    return set(EC_RE.findall(json.dumps(raw, ensure_ascii=False)))


def extract_gene_names(raw_genes: object) -> set[str]:
    names: set[str] = set()
    if not isinstance(raw_genes, list):
        return names
    for gene in raw_genes:
        if not isinstance(gene, dict):
            continue
        for key in ("geneName", "orderedLocusNames", "orfNames", "synonyms"):
            value = gene.get(key)
            if isinstance(value, dict) and value.get("value"):
                names.add(str(value["value"]))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and item.get("value"):
                        names.add(str(item["value"]))
    return names


def reviewed_status_from_entry_type(entry_type: str) -> str:
    text = entry_type.lower()
    if "unreviewed" in text:
        return "unreviewed"
    if "reviewed" in text or "swiss-prot" in text:
        return "reviewed"
    return ""
