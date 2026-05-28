"""
insnav_cube_client — Cube REST/SQL client + securityContext builder
+ canonical-query hashing for the determinism cache.

PRD § Hard constraint #2: every Cube join MUST trace to a human-confirmed
graph edge. This client refuses queries whose joins aren't backed by edges
in insnav_graph_store.

TODO Phase 5.
"""

__version__ = "0.1.0"
