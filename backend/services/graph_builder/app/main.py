# NOT DEPLOYED - Phase-0 scaffold only. The real logic runs IN-PROCESS in
# services/api_gateway (swarm/onboarding/ingestion/edge_proposer). This file is
# an extraction boundary for future independent scaling; no Cloud Run resource
# points at it. See backend/README.md.
"""
graph_builder — Cloud Run JOB. Embedding-based edge proposals + key-overlap
scoring; writes proposals for admin review. Phase 0: stub. Phase 4: real.
"""
def main() -> int:
    print("[graph_builder] phase-0 stub — no-op")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
