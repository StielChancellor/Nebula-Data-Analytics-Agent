"""
insnav_cube_client — Cube schema generation + sync + REST query client.

Phase 5 (generator): approved graph edges + dataset metadata + column
profiles → Cube .js schemas. Every Cube join traces to a confirmed graph
edge (PRD § Hard constraint #2).

Phase 5b (sync + client):
  - sync: write generated schemas to GCS so the deployed Cube container reads
    them via its repositoryFactory (infra/cube/cube.js).
  - client: CubeQueryClient the Semantic agent (Phase 6) uses to run governed
    queries. LLMs select; Cube compiles deterministic SQL (PRD constraint #1).

Phase 11 add: revenue-touching detector gates auto-deploy behind a PR.
"""
from .client import CubeQueryClient, mint_cube_token
from .generator import (
    BQ_TYPE_TO_CUBE_TYPE,
    bq_type_to_cube_type,
    build_cube_schema,
    build_tenant_schemas,
    cube_name_for_dataset,
    render_to_js,
)
from .models import CubeDimension, CubeJoin, CubeMeasure, CubeRelationship, CubeSchema
from .sync import (
    model_version,
    read_offline_model,
    render_model_files,
    reset_offline_model,
    sync_cube_model,
)

__all__ = [
    # models
    "CubeSchema",
    "CubeDimension",
    "CubeMeasure",
    "CubeJoin",
    "CubeRelationship",
    # generator
    "build_cube_schema",
    "build_tenant_schemas",
    "render_to_js",
    "cube_name_for_dataset",
    "bq_type_to_cube_type",
    "BQ_TYPE_TO_CUBE_TYPE",
    # sync
    "sync_cube_model",
    "render_model_files",
    "model_version",
    "read_offline_model",
    "reset_offline_model",
    # client
    "CubeQueryClient",
    "mint_cube_token",
]

__version__ = "0.3.0"
