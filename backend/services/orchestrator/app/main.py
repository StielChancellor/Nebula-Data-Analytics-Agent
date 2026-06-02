# NOT DEPLOYED - Phase-0 scaffold only. The real logic runs IN-PROCESS in
# services/api_gateway (swarm/onboarding/ingestion/edge_proposer). This file is
# an extraction boundary for future independent scaling; no Cloud Run resource
# points at it. See backend/README.md.
"""
orchestrator — hosts all 7 agents in-process v1 (per PRD D5).

Phase 0: stub. Phase 6+ builds the actual swarm protocol on top of the
insnav_contracts.AgentMessage envelope.
"""
from fastapi import FastAPI

app = FastAPI(title="Insights Navigator V2.0 — Orchestrator", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "orchestrator", "version": "0.1.0"}
