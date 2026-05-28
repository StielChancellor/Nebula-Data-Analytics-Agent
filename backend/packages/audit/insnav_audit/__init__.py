"""
insnav_audit — append-only audit log writer.

Every query (agent or user) writes a row to BQ audit.queries with
(user, tenant, query, snapshot, definition_version, sandbox_job_id, cost_bytes).
PRD § Features lifted from Metabase. TODO Phase 6.
"""
__version__ = "0.1.0"
