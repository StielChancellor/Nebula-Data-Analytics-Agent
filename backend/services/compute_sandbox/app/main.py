# NOT DEPLOYED - Phase-0 scaffold only. The real logic runs IN-PROCESS in
# services/api_gateway (swarm/onboarding/ingestion/edge_proposer). This file is
# an extraction boundary for future independent scaling; no Cloud Run resource
# points at it. See backend/README.md.
"""
compute_sandbox — Cloud Run JOB invoked PER INVOCATION (not a long-running
service). Pinned image (numpy/pandas/scipy/statsmodels/prophet/lifelines/pymc),
60s timeout, no network egress except BQ via service account, results to
GCS scratch bucket.

PRD D9. Phase 0: stub. Phase 9: real.
"""
def main() -> int:
    print("[compute_sandbox] phase-0 stub — no-op")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
