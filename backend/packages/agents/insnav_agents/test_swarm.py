"""Agent-swarm tests — fake LLM (canned interpretation) + offline Cube client."""
import json

import pytest

from insnav_cube_client import CubeQueryClient, build_cube_schema, cube_name_for_dataset
from insnav_llm_router import LLMRouter
from insnav_llm_router.router import LLMResponse

from insnav_agents import (
    answer_question,
    build_catalog,
    critic_check,
    data_health,
    run_specialist_analysis,
    to_cube_query,
)
from insnav_agents.schemas import Interpretation


# ---------- fixtures ----------

DS_ID = "a3f4d2b1c0d9e8f7a3f4d2b1c0d9e8f7"
CUBE = cube_name_for_dataset(DS_ID, "Sales")  # e.g. sales__a3f4d2b1


def _schema():
    return build_cube_schema(
        dataset={"id": DS_ID, "tenant_id": "t1", "label": "Sales",
                 "bq_table": "p.raw.raw_x", "locale_hint": "US"},
        columns=[
            {"name": "city", "type": "STRING", "key_likeness": 0.2},
            {"name": "revenue", "type": "FLOAT64", "key_likeness": 0.0},
        ],
        edges=[],
    )


def _health(status="ready", rows=1000):
    return [{"id": DS_ID, "label": "Sales", "last_refreshed": "2026-05-30T00:00:00Z",
             "row_count": rows, "status": status}]


class _FakeProvider:
    """Returns a fixed JSON string as the LLM output."""
    name = "stub"
    model = "fake"

    def __init__(self, payload: dict):
        self._text = json.dumps(payload)

    async def generate(self, *, prompt: str, system=None, max_tokens=16384) -> LLMResponse:
        return LLMResponse(text=self._text, model=self.model, provider="stub")


def _router(payload: dict) -> LLMRouter:
    return LLMRouter(_FakeProvider(payload))


def _offline_cube() -> CubeQueryClient:
    return CubeQueryClient(api_url="", api_secret="x" * 32)  # offline → stub rows


def _good_interp() -> dict:
    return {
        "measures": [f"{CUBE}.sum_revenue"],
        "dimensions": [f"{CUBE}.city"],
        "time_dimension": None,
        "filters": [],
        "order": {f"{CUBE}.sum_revenue": "desc"},
        "plain_english": "Total revenue by city.",
        "analysis_level": "descriptive",
        "confidence": 0.9,
    }


# ---------- catalog + critic (pure) ----------

class TestCatalogAndCritic:
    def test_catalog_lists_valid_names(self):
        text, valid = build_catalog([_schema()])
        assert f"{CUBE}.sum_revenue" in valid
        assert f"{CUBE}.city" in valid
        assert "measure" in text and "dimension" in text

    def test_critic_passes_valid_selection(self):
        _, valid = build_catalog([_schema()])
        interp = Interpretation(**_good_interp())
        assert critic_check(interp, valid) == []

    def test_critic_flags_hallucinated_measure(self):
        _, valid = build_catalog([_schema()])
        interp = Interpretation(measures=[f"{CUBE}.profit_margin"], confidence=0.9)
        issues = critic_check(interp, valid)
        assert any("profit_margin" in i for i in issues)

    def test_critic_flags_empty_selection(self):
        _, valid = build_catalog([_schema()])
        assert critic_check(Interpretation(confidence=0.9), valid)


class TestSpecialistAnalysis:
    def test_forecast_routes_to_series(self):
        cols = ["c.m"]
        rows = [[v] for v in (1, 2, 3, 4, 5, 6, 7, 8)]
        out = run_specialist_analysis({"method": "forecast", "value_field": "c.m", "periods": 2}, cols, rows)
        assert out["method_used"] == "holt_linear"
        assert len(out["result"]["predictions"]) == 2

    def test_significance_splits_by_group(self):
        cols = ["c.region", "c.rev"]
        rows = [["A", 10], ["A", 11], ["A", 9], ["A", 10], ["B", 20], ["B", 21], ["B", 19], ["B", 20]]
        out = run_specialist_analysis(
            {"method": "significance", "value_field": "c.rev", "group_field": "c.region",
             "group_a": "A", "group_b": "B"}, cols, rows)
        assert out["result"]["significant"] is True

    def test_correlation_two_fields(self):
        cols = ["c.x", "c.y"]
        rows = [[1, 2], [2, 4], [3, 6], [4, 8], [5, 10]]
        out = run_specialist_analysis({"method": "correlation", "x_field": "c.x", "y_field": "c.y"}, cols, rows)
        assert out["result"]["r"] == pytest.approx(1.0, abs=1e-9)

    def test_missing_field_is_graceful(self):
        out = run_specialist_analysis({"method": "forecast", "value_field": "nope"}, ["c.m"], [[1], [2]])
        assert out["confidence"] == 0.0


class TestToCubeQuery:
    def test_maps_all_parts(self):
        interp = Interpretation(
            measures=["c.m"], dimensions=["c.d"], time_dimension="c.t",
            granularity="month", filters=[{"member": "c.d", "operator": "equals", "values": ["x"]}],
            order={"c.m": "desc"}, limit=10, confidence=0.9,
        )
        q = to_cube_query(interp)
        assert q["measures"] == ["c.m"]
        assert q["timeDimensions"] == [{"dimension": "c.t", "granularity": "month"}]
        assert q["filters"][0]["operator"] == "equals"
        assert q["order"] == {"c.m": "desc"} and q["limit"] == 10


class TestDataHealth:
    def test_ok_when_ready(self):
        assert data_health(_health()).status == "ok"

    def test_warn_when_not_ready(self):
        assert data_health(_health(status="loading")).status == "warn"

    def test_warn_when_zero_rows(self):
        b = data_health(_health(rows=0))
        assert b.status == "warn"
        assert any("0 rows" in w for w in b.warnings)


# ---------- orchestrator (end-to-end, offline) ----------

class TestAnswerQuestion:
    @pytest.mark.asyncio
    async def test_happy_path(self):
        ans = await answer_question(
            "revenue by city", tenant_id="t1",
            schemas=[_schema()], dataset_health=_health(),
            router=_router(_good_interp()), cube_client=_offline_cube(),
        )
        assert ans.kind == "answer"
        assert ans.interpretation_echo == "Total revenue by city."
        assert ans.cube_query["measures"] == [f"{CUBE}.sum_revenue"]
        assert ans.data_health.status == "ok"
        assert len(ans.rows) == 2  # offline stub returns 2 rows
        assert ans.inputs_hash  # provenance present

    @pytest.mark.asyncio
    async def test_hallucinated_measure_clarifies(self):
        bad = _good_interp()
        bad["measures"] = [f"{CUBE}.profit_margin"]  # not in catalog
        ans = await answer_question(
            "what's the margin", tenant_id="t1",
            schemas=[_schema()], dataset_health=_health(),
            router=_router(bad), cube_client=_offline_cube(),
        )
        assert ans.kind == "clarify"
        assert any("profit_margin" in c for c in ans.caveats)

    @pytest.mark.asyncio
    async def test_low_confidence_clarifies(self):
        low = _good_interp()
        low["confidence"] = 0.1
        ans = await answer_question(
            "huh", tenant_id="t1", schemas=[_schema()], dataset_health=_health(),
            router=_router(low), cube_client=_offline_cube(),
        )
        assert ans.kind == "clarify"

    @pytest.mark.asyncio
    async def test_no_schemas_refuses(self):
        ans = await answer_question(
            "anything", tenant_id="t1", schemas=[], dataset_health=[],
            router=_router(_good_interp()), cube_client=_offline_cube(),
        )
        assert ans.kind == "refuse"

    @pytest.mark.asyncio
    async def test_deterministic_inputs_hash(self):
        kw = dict(tenant_id="t1", schemas=[_schema()], dataset_health=_health(),
                  cube_client=_offline_cube())
        a = await answer_question("revenue by city", router=_router(_good_interp()), **kw)
        b = await answer_question("revenue by city", router=_router(_good_interp()), **kw)
        assert a.inputs_hash == b.inputs_hash

    @pytest.mark.asyncio
    async def test_forecast_analysis_attached(self):
        # A cube client returning a clean upward series; analysis=forecast.
        class _SeriesCube:
            def load(self, query, *, tenant_id):
                rows = [{f"{CUBE}.sum_revenue": v} for v in (1, 2, 3, 4, 5, 6, 7, 8)]
                return {"data": rows, "_stub": False}

        interp = _good_interp()
        interp["analysis"] = {"method": "forecast", "value_field": f"{CUBE}.sum_revenue", "periods": 3}
        interp["dimensions"] = []  # series of the measure only
        ans = await answer_question(
            "forecast revenue", tenant_id="t1", schemas=[_schema()], dataset_health=_health(),
            router=_router(interp), cube_client=_SeriesCube(),
        )
        assert ans.kind == "answer"
        assert ans.analysis is not None
        assert ans.analysis["method_used"] == "holt_linear"
        assert len(ans.analysis["result"]["predictions"]) == 3

    @pytest.mark.asyncio
    async def test_unparseable_llm_output_clarifies(self):
        class _Garbage:
            name = "stub"; model = "g"
            async def generate(self, *, prompt, system=None, max_tokens=16384):
                return LLMResponse(text="sorry, I can't do that", model="g", provider="stub")
        ans = await answer_question(
            "revenue by city", tenant_id="t1", schemas=[_schema()], dataset_health=_health(),
            router=LLMRouter(_Garbage()), cube_client=_offline_cube(),
        )
        assert ans.kind == "clarify"
