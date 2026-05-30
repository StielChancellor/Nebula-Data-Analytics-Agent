"""
Knowledge-graph edge endpoints.

PRD § 4.3: this is the headline UX — admin reviews edge proposals and
confirms which become real joins. Without confirmation, no Cube join can
reference the relationship; the agent swarm physically cannot connect
those two datasets.

Endpoints:
  GET  /v1/edges                          — approved edges (the "real" graph)
  GET  /v1/edges/proposals                — pending review
  POST /v1/edges/{id}/approve             — admin approves
  POST /v1/edges/{id}/reject              — admin rejects
  POST /v1/datasets/{id}/discover-edges   — manual re-run of the proposer
                                            (auto-runs on upload complete)
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from insnav_graph_store import (
    GraphEdge,
    approve_edge as store_approve,
    list_approved_edges,
    list_proposed_edges,
    reject_edge as store_reject,
)
from insnav_graph_store.store import get_edge

from services.api_gateway.app.auth import Principal, current_principal
from services.api_gateway.app.datasets import get_dataset as get_ds
from services.api_gateway.app.edge_proposer import propose_for_dataset

logger = logging.getLogger(__name__)

router = APIRouter(tags=["edges"])


@router.get("/v1/edges", response_model=list[GraphEdge])
def list_edges(
    principal: Annotated[Principal, Depends(current_principal)],
) -> list[GraphEdge]:
    return list_approved_edges(principal.tenant_id)


@router.get("/v1/edges/proposals", response_model=list[GraphEdge])
def list_proposals(
    principal: Annotated[Principal, Depends(current_principal)],
) -> list[GraphEdge]:
    return list_proposed_edges(principal.tenant_id)


@router.post("/v1/edges/{edge_id}/approve", response_model=GraphEdge)
def approve(
    edge_id: str,
    principal: Annotated[Principal, Depends(current_principal)],
) -> GraphEdge:
    edge = get_edge(edge_id)
    if edge is None or edge.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "edge not found")
    approved = store_approve(edge_id, reviewer_email=principal.email)

    # Phase 5b: a newly-approved edge changes the Cube model (it becomes a
    # join). Re-publish so the deployed Cube container picks it up. Wrapped
    # in try/except — a sync hiccup must not roll back the approval.
    try:
        from services.api_gateway.app.cube_sync_service import sync_tenant

        sync_tenant(principal.tenant_id)
    except Exception:  # noqa: BLE001
        logger.exception("cube model sync after approve failed (edge %s)", edge_id)

    return approved


@router.post("/v1/edges/{edge_id}/reject", response_model=GraphEdge)
def reject(
    edge_id: str,
    principal: Annotated[Principal, Depends(current_principal)],
) -> GraphEdge:
    edge = get_edge(edge_id)
    if edge is None or edge.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "edge not found")
    return store_reject(edge_id, reviewer_email=principal.email)


@router.post("/v1/datasets/{dataset_id}/discover-edges", response_model=list[GraphEdge])
def discover_for_dataset(
    dataset_id: str,
    principal: Annotated[Principal, Depends(current_principal)],
) -> list[GraphEdge]:
    """
    Manual re-run of the proposer for a single dataset. Useful after fixing
    a bad load, or when the user wants to refresh proposals without
    re-uploading. (Auto-runs on /uploads/complete.)
    """
    ds = get_ds(dataset_id)
    if ds is None or ds.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dataset not found")
    if ds.status != "ready":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"dataset not ready (current status: {ds.status})",
        )
    return propose_for_dataset(ds)
