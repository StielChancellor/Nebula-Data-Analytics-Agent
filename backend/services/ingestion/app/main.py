# NOT DEPLOYED - Phase-0 scaffold only. The real logic runs IN-PROCESS in
# services/api_gateway (swarm/onboarding/ingestion/edge_proposer). This file is
# an extraction boundary for future independent scaling; no Cloud Run resource
# points at it. See backend/README.md.
"""
ingestion — Cloud Run JOB. GCS → BQ raw load + profiler + schema catalog.
Phase 0: stub. Phase 2: real implementation.

Entry point: `python -m services.ingestion.app.main` (no HTTP server; Cloud Run
Jobs invoke containers and let them run to completion).
"""
def main() -> int:
    print("[ingestion] phase-0 stub — no-op")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
