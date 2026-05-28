"""
insnav_cube_client — Cube schema generation + (eventual) Cube REST/SQL client.

Phase 5 (this turn): the GENERATOR half. Takes approved graph edges +
dataset metadata + column profiles → produces Cube .js schemas. Every Cube
join traces to a confirmed graph edge (PRD § Hard constraint #2).

Phase 5b (future): the CLIENT half. Once Cube is deployed (Cloud Run with
the generated schemas), this package will also include the REST/SQL client
the Semantic agent uses to run queries.

Phase 11 add: revenue-touching detector that gates auto-deploy behind a PR.
"""
from .generator import (
    BQ_TYPE_TO_CUBE_TYPE,
    bq_type_to_cube_type,
    build_cube_schema,
    cube_name_for_dataset,
    render_to_js,
)
from .models import CubeDimension, CubeJoin, CubeMeasure, CubeRelationship, CubeSchema

__all__ = [
    "CubeSchema",
    "CubeDimension",
    "CubeMeasure",
    "CubeJoin",
    "CubeRelationship",
    "build_cube_schema",
    "render_to_js",
    "cube_name_for_dataset",
    "bq_type_to_cube_type",
    "BQ_TYPE_TO_CUBE_TYPE",
]

__version__ = "0.2.0"
