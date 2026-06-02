"""
Edge proposer — finds candidate joins between a freshly-profiled dataset
and the existing approved datasets.

PRD § 4.3 / D4 / Hard constraint #2: every Cube join MUST trace to a
human-confirmed graph edge. The proposer's job is to surface the right
candidates so the human-in-the-loop confirmation is fast and accurate.

V1 strategy: **key-overlap via BQ** (no embeddings yet).
  - Only consider columns where the profile's `key_likeness` > THRESHOLD
    on BOTH sides. This cuts noise dramatically — only high-cardinality
    + low-null columns get proposed. Joins between status/category-style
    low-cardinality fields almost never matter.
  - For each candidate pair, run one BQ JOIN query to compute the actual
    overlap %: `COUNT(intersect) / MIN(COUNT(distinct_a), COUNT(distinct_b))`.
  - Only emit a proposal if overlap > MIN_OVERLAP (default 0.5).

Cost: 1 BQ query per candidate column pair. For typical sizes (~5 high-
key-likeness columns per dataset, joining against ~10 existing datasets),
that's ~50 small queries per upload — well within BQ free tier.

Phase 4.5 will add Vertex AI embedding similarity as an additional signal
(name + description + sample values → embedding cosine). The two signals
ranked together cut false positives further.
"""
from __future__ import annotations

import logging
from typing import Any

from insnav_graph_store import GraphEdge, propose_edge

from services.api_gateway.app.datasets import (
    Dataset,
    list_datasets_for_tenant,
)
from services.api_gateway.app.settings import get_settings

logger = logging.getLogger(__name__)

# Tunable thresholds. Conservative defaults — change in PRs only.
KEY_LIKENESS_MIN = 0.7
MIN_OVERLAP_PCT = 0.5


def propose_for_dataset(new_dataset: Dataset) -> list[GraphEdge]:
    """
    Generate edge proposals between `new_dataset` and existing datasets in
    the same tenant. Returns the list of proposals created (or rediscovered
    if idempotent).
    """
    if new_dataset.bq_table is None:
        # Can't compute overlap on a dataset that didn't finish loading
        return []

    # Pull the new dataset's high-key-likeness columns
    new_keys = _high_key_columns(new_dataset.id)
    if not new_keys:
        return []

    # Compare against every other ready dataset in the SAME project workspace
    # (Phase 10). Projects are isolated, so we never propose joins across
    # projects. Legacy datasets without a project_id fall back to tenant-wide.
    if new_dataset.project_id is not None:
        from services.api_gateway.app.datasets import list_datasets_for_project

        candidates = list_datasets_for_project(new_dataset.tenant_id, new_dataset.project_id)
    else:
        candidates = list_datasets_for_tenant(new_dataset.tenant_id)
    peers = [
        d for d in candidates
        if d.id != new_dataset.id and d.status == "ready" and d.bq_table is not None
    ]

    proposals: list[GraphEdge] = []
    for peer in peers:
        peer_keys = _high_key_columns(peer.id)
        for new_col, _new_profile in new_keys:
            for peer_col, _peer_profile in peer_keys:
                try:
                    overlap = _compute_key_overlap(
                        new_table=new_dataset.bq_table,
                        new_column=new_col,
                        peer_table=peer.bq_table,
                        peer_column=peer_col,
                    )
                except Exception as e:  # noqa: BLE001 — one bad query shouldn't stop discovery
                    logger.warning("overlap query failed for %s.%s ↔ %s.%s: %s",
                                   new_dataset.id, new_col, peer.id, peer_col, e)
                    continue

                if overlap["pct"] < MIN_OVERLAP_PCT:
                    continue

                edge = GraphEdge(
                    tenant_id=new_dataset.tenant_id,
                    project_id=new_dataset.project_id,
                    from_dataset=new_dataset.id,
                    from_column=new_col,
                    to_dataset=peer.id,
                    to_column=peer_col,
                    similarity_score=0.0,   # no embeddings yet
                    key_overlap_pct=round(overlap["pct"], 4),
                    from_distinct_count=overlap.get("from_distinct"),
                    to_distinct_count=overlap.get("to_distinct"),
                    sample_overlap=overlap.get("samples", [])[:5],
                )
                created = propose_edge(edge)
                proposals.append(created)

    return proposals


# ---------- internals ----------

def _high_key_columns(dataset_id: str) -> list[tuple[str, dict[str, Any]]]:
    """
    Pull columns where key_likeness > KEY_LIKENESS_MIN from the profile.
    Honors offline_mode by reading from the in-memory column store.
    """
    settings = get_settings()
    if settings.offline_mode:
        from services.api_gateway.app.datasets import _OFFLINE_COLUMNS

        cols = _OFFLINE_COLUMNS.get(dataset_id, {})
        return [
            (name, c)
            for name, c in cols.items()
            if (c.get("key_likeness", 0.0) or 0.0) >= KEY_LIKENESS_MIN
        ]

    from services.api_gateway.app.gcp_clients import firestore_client

    docs = (
        firestore_client()
        .collection(settings.fs_datasets_collection)
        .document(dataset_id)
        .collection("columns")
        .stream()
    )
    out: list[tuple[str, dict[str, Any]]] = []
    for d in docs:
        c = d.to_dict() or {}
        if (c.get("key_likeness", 0.0) or 0.0) >= KEY_LIKENESS_MIN:
            out.append((c["name"], c))
    return out


def _compute_key_overlap(
    new_table: str,
    new_column: str,
    peer_table: str,
    peer_column: str,
) -> dict[str, Any]:
    """
    Return {pct, from_distinct, to_distinct, samples}.

    Overlap % is defined as |distinct values in both| / min(|distinct_a|, |distinct_b|).
    That gives a high score when one side is a subset of the other (typical
    foreign-key relationship), not just when they're the same size.
    """
    settings = get_settings()
    if settings.offline_mode:
        # Synthetic: the offline upload stub creates ("city", "revenue") columns.
        # For tests we return a fixed high-overlap result so the proposer is
        # exercised end-to-end without real BQ.
        return {"pct": 0.85, "from_distinct": 100, "to_distinct": 90, "samples": ["Mumbai", "Pune"]}

    from services.api_gateway.app.gcp_clients import bigquery_client

    sql = build_overlap_sql(new_table, new_column, peer_table, peer_column)
    rows = list(bigquery_client().query(sql).result())
    if not rows:
        return {"pct": 0.0, "from_distinct": 0, "to_distinct": 0, "samples": []}
    r = dict(rows[0].items())
    return {
        "pct": float(r.get("overlap_pct", 0.0) or 0.0),
        "from_distinct": int(r.get("from_distinct") or 0),
        "to_distinct": int(r.get("to_distinct") or 0),
        "samples": [s for s in (r.get("samples") or []) if s is not None],
    }


def build_overlap_sql(new_table: str, new_column: str, peer_table: str, peer_column: str) -> str:
    """
    Build the overlap SQL. Returns a single row with overlap_pct, from_distinct,
    to_distinct, samples (up to 5 shared values).

    Uses CAST to STRING so we can compare across slightly-different inferred
    types (BQ autodetect may give one side INT64 and the other STRING for the
    same logical key).
    """
    return f"""
WITH
  a AS (SELECT DISTINCT CAST(`{new_column}` AS STRING) AS v FROM `{new_table}` WHERE `{new_column}` IS NOT NULL),
  b AS (SELECT DISTINCT CAST(`{peer_column}` AS STRING) AS v FROM `{peer_table}` WHERE `{peer_column}` IS NOT NULL),
  shared AS (SELECT a.v FROM a INNER JOIN b USING (v)),
  counts AS (
    SELECT
      (SELECT COUNT(*) FROM a) AS from_distinct,
      (SELECT COUNT(*) FROM b) AS to_distinct,
      (SELECT COUNT(*) FROM shared) AS shared_distinct
  )
SELECT
  SAFE_DIVIDE(c.shared_distinct, LEAST(c.from_distinct, c.to_distinct)) AS overlap_pct,
  c.from_distinct,
  c.to_distinct,
  ARRAY(SELECT v FROM shared LIMIT 5) AS samples
FROM counts c
"""
