"""
Cube schema models.

Map to https://cube.dev/docs/reference/data-model. We emit JS files (not
YAML) because the PRD specifies .js — JS is more powerful and matches what
existing Cube users tend to maintain by hand.

CRITICAL (PRD § Hard constraint #2): every CubeJoin in a CubeSchema MUST
trace to an approved GraphEdge from insnav_graph_store. The generator
enforces this — there is no path in the code that constructs a CubeJoin
from anything other than an approved edge.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Cube's relationship vocabulary (1.x). Older Cube called these
# "belongsTo / hasMany / hasOne"; modern syntax uses _to_ form.
CubeRelationship = Literal["one_to_one", "one_to_many", "many_to_one", "many_to_many"]

# Cube column types. We're a strict subset — Cube supports more (e.g. "geo")
# but our profiler doesn't surface them yet.
CubeColumnType = Literal["string", "number", "time", "boolean"]

# Cube measure types we emit.
CubeMeasureType = Literal["count", "sum", "avg", "min", "max", "count_distinct"]


class CubeDimension(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str                                 # identifier
    sql: str                                  # SQL expression in the source table
    type: CubeColumnType
    primary_key: bool = False                 # if true, used by Cube for join targets
    title: str | None = None                  # human label
    description: str | None = None


class CubeMeasure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: CubeMeasureType
    sql: str | None = None                    # required for sum/avg/min/max/etc; null for count
    title: str | None = None
    description: str | None = None
    # Soft flag: revenue/roas/cost names → require PR review (PRD §11).
    # Phase 5 v1 just sets it; Phase 11 adds the gating.
    revenue_touching: bool = False


class CubeJoin(BaseModel):
    """Always backed by an approved GraphEdge (PRD § Hard constraint #2)."""

    model_config = ConfigDict(extra="forbid")

    to_cube: str                              # other cube's name
    sql_clause: str                           # e.g. ${CUBE}.gclid = ${ga4_sessions}.gclid
    relationship: CubeRelationship = "many_to_many"
    # Provenance — points back to the graph edge so we can audit "what
    # confirmation makes this join exist?"
    from_edge_id: str
    from_dataset_id: str
    to_dataset_id: str


class CubeSchema(BaseModel):
    """One cube = one dataset in our world."""

    model_config = ConfigDict(extra="forbid")

    name: str                                 # cube identifier (also the JS variable)
    title: str                                # human label shown in UI
    sql_table: str                            # `project.dataset.table` fqn
    description: str
    dimensions: list[CubeDimension] = Field(default_factory=list)
    measures: list[CubeMeasure] = Field(default_factory=list)
    joins: list[CubeJoin] = Field(default_factory=list)
    # Metadata
    dataset_id: str                           # source dataset
    tenant_id: str
    generated_at: str = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat()
    )
    locale_hint: Literal["US", "IN"] = "US"   # surfaces region-aware behavior

    def revenue_touching(self) -> bool:
        return any(m.revenue_touching for m in self.measures)
