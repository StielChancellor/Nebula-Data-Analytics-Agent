"""Cube model sync tests (offline mode — no GCS)."""
import pytest

from insnav_cube_client import (
    model_version,
    read_offline_model,
    render_model_files,
    reset_offline_model,
    sync_cube_model,
)
from insnav_cube_client.generator import build_tenant_schemas


@pytest.fixture(autouse=True)
def _clean():
    reset_offline_model()
    yield
    reset_offline_model()


def _ds(id_: str, label: str) -> dict:
    return {
        "id": id_,
        "tenant_id": "t1",
        "label": label,
        "bq_table": f"proj.raw.raw_{id_}",
        "locale_hint": "US",
    }


def _cols(*names_types_kl: tuple[str, str, float]) -> list[dict]:
    return [
        {"name": n, "type": t, "key_likeness": kl, "distinct_count": 900 if kl > 0.5 else 5}
        for n, t, kl in names_types_kl
    ]


class TestModelVersion:
    def test_deterministic_for_same_content(self) -> None:
        files = {"a.js": "cube(`a`)", "b.js": "cube(`b`)"}
        assert model_version(files) == model_version(dict(files))

    def test_changes_when_content_changes(self) -> None:
        v1 = model_version({"a.js": "cube(`a`)"})
        v2 = model_version({"a.js": "cube(`a2`)"})
        assert v1 != v2

    def test_order_independent(self) -> None:
        v1 = model_version({"a.js": "x", "b.js": "y"})
        v2 = model_version({"b.js": "y", "a.js": "x"})
        assert v1 == v2


class TestRenderModelFiles:
    def test_one_file_per_schema_named_by_cube(self) -> None:
        schemas = build_tenant_schemas(
            datasets=[_ds("a" * 32, "Sales")],
            columns_by_dataset={"a" * 32: _cols(("revenue", "FLOAT64", 0.0))},
            edges=[],
        )
        files = render_model_files(schemas)
        assert len(files) == 1
        name = next(iter(files))
        assert name.startswith("sales__") and name.endswith(".js")
        assert "cube(`sales__" in files[name]


class TestSyncOffline:
    def test_writes_model_to_offline_store(self) -> None:
        ds_id = "a" * 32
        result = sync_cube_model(
            tenant_id="t1",
            datasets=[_ds(ds_id, "Sales")],
            columns_by_dataset={ds_id: _cols(("city", "STRING", 0.1), ("revenue", "FLOAT64", 0.0))},
            edges=[],
            bucket="unused-offline",
            offline=True,
        )
        assert result["file_count"] == 1
        assert result["cube_names"][0].startswith("sales__")
        assert len(result["version"]) == 64  # sha256 hex

        model = read_offline_model("t1")
        assert model["version"] == result["version"]
        assert len(model["files"]) == 1

    def test_resync_with_same_inputs_is_stable(self) -> None:
        ds_id = "a" * 32
        kw = dict(
            tenant_id="t1",
            datasets=[_ds(ds_id, "Sales")],
            columns_by_dataset={ds_id: _cols(("revenue", "FLOAT64", 0.0))},
            edges=[],
            bucket="unused",
            offline=True,
        )
        r1 = sync_cube_model(**kw)
        r2 = sync_cube_model(**kw)
        assert r1["version"] == r2["version"]

    def test_approved_edge_changes_version(self) -> None:
        a, b = "a" * 32, "b" * 32
        datasets = [_ds(a, "Ads"), _ds(b, "GA")]
        cols = {a: _cols(("gclid", "STRING", 0.95)), b: _cols(("gclid", "STRING", 0.95))}

        without = sync_cube_model(
            tenant_id="t1", datasets=datasets, columns_by_dataset=cols, edges=[],
            bucket="x", offline=True,
        )
        with_edge = sync_cube_model(
            tenant_id="t1", datasets=datasets, columns_by_dataset=cols,
            edges=[{
                "id": "e1", "from_dataset": a, "from_column": "gclid",
                "to_dataset": b, "to_column": "gclid",
                "from_distinct_count": 900, "to_distinct_count": 900,
            }],
            bucket="x", offline=True,
        )
        # Adding a join changes the rendered JS → new version.
        assert without["version"] != with_edge["version"]
        assert with_edge["file_count"] == 2
