"""Cohort builder tests — pure set-algebra core + the router (offline)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.api_gateway.app import datasets as ds_mod
from services.api_gateway.app.cohort_algebra import (
    CohortSyntaxError,
    NonInvertibleFilter,
    UnknownSegment,
    collect_members,
    compile_expression,
    negate,
    parse_expression,
)
from services.api_gateway.app.main import app


# ---------- pure set algebra ----------

_SF = {
    "A": [{"member": "c.city", "operator": "equals", "values": ["X"]}],
    "B": [{"member": "c.rev", "operator": "gt", "values": ["100"]}],
    "C": [{"member": "c.city", "operator": "equals", "values": ["Y"]}],
}


class TestCohortAlgebra:
    def test_intersection_compiles_to_and(self) -> None:
        tree, members = compile_expression("A & B", _SF)
        assert tree == {"and": [_SF["A"][0], _SF["B"][0]]}
        assert members == {"c.city", "c.rev"}

    def test_union_compiles_to_or(self) -> None:
        tree, _ = compile_expression("A | C", _SF)
        assert "or" in tree

    def test_difference_uses_de_morgan_negation(self) -> None:
        tree, _ = compile_expression("A - C", _SF)
        # A AND NOT C ; NOT (city=Y) → city notEquals Y
        assert tree["and"][1] == {"member": "c.city", "operator": "notEquals", "values": ["Y"]}

    def test_precedence_and_binds_tighter_than_or(self) -> None:
        # A | B & C  ==  A | (B & C)
        tree, _ = compile_expression("A | B & C", _SF)
        assert "or" in tree and "and" in tree["or"][1]

    def test_parentheses_override_precedence(self) -> None:
        tree, _ = compile_expression("(A | B) & C", _SF)
        assert "and" in tree and "or" in tree["and"][0]

    def test_negate_and_group_becomes_or(self) -> None:
        grp = {"and": [{"member": "m1", "operator": "equals", "values": ["1"]},
                       {"member": "m2", "operator": "set", "values": []}]}
        neg = negate(grp)
        assert "or" in neg
        assert neg["or"][0]["operator"] == "notEquals"
        assert neg["or"][1]["operator"] == "notSet"

    def test_non_invertible_operator_raises(self) -> None:
        with pytest.raises(NonInvertibleFilter):
            negate({"member": "m", "operator": "measureFilter", "values": []})

    def test_unknown_segment_raises(self) -> None:
        with pytest.raises(UnknownSegment):
            compile_expression("A & Z", _SF)

    def test_syntax_error_raises(self) -> None:
        with pytest.raises(CohortSyntaxError):
            compile_expression("A & & B", _SF)

    def test_collect_members_walks_tree(self) -> None:
        tree, _ = compile_expression("(A & B) - C", _SF)
        assert collect_members(tree) == {"c.city", "c.rev"}

    def test_parse_roundtrip_names(self) -> None:
        ast = parse_expression('"High value" & B')
        assert ast[0] == "and"


# ---------- router ----------

@pytest.fixture
def client(auth_env) -> TestClient:
    return TestClient(app)


def _auth(client: TestClient) -> dict[str, str]:
    r = client.post("/v1/auth/login",
                    json={"email": "admin@insnav.local", "password": "TESTING-do-not-use-in-prod-123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _seed(client: TestClient, h: dict[str, str]) -> tuple[str, str]:
    """Returns (project_id, cube_name)."""
    pid = client.post("/v1/projects", headers=h, json={"name": "Cohorts"}).json()["id"]
    ds_mod.save_dataset(ds_mod.Dataset(
        id="cods", tenant_id="default", project_id=pid, brand="nebula",
        label="sales", source_filename="s.csv", source_size_bytes=10,
        gcs_blob_path="gs://b/s.csv", status="ready", bq_table="p.raw.raw_cods",
        row_count=2, column_count=2,
    ))
    ds_mod.save_column_profiles("cods", [
        ds_mod.ColumnProfile(name="city", type="STRING", row_count=2, null_count=0,
                             null_pct=0.0, distinct_count=2, min_value=None, max_value=None, key_likeness=0.2),
        ds_mod.ColumnProfile(name="revenue", type="NUMERIC", row_count=2, null_count=0,
                             null_pct=0.0, distinct_count=2, min_value=None, max_value=None, key_likeness=0.05),
    ])
    dim = next(
        d["name"]
        for d in client.get(f"/v1/pivot/fields?project_id={pid}", headers=h).json()["dimensions"]
        if d["name"].endswith(".city")
    )
    return pid, dim.rsplit(".", 1)[0]


class TestCohortRouter:
    def test_create_list_delete(self, client: TestClient) -> None:
        h = _auth(client)
        pid, cube = _seed(client, h)
        seg = client.post("/v1/cohorts", headers=h, json={
            "project_id": pid, "name": "Mumbai", "cube": cube,
            "filters": [{"member": f"{cube}.city", "operator": "equals", "values": ["Mumbai"]}],
        }).json()
        assert seg["name"] == "Mumbai"
        listed = client.get(f"/v1/cohorts?project_id={pid}", headers=h).json()
        assert any(s["id"] == seg["id"] for s in listed)
        assert client.delete(f"/v1/cohorts/{seg['id']}", headers=h).status_code == 204

    def test_create_rejects_unknown_member(self, client: TestClient) -> None:
        h = _auth(client)
        pid, cube = _seed(client, h)
        r = client.post("/v1/cohorts", headers=h, json={
            "project_id": pid, "name": "Bad", "cube": cube,
            "filters": [{"member": "ghost.col", "operator": "equals", "values": ["x"]}],
        })
        assert r.status_code == 400

    def test_resolve_intersection_runs(self, client: TestClient) -> None:
        h = _auth(client)
        pid, cube = _seed(client, h)
        for name, city in (("Mumbai", "Mumbai"), ("Big", "Pune")):
            client.post("/v1/cohorts", headers=h, json={
                "project_id": pid, "name": name, "cube": cube,
                "filters": [{"member": f"{cube}.city", "operator": "equals", "values": [city]}],
            })
        measure = next(
            m["name"]
            for m in client.get(f"/v1/pivot/fields?project_id={pid}", headers=h).json()["measures"]
            if m["name"].endswith(".sum_revenue")
        )
        r = client.post("/v1/cohorts/resolve", headers=h, json={
            "project_id": pid, "expression": "Mumbai | Big", "measures": [measure],
            "dimensions": [f"{cube}.city"],
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert "or" in body["filter_tree"]
        assert set(body["segments_used"]) == {"Mumbai", "Big"}

    def test_resolve_unknown_segment_400(self, client: TestClient) -> None:
        h = _auth(client)
        pid, _ = _seed(client, h)
        r = client.post("/v1/cohorts/resolve", headers=h,
                        json={"project_id": pid, "expression": "Ghost", "measures": []})
        assert r.status_code == 400

    def test_resolve_mixed_cubes_refused(self, client: TestClient) -> None:
        h = _auth(client)
        pid, cube = _seed(client, h)
        client.post("/v1/cohorts", headers=h, json={
            "project_id": pid, "name": "Here", "cube": cube,
            "filters": [{"member": f"{cube}.city", "operator": "equals", "values": ["A"]}],
        })
        # A segment claiming a different cube (no member validation needed — empty filters).
        client.post("/v1/cohorts", headers=h, json={
            "project_id": pid, "name": "Elsewhere", "cube": "other_cube", "filters": [],
        })
        r = client.post("/v1/cohorts/resolve", headers=h,
                        json={"project_id": pid, "expression": "Here & Elsewhere", "measures": []})
        assert r.status_code == 400
        assert "per-cube" in r.json()["detail"]

    def test_foreign_project_404(self, client: TestClient) -> None:
        assert client.get("/v1/cohorts?project_id=nope", headers=_auth(client)).status_code == 404
