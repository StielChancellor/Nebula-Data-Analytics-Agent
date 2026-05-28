"""
Inter-agent message and result envelopes.

PRD § Agent swarm wiring + § Hard constraints #1:
    - Every agent call MUST return an AgentResult; that's how Critic and the
      Orchestrator verify provenance and detect drift.
    - The envelope is the extraction boundary: v1 agents are in-process Python
      modules, but the envelope is shaped exactly as it would be over RPC,
      so extracting an agent to its own Cloud Run service later is a port,
      not a refactor.
"""
from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentName(str, Enum):
    """The 7 agents in the swarm (PRD § L4)."""

    ORCHESTRATOR = "orchestrator"
    SEMANTIC = "semantic"
    GRAPH = "graph"
    STATS = "stats"
    MATHS = "maths"
    CRITIC = "critic"
    DATA_QUALITY = "data_quality"


class Intent(str, Enum):
    """Verbs in the inter-agent protocol."""

    INTERPRET = "interpret"   # turn a user question into a structured query
    COMPUTE = "compute"       # run a deterministic computation (Cube / sandbox)
    VERIFY = "verify"         # Critic re-checks an interpretation / assumptions
    NARRATE = "narrate"       # LLM-narrate a result (LAST step only)


class AgentMessage(BaseModel):
    """
    Envelope passed between agents (in-process v1, RPC later).

    PRD § Agent swarm wiring — keep these fields stable; downstream code
    relies on `trace_id` for correlation across logs/audit.
    """

    model_config = ConfigDict(use_enum_values=True, extra="forbid")

    trace_id: str
    parent_span: str | None = None
    agent_from: AgentName
    agent_to: AgentName
    intent: Intent
    payload: dict[str, Any] = Field(default_factory=dict)
    context_refs: list[str] = Field(default_factory=list)
    """conversation_id, prior result_ids — how Critic loads the original interpretation"""
    deadline_ms: int = 60_000


class InterpretationEcho(BaseModel):
    """
    The plain-English re-statement of the user's question, shown back to them.
    PRD failure-mode mitigation #2 (existential — wrong-question prevention).
    """

    model_config = ConfigDict(extra="forbid")

    text: str
    confidence: float = Field(ge=0.0, le=1.0)
    metric: str | None = None
    dimensions: list[str] = Field(default_factory=list)
    filters: list[str] = Field(default_factory=list)
    attribution_model: str | None = None


class DataHealthBadge(BaseModel):
    """
    Freshness + completeness + coverage per source feeding the answer.
    PRD failure-mode mitigation #3 (existential — silent data-quality).
    If any source is failed, status MUST be 'block' or 'warn' and the
    Orchestrator MUST surface this to the user.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "warn", "block"]
    freshness: list[dict[str, Any]] = Field(default_factory=list)
    completeness: list[dict[str, Any]] = Field(default_factory=list)
    coverage_rate: float | None = None
    warnings: list[str] = Field(default_factory=list)


class AgentResult(BaseModel):
    """
    MANDATORY return shape from every agent invocation.

    Why every field is required:
      result               — the actual output (chart spec, table rows, ...)
      method_used          — names the deterministic technique (cube_query,
                             diff_in_diff, prophet, ...). Used by Critic.
      assumptions_checked  — what the agent verified before returning
      confidence           — 0..1 calibrated. Below threshold → Orchestrator
                             asks a clarifying question instead of answering.
      caveats              — human-readable caveats appended to narration
      inputs_hash          — SHA256 of normalized inputs; used to detect drift
                             across identical calls (determinism test)
      version              — agent module version for reproducibility
    """

    model_config = ConfigDict(use_enum_values=True, extra="forbid")

    result: Any
    method_used: str
    assumptions_checked: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    caveats: list[str] = Field(default_factory=list)
    inputs_hash: str
    version: str = "0.1.0"
    interpretation_echo: InterpretationEcho | None = None
    data_health: DataHealthBadge | None = None


class ResultEnvelopeError(BaseModel):
    """
    Returned when an agent CANNOT compute (vs. computed-with-warnings).
    PRD § Hard constraint #5: the platform must be able to say "I don't know."
    """

    model_config = ConfigDict(extra="forbid")

    code: Literal[
        "no_confirmed_edge",       # cross-dataset join requested but graph has no edge
        "data_unavailable",        # source failed to load
        "ambiguous_question",      # confidence below threshold; asking for clarification
        "metric_undefined",        # requested metric has no Cube definition
        "sandbox_timeout",         # compute exceeded budget
        "provider_error",          # LLM router / external dependency failure
    ]
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


# ---------- helpers ----------

def compute_inputs_hash(payload: dict[str, Any]) -> str:
    """
    Canonicalize a payload (sorted keys, no whitespace) and SHA256 it.
    Two identical agent inputs MUST produce the same hash; this is what
    the determinism test asserts.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
