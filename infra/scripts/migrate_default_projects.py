"""
One-time migration (Phase 10): wrap pre-projects datasets into a per-tenant
"Default" project and re-sync their Cube model under the per-project GCS path.

Existing datasets predate the project workspace concept (project_id is None).
This assigns each to a Default project so nothing is orphaned and the per-project
Cube path (cube-model/<tenant>/<project>/) is populated.

Run live (NOT offline) from the repo root with the backend venv:
    INSNAV_GCP_PROJECT=insights-navigator-v2 \
    ./backend/.venv/Scripts/python.exe infra/scripts/migrate_default_projects.py

Idempotent: re-running reuses the existing Default project and only touches
datasets that still have no project.
"""
from __future__ import annotations

import os
import sys

# Make the backend packages importable when run from the repo root.
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.normpath(os.path.join(_HERE, "..", "..", "backend"))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("INSNAV_GCP_PROJECT", "insights-navigator-v2")
os.environ["INSNAV_OFFLINE"] = "false"  # must hit real Firestore/GCS/BQ


def main() -> None:
    from services.api_gateway.app.cube_sync_service import sync_project
    from services.api_gateway.app.datasets import (
        list_all_ready_datasets,
        save_dataset,
    )
    from services.api_gateway.app.projects import (
        Project,
        add_dataset_to_project,
        list_projects_for_tenant,
        new_project_id,
        save_project,
    )

    ready = list_all_ready_datasets()
    by_tenant: dict[str, list] = {}
    for d in ready:
        if d.project_id is None:
            by_tenant.setdefault(d.tenant_id, []).append(d)

    if not by_tenant:
        print("Nothing to migrate — every ready dataset already has a project.")
        return

    for tenant, datasets in by_tenant.items():
        existing = [p for p in list_projects_for_tenant(tenant) if p.name == "Default"]
        if existing:
            proj = existing[0]
            print(f"[{tenant}] reusing Default project {proj.id}")
        else:
            proj = Project(
                id=new_project_id(),
                tenant_id=tenant,
                brand=datasets[0].brand,
                name="Default",
                description="Auto-created during the Phase 10 project-workspaces migration.",
                owner_email=os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "admin@insnav.local"),
                status="active",
            )
            save_project(proj)
            print(f"[{tenant}] created Default project {proj.id}")

        for d in datasets:
            d.project_id = proj.id
            save_dataset(d)
            add_dataset_to_project(proj.id, d.id)
            print(f"   ↳ {d.id} ({d.label}) → project {proj.id}")

        result = sync_project(tenant, proj.id)
        print(f"[{tenant}] cube re-synced: {result['file_count']} file(s), version {result['version'][:12]}")


if __name__ == "__main__":
    main()
