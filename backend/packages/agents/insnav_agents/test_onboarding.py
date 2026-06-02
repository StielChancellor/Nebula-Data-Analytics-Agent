"""Unit tests for the agent-led onboarding state machine (Phase 10-C)."""
from __future__ import annotations

import pytest

from insnav_agents import onboarding as ob
from insnav_llm_router import LLMRouter
from insnav_llm_router.router import LLMResponse, StubProvider


class _FakeProvider:
    name = "stub"
    model = "fake"

    def __init__(self, text: str) -> None:
        self._text = text

    async def generate(self, *, prompt: str, system=None, max_tokens=16384) -> LLMResponse:
        return LLMResponse(text=self._text, model=self.model, provider="stub")


def _router(text: str) -> LLMRouter:
    return LLMRouter(_FakeProvider(text))


# ---------- heuristic draft ----------

class TestHeuristicSemantics:
    def test_numeric_low_key_is_measure(self) -> None:
        s = ob.heuristic_semantics({"name": "amount", "type": "NUMERIC", "key_likeness": 0.1})
        assert s.role == "measure"
        assert s.measure_aggregation == "sum"

    def test_revenue_keyword_guessed_but_unconfirmed(self) -> None:
        # The gate (PRD #3): drafted revenue is a guess; confirmed_by stays None.
        s = ob.heuristic_semantics({"name": "total_revenue", "type": "FLOAT64", "key_likeness": 0.05})
        assert s.role == "measure"
        assert s.is_revenue is True
        assert s.confirmed_by is None

    def test_date_is_time(self) -> None:
        s = ob.heuristic_semantics({"name": "txn_date", "type": "DATE", "key_likeness": 0.0})
        assert s.role == "time"
        assert s.date_granularity == "day"

    def test_high_key_likeness_is_identifier(self) -> None:
        s = ob.heuristic_semantics({"name": "order_id", "type": "STRING", "key_likeness": 0.97})
        assert s.role == "identifier"
        assert s.join_key is True

    def test_plain_string_is_dimension(self) -> None:
        s = ob.heuristic_semantics({"name": "city", "type": "STRING", "key_likeness": 0.2})
        assert s.role == "dimension"

    def test_build_draft_classifies_all(self) -> None:
        profiles = [
            {"name": "city", "type": "STRING", "key_likeness": 0.2},
            {"name": "revenue", "type": "NUMERIC", "key_likeness": 0.05},
            {"name": "txn_date", "type": "DATE", "key_likeness": 0.0},
        ]
        draft = ob.build_draft(profiles)
        assert set(draft) == {"city", "revenue", "txn_date"}
        assert draft["revenue"].role == "measure"


# ---------- transitions ----------

class TestTransitions:
    def test_full_path_with_joins(self) -> None:
        assert ob.next_step("project_name", has_joins=False) == "grain"
        assert ob.next_step("grain", has_joins=False) == "draft_review"
        assert ob.next_step("draft_review", has_joins=True) == "joins"
        assert ob.next_step("joins", has_joins=True) == "confirm"
        assert ob.next_step("confirm", has_joins=True) == "done"

    def test_draft_review_skips_joins_when_none(self) -> None:
        assert ob.next_step("draft_review", has_joins=False) == "confirm"

    def test_affirmative(self) -> None:
        for a in ("yes", "Yes", "looks good", "accept", "LGTM", "build"):
            assert ob.is_affirmative(a) is True
        for a in ("no", "change amount to revenue", ""):
            assert ob.is_affirmative(a) is False


# ---------- LLM-authored text + parsing (graceful offline fallback) ----------

class TestLlmInteractions:
    @pytest.mark.asyncio
    async def test_draft_summary_falls_back_offline(self) -> None:
        draft = ob.build_draft([{"name": "revenue", "type": "NUMERIC", "key_likeness": 0.05}])
        # stub LLM → deterministic summary (mentions the column count)
        text = await ob.draft_summary("Marriott", draft, LLMRouter(StubProvider()))
        assert "1 columns" in text or "1 measures" in text

    @pytest.mark.asyncio
    async def test_interpret_correction_applies_patch(self) -> None:
        draft = ob.build_draft([
            {"name": "amount", "type": "NUMERIC", "key_likeness": 0.05},
            {"name": "notes", "type": "STRING", "key_likeness": 0.1},
        ])
        canned = '{"amount": {"role": "measure", "is_revenue": true}, "notes": {"role": "ignore"}}'
        patches = await ob.interpret_correction("amount is revenue, drop notes", draft, _router(canned))
        assert patches["amount"].is_revenue is True
        assert patches["notes"].role == "ignore"

    @pytest.mark.asyncio
    async def test_interpret_correction_offline_is_noop(self) -> None:
        draft = ob.build_draft([{"name": "amount", "type": "NUMERIC", "key_likeness": 0.05}])
        patches = await ob.interpret_correction("amount is revenue", draft, LLMRouter(StubProvider()))
        assert patches == {}

    @pytest.mark.asyncio
    async def test_interpret_correction_ignores_unknown_columns(self) -> None:
        draft = ob.build_draft([{"name": "amount", "type": "NUMERIC", "key_likeness": 0.05}])
        canned = '{"ghost": {"role": "ignore"}}'
        patches = await ob.interpret_correction("drop ghost", draft, _router(canned))
        assert patches == {}
