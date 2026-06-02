"""
Agent-led onboarding endpoints (Phase 10-C) — stateful interview.

Chat is stateless, so the interview keeps its own persisted state in the
`ingest_sessions` collection. This router fetches data + persists; the pure
onboarding state machine (insnav_agents.onboarding) drafts questions, parses
corrections, and computes transitions. On completion it persists the
human-confirmed semantics, approves the confirmed join edges, activates the
project, and republishes the Cube model.
"""
from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from insnav_agents import onboarding as ob
from insnav_agents.onboarding_models import (
    AgentQuestion,
    ColumnSemantics,
    IngestSession,
    TranscriptEntry,
)
from insnav_llm_router import build_router

from services.api_gateway.app.auth import Principal, current_principal
from services.api_gateway.app.datasets import (
    get_column_profiles,
    get_dataset,
    save_column_semantics,
    save_dataset,
)
from services.api_gateway.app.projects import (
    Project,
    ProjectMember,
    add_dataset_to_project,
    get_project,
    new_project_id,
    save_project,
    update_project_status,
)

router = APIRouter(prefix="/v1/ingest", tags=["ingest"])


# ---------- session storage (Firestore + offline dict) ----------

_OFFLINE_SESSIONS: dict[str, dict[str, Any]] = {}


def reset_offline_store() -> None:
    _OFFLINE_SESSIONS.clear()


def _offline() -> bool:
    from services.api_gateway.app.settings import get_settings

    return get_settings().offline_mode


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _build_router(model_id: str | None):
    """Force the stub offline so tests + local dev never hit a paid LLM."""
    if _offline():
        return build_router("stub")
    return build_router(model_id)


def _save_session(s: IngestSession) -> None:
    s.updated_at = _now()
    payload = s.model_dump()
    if _offline():
        _OFFLINE_SESSIONS[s.id] = payload
        return
    from services.api_gateway.app.gcp_clients import firestore_client
    from services.api_gateway.app.settings import get_settings

    firestore_client().collection(get_settings().fs_ingest_sessions_collection).document(s.id).set(payload)


def _get_session(session_id: str) -> IngestSession | None:
    if _offline():
        data = _OFFLINE_SESSIONS.get(session_id)
        return IngestSession(**data) if data else None
    from services.api_gateway.app.gcp_clients import firestore_client
    from services.api_gateway.app.settings import get_settings

    doc = (
        firestore_client()
        .collection(get_settings().fs_ingest_sessions_collection)
        .document(session_id)
        .get()
    )
    return IngestSession(**doc.to_dict()) if doc.exists else None


# ---------- request / response shapes ----------

class StartSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: str
    llm: str | None = None


class ReplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str | None = None
    # The draft-review table submits the full edited semantics here.
    semantics_patch: list[ColumnSemantics] | None = None
    # The joins step submits the edge ids the human approved.
    confirmed_edge_ids: list[str] | None = None
    llm: str | None = None


class CompletionResult(BaseModel):
    project_id: str | None = None
    cube_synced: bool = False
    columns_confirmed: int = 0
    joins_approved: int = 0


class SessionResponse(BaseModel):
    session: IngestSession
    agent_message: AgentQuestion | None = None
    completion: CompletionResult | None = None


# ---------- endpoints ----------

@router.post("/sessions", response_model=SessionResponse)
async def start_session(
    req: StartSessionRequest,
    principal: Annotated[Principal, Depends(current_principal)],
) -> SessionResponse:
    ds = get_dataset(req.dataset_id)
    if ds is None or ds.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dataset not found")
    if ds.status != "ready":
        raise HTTPException(status.HTTP_409_CONFLICT, "dataset is not ready to onboard")

    profiles = get_column_profiles(ds.id)
    semantics = ob.build_draft(profiles)
    llm_router = _build_router(req.llm)

    project_name = None
    if ds.project_id:
        step = "draft_review"
        proj = get_project(ds.project_id)
        project_name = proj.name if proj else None
    else:
        step = "project_name"

    session = IngestSession(
        tenant_id=ds.tenant_id,
        project_id=ds.project_id,
        dataset_id=ds.id,
        current_step=step,  # type: ignore[arg-type]
        columns_remaining=[p.get("name", "") for p in profiles],
        semantics=semantics,
    )
    agent_q = await _question_for(session, profiles, project_name, llm_router)
    session.transcript.append(TranscriptEntry(role="agent", step=session.current_step, text=agent_q.prompt))
    _save_session(session)
    return SessionResponse(session=session, agent_message=agent_q)


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: str,
    principal: Annotated[Principal, Depends(current_principal)],
) -> SessionResponse:
    s = _get_session(session_id)
    if s is None or s.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    # Re-derive the current question so a reload can resume.
    return SessionResponse(session=s)


@router.post("/sessions/{session_id}/reply", response_model=SessionResponse)
async def reply(
    session_id: str,
    req: ReplyRequest,
    principal: Annotated[Principal, Depends(current_principal)],
) -> SessionResponse:
    session = _get_session(session_id)
    if session is None or session.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    if session.status != "in_progress":
        return SessionResponse(session=session)

    llm_router = _build_router(req.llm)
    profiles = get_column_profiles(session.dataset_id)
    answer = (req.answer or "").strip()
    session.transcript.append(
        TranscriptEntry(role="user", step=session.current_step, text=answer or "(edited draft)")
    )

    completion: CompletionResult | None = None
    step = session.current_step

    if step == "project_name":
        _create_project_for_session(session, answer or "Untitled project", principal)
        session.current_step = ob.next_step("project_name", has_joins=False)

    elif step == "grain":
        session.grain_description = answer
        session.current_step = ob.next_step("grain", has_joins=False)

    elif step == "draft_review":
        # Structured table edit > free-text chat correction (offline: a no-op).
        if req.semantics_patch:
            for s in req.semantics_patch:
                session.semantics[s.column] = s
        elif answer and not ob.is_affirmative(answer):
            patches = await ob.interpret_correction(answer, session.semantics, llm_router)
            session.semantics.update(patches)
        if ob.is_affirmative(answer):
            has_joins = len(_proposed_edges_for(session)) > 0
            session.current_step = ob.next_step("draft_review", has_joins=has_joins)

    elif step == "joins":
        if req.confirmed_edge_ids is not None:
            session.confirmed_join_edge_ids = req.confirmed_edge_ids
        session.current_step = ob.next_step("joins", has_joins=True)

    elif step == "confirm":
        if ob.is_affirmative(answer):
            completion = _complete_session(session, principal)
            session.current_step = "done"
            session.status = "completed"

    project_name = None
    if session.project_id:
        proj = get_project(session.project_id)
        project_name = proj.name if proj else None

    agent_q: AgentQuestion | None = None
    if session.current_step != "done":
        agent_q = await _question_for(session, profiles, project_name, llm_router)
        session.transcript.append(
            TranscriptEntry(role="agent", step=session.current_step, text=agent_q.prompt)
        )
    _save_session(session)
    return SessionResponse(session=session, agent_message=agent_q, completion=completion)


# ---------- internals ----------

async def _question_for(
    session: IngestSession, profiles: list[dict], project_name: str | None, llm_router
) -> AgentQuestion:
    step = session.current_step
    if step == "project_name":
        return AgentQuestion(
            step="project_name",
            prompt="What should we name this project?",
            question_type="free_text",
        )
    if step == "grain":
        return AgentQuestion(
            step="grain",
            prompt="What does one row represent? (e.g. “one transaction”, “one customer per day”)",
            question_type="free_text",
        )
    if step == "draft_review":
        prompt = await ob.draft_summary(project_name, session.semantics, llm_router)
        return AgentQuestion(
            step="draft_review",
            prompt=prompt,
            question_type="draft_review",
            draft=list(session.semantics.values()),
        )
    if step == "joins":
        edges = _proposed_edges_for(session)
        return AgentQuestion(
            step="joins",
            prompt=f"I found {len(edges)} possible join(s) in this project. Confirm which to use.",
            question_type="confirm",
            context={"edges": [e.model_dump() for e in edges]},
        )
    if step == "confirm":
        c = ob.draft_counts(session.semantics)
        rev = f", {c['revenue']} revenue" if c["revenue"] else ""
        return AgentQuestion(
            step="confirm",
            prompt=(
                f"Ready to build: {c['measure']} measures, {c['dimension']} dimensions{rev}. "
                "Proceed to generate the cube + graph?"
            ),
            question_type="confirm",
        )
    return AgentQuestion(step="done", prompt="Onboarding complete.", question_type="confirm")


def _create_project_for_session(session: IngestSession, name: str, principal: Principal) -> None:
    p = Project(
        id=new_project_id(),
        tenant_id=session.tenant_id,
        brand=principal.brand,
        name=name,
        owner_email=principal.email,
        members=[ProjectMember(email=principal.email, role="owner")],
    )
    save_project(p)
    session.project_id = p.id
    ds = get_dataset(session.dataset_id)
    if ds is not None:
        ds.project_id = p.id
        save_dataset(ds)
        add_dataset_to_project(p.id, ds.id)


def _proposed_edges_for(session: IngestSession) -> list:
    from insnav_graph_store import list_proposed_edges

    return list_proposed_edges(session.tenant_id, session.project_id)


def _complete_session(session: IngestSession, principal: Principal) -> CompletionResult:
    now = _now()
    for s in session.semantics.values():
        s.confirmed_by = principal.email
        s.confirmed_at = now
    save_column_semantics(
        session.dataset_id, {k: v.model_dump() for k, v in session.semantics.items()}
    )

    from insnav_graph_store import approve_edge

    joins_approved = 0
    for eid in session.confirmed_join_edge_ids:
        try:
            approve_edge(eid, reviewer_email=principal.email)
            joins_approved += 1
        except Exception:  # noqa: BLE001 — a stale edge id must not fail completion
            pass

    cube_synced = False
    if session.project_id:
        update_project_status(session.project_id, "active")
        try:
            _resync_project(session.tenant_id, session.project_id)
            cube_synced = True
        except Exception:  # noqa: BLE001 — sync hiccup must not fail completion
            pass

    return CompletionResult(
        project_id=session.project_id,
        cube_synced=cube_synced,
        columns_confirmed=len(session.semantics),
        joins_approved=joins_approved,
    )


def _resync_project(tenant_id: str, project_id: str) -> None:
    """Prefer project-scoped sync (Phase 10-D); fall back to tenant sync."""
    from services.api_gateway.app import cube_sync_service

    if hasattr(cube_sync_service, "sync_project"):
        cube_sync_service.sync_project(tenant_id, project_id)
    else:
        cube_sync_service.sync_tenant(tenant_id)
