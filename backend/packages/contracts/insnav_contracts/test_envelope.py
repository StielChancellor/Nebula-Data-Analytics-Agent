"""
Contract tests — these enforce the load-bearing properties of the envelope.
"""
from insnav_contracts import (
    AgentMessage,
    AgentResult,
    AgentName,
    Intent,
    DataHealthBadge,
    InterpretationEcho,
)
from insnav_contracts.envelope import compute_inputs_hash


def test_inputs_hash_is_deterministic() -> None:
    """PRD § Determinism: identical inputs → identical hash, even with key reorder."""
    a = {"metric": "revenue", "dims": ["city"], "filters": [{"f": "country", "v": "IN"}]}
    b = {"filters": [{"v": "IN", "f": "country"}], "dims": ["city"], "metric": "revenue"}
    assert compute_inputs_hash(a) == compute_inputs_hash(b)


def test_agent_message_roundtrip() -> None:
    msg = AgentMessage(
        trace_id="t1",
        agent_from=AgentName.ORCHESTRATOR,
        agent_to=AgentName.SEMANTIC,
        intent=Intent.INTERPRET,
        payload={"q": "revenue by city last 30 days"},
        context_refs=["conv-123"],
    )
    data = msg.model_dump_json()
    restored = AgentMessage.model_validate_json(data)
    assert restored.agent_from == "orchestrator"
    assert restored.intent == "interpret"


def test_agent_result_requires_confidence_and_inputs_hash() -> None:
    """Two fields without which the swarm's mitigations don't work."""
    result = AgentResult(
        result={"rows": [["Mumbai", 12400000]], "columns": ["city", "revenue"]},
        method_used="cube_query",
        assumptions_checked=["sample_size>=30", "no_seasonality_break"],
        confidence=0.93,
        inputs_hash=compute_inputs_hash({"q": "revenue by city"}),
        interpretation_echo=InterpretationEcho(
            text="Net revenue by billing city for the last 30 complete days",
            confidence=0.93,
            metric="revenue",
            dimensions=["city"],
        ),
        data_health=DataHealthBadge(status="ok", coverage_rate=0.97),
    )
    payload = result.model_dump()
    assert payload["confidence"] == 0.93
    assert payload["data_health"]["status"] == "ok"
    assert payload["interpretation_echo"]["metric"] == "revenue"
