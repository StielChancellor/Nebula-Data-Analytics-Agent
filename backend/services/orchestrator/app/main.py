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
