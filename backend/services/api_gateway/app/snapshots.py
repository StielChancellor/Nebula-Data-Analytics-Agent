"""
Result snapshots + diff (Phase 11 #3) and assumption checks (Phase 11 #5).

Snapshot: a captured (columns, rows) for a governed query spec at a point in
time. Diffing two snapshots of the SAME spec answers "what changed in metric X
between yesterday and today" deterministically — rows aligned by dimension key,
per-measure deltas computed in code (no LLM).

Assumption checks: re-evaluate a tile's statistical assumptions on demand (small
sample, recent anomaly / seasonality break). On-demand, not a nightly cron, so
it stays $0 — the UI calls it when a dashboard is viewed and badges the tile.

Firestore layout: /snapshots/{id}. Mirrors dashboards.py (dual offline backend).
"""
from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _num(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(default_factory=lambda: uuid4().hex)
    tenant_id: str
    project_id: str
    label: str = ""
    spec: dict[str, Any] = Field(default_factory=dict)   # the TileSpec used
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    captured_at: str = Field(default_factory=_now)


# ---------- pure: diff ----------

def diff_snapshots(
    spec: dict[str, Any],
    a_cols: list[str], a_rows: list[list[Any]],
    b_cols: list[str], b_rows: list[list[Any]],
) -> dict[str, Any]:
    """Align rows by dimension key, compute per-measure deltas. Pure/testable."""
    dims = list(spec.get("dimensions") or [])
    if spec.get("time_dimension"):
        dims.append(spec["time_dimension"])
    measures = list(spec.get("measures") or [])

    def index_rows(cols: list[str], rows: list[list[Any]]) -> dict[tuple, dict[str, float | None]]:
        di = [cols.index(d) for d in dims if d in cols]
        mi = {m: cols.index(m) for m in measures if m in cols}
        out: dict[tuple, dict[str, float | None]] = {}
        for r in rows:
            key = tuple(str(r[i]) for i in di)
            out[key] = {m: _num(r[idx]) for m, idx in mi.items()}
        return out

    A = index_rows(a_cols, a_rows)
    B = index_rows(b_cols, b_rows)
    added = [k for k in B if k not in A]
    removed = [k for k in A if k not in B]
    changed: list[dict[str, Any]] = []
    for k in A:
        if k not in B:
            continue
        deltas: dict[str, Any] = {}
        for m in measures:
            av, bv = A[k].get(m), B[k].get(m)
            if av is None and bv is None:
                continue
            a0, b0 = av or 0.0, bv or 0.0
            if a0 != b0:
                deltas[m] = {
                    "from": a0, "to": b0, "delta": b0 - a0,
                    "pct": ((b0 - a0) / a0 * 100.0) if a0 else None,
                }
        if deltas:
            changed.append({"key": list(k), "deltas": deltas})

    return {
        "dimensions": dims, "measures": measures,
        "added": [list(k) for k in added], "removed": [list(k) for k in removed],
        "changed": changed,
        "summary": {"added": len(added), "removed": len(removed), "changed": len(changed)},
    }


# ---------- pure: assumption checks ----------

def evaluate_assumptions(spec: dict[str, Any], columns: list[str], rows: list[list[Any]]) -> list[dict[str, str]]:
    """Deterministic assumption re-check for a tile. Returns warning badges."""
    warnings: list[dict[str, str]] = []
    n = len(rows)
    if n == 0:
        return [{"level": "warn", "code": "empty",
                 "message": "No rows returned — tile may be broken or over-filtered."}]
    if n < 30:
        warnings.append({"level": "info", "code": "small_sample",
                         "message": f"Small sample (n={n}); treat trends and tests cautiously."})

    measures = spec.get("measures") or []
    td = spec.get("time_dimension")
    if td and len(measures) == 1 and n >= 5 and td in columns and measures[0] in columns:
        mi = columns.index(measures[0])
        vals = [_num(r[mi]) for r in rows]
        clean = [v for v in vals if v is not None]
        if len(clean) >= 3:
            from insnav_agents import stats

            res = stats.detect_anomalies(clean).get("result", {})
            anoms = res.get("anomalies", [])
            last_idx = len(clean) - 1
            if any(a.get("index") == last_idx for a in anoms):
                warnings.append({"level": "warn", "code": "recent_anomaly",
                                 "message": "The most recent point is a statistical anomaly vs its "
                                            "history — possible seasonality break or data issue."})
            elif anoms:
                warnings.append({"level": "info", "code": "anomaly",
                                 "message": f"{len(anoms)} anomalous point(s) detected in the series."})
    return warnings


# ---------- storage ----------

_OFFLINE: dict[str, dict[str, Any]] = {}


def reset_offline_store() -> None:
    _OFFLINE.clear()


def _offline() -> bool:
    from services.api_gateway.app.settings import get_settings

    return get_settings().offline_mode


def _col() -> str:
    from services.api_gateway.app.settings import get_settings

    return get_settings().fs_snapshots_collection


def save_snapshot(s: Snapshot) -> None:
    payload = s.model_dump()
    if _offline():
        _OFFLINE[s.id] = payload
        return
    from services.api_gateway.app.gcp_clients import firestore_client

    firestore_client().collection(_col()).document(s.id).set(payload)


def get_snapshot(snapshot_id: str) -> Snapshot | None:
    if _offline():
        data = _OFFLINE.get(snapshot_id)
        return Snapshot(**data) if data else None
    from services.api_gateway.app.gcp_clients import firestore_client

    doc = firestore_client().collection(_col()).document(snapshot_id).get()
    return Snapshot(**doc.to_dict()) if doc.exists else None


def list_snapshots_for_project(tenant_id: str, project_id: str) -> list[Snapshot]:
    if _offline():
        return [
            Snapshot(**d)
            for d in _OFFLINE.values()
            if d.get("tenant_id") == tenant_id and d.get("project_id") == project_id
        ]
    from google.cloud.firestore_v1.base_query import FieldFilter

    from services.api_gateway.app.gcp_clients import firestore_client

    docs = (
        firestore_client()
        .collection(_col())
        .where(filter=FieldFilter("tenant_id", "==", tenant_id))
        .where(filter=FieldFilter("project_id", "==", project_id))
        .stream()
    )
    return [Snapshot(**(d.to_dict() or {})) for d in docs if d.to_dict()]


def delete_snapshot_record(snapshot_id: str) -> None:
    if _offline():
        _OFFLINE.pop(snapshot_id, None)
        return
    from services.api_gateway.app.gcp_clients import firestore_client

    firestore_client().collection(_col()).document(snapshot_id).delete()
