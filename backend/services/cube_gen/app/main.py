"""
cube_gen — Cloud Run JOB. Full rebuild of every tenant's Cube model.

Reads ready datasets + column profiles + approved edges from Firestore,
generates Cube .js schemas, and writes them to the GCS Cube model directory
that the deployed Cube container reads (infra/cube/cube.js repositoryFactory).

The api_gateway also syncs incrementally (on edge approve), so this job is
mostly a belt-and-suspenders full refresh — run it on a schedule, or manually
after a bulk change. Same backend image; just a different entrypoint:

    python -m services.cube_gen.app.main
"""
from __future__ import annotations


def main() -> int:
    # Import lazily so the module is importable without the whole app graph.
    from services.api_gateway.app.cube_sync_service import sync_all_tenants

    results = sync_all_tenants()
    print(f"[cube_gen] synced {len(results)} tenant(s)")
    for tenant, r in results.items():
        version = str(r.get("version", ""))[:12]
        print(f"[cube_gen]   {tenant}: {r.get('file_count', 0)} cube(s), version {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
