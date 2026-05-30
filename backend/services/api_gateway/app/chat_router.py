"""
Chat endpoint (Phase 6) — natural-language question → governed answer.

Wires the agent swarm: builds the tenant's Cube catalog + dataset health, runs
the orchestrator (LLM selects, Cube computes), and returns a ChatAnswer with the
interpretation echo, data-health badge, and the Cube query that ran.

LLM: get_default_router() (Gemini when configured + [llm] installed; else a
stub → the orchestrator will clarify because the stub can't produce a real
interpretation). Cube: the deployed service when INSNAV_CUBE_API_URL is set,
else the offline stub (results flagged illustrative).

Determinism: identical (tenant, question, datasets) returns the cached answer
(canonical-hash cache).
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from insnav_agents import ChatAnswer, answer_question
from insnav_cube_client import CubeQueryClient, build_tenant_schemas
from insnav_contracts.envelope import compute_inputs_hash
from insnav_graph_store import list_approved_edges
from insnav_llm_router import get_default_router
from pydantic import BaseModel, Field

from services.api_gateway.app.auth import Principal, current_principal
from services.api_gateway.app.datasets import (
    get_column_profiles,
    list_datasets_for_tenant,
)
from services.api_gateway.app.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# Per-process canonical-hash cache. Phase 9 moves this to Redis/Firestore with a
# snapshot-version key; in-process is enough for MVP determinism.
_CACHE: dict[str, ChatAnswer] = {}


def reset_chat_cache() -> None:
    _CACHE.clear()


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    # Empty → all of the tenant's ready datasets.
    dataset_ids: list[str] = Field(default_factory=list)


@router.post("/v1/chat", response_model=ChatAnswer)
async def chat(
    req: ChatRequest,
    principal: Annotated[Principal, Depends(current_principal)],
) -> ChatAnswer:
    settings = get_settings()
    cache_key = compute_inputs_hash(
        {"t": principal.tenant_id, "q": req.question, "ds": sorted(req.dataset_ids)}
    )
    cached = _CACHE.get(cache_key)
    if cached is not None:
        return cached

    schemas, health = _catalog_and_health(principal.tenant_id, req.dataset_ids)

    llm = get_default_router()
    cube = CubeQueryClient(
        api_url=settings.cube_api_url,
        api_secret=settings.cube_api_secret,
        offline=settings.offline_mode or not settings.cube_api_url,
    )

    answer = await answer_question(
        req.question,
        tenant_id=principal.tenant_id,
        schemas=schemas,
        dataset_health=health,
        router=llm,
        cube_client=cube,
    )

    # Audit (Phase 9 → BQ audit.queries). For now, structured log.
    logger.info(
        "chat tenant=%s kind=%s level=%s conf=%.2f hash=%s",
        principal.tenant_id, answer.kind, answer.analysis_level,
        answer.confidence, answer.inputs_hash[:12],
    )

    if answer.kind == "answer":
        _CACHE[cache_key] = answer
    return answer


def _catalog_and_health(tenant_id: str, dataset_ids: list[str]):
    datasets = [d for d in list_datasets_for_tenant(tenant_id) if d.status == "ready"]
    if dataset_ids:
        wanted = set(dataset_ids)
        datasets = [d for d in datasets if d.id in wanted]

    columns_by_dataset = {d.id: get_column_profiles(d.id) for d in datasets}
    edges = [e.model_dump() for e in list_approved_edges(tenant_id)]
    schemas = build_tenant_schemas(
        datasets=[d.model_dump() for d in datasets],
        columns_by_dataset=columns_by_dataset,
        edges=edges,
    )
    health = [
        {
            "id": d.id, "label": d.label, "last_refreshed": d.updated_at,
            "row_count": d.row_count, "status": d.status,
        }
        for d in datasets
    ]
    return schemas, health
