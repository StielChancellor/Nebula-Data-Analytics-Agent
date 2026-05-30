"""
Seed a Firestore 'smoke' dataset (default tenant) matching the live Cube model
(smoke__smoke) + BigQuery raw.smoke table, so the deployed /v1/chat has a real
catalog to answer against. Run with ADC, NOT offline:

    backend/.venv/Scripts/python.exe infra/scripts/seed_firestore_smoke.py
"""
from services.api_gateway.app.datasets import (
    ColumnProfile,
    Dataset,
    save_column_profiles,
    save_dataset,
)

PROJECT = "insights-navigator-v2"


def main() -> int:
    save_dataset(Dataset(
        id="smoke", tenant_id="default", brand="nebula", label="Smoke",
        source_filename="smoke.csv", source_size_bytes=100,
        gcs_blob_path=f"gs://{PROJECT}-staging/uploads/smoke/smoke.csv",
        bq_table=f"{PROJECT}.raw.smoke", status="ready", row_count=3,
        column_count=2,
    ))
    save_column_profiles("smoke", [
        ColumnProfile(name="city", type="STRING", row_count=3, null_count=0,
                       null_pct=0.0, distinct_count=2, min_value="Mumbai",
                       max_value="Pune", key_likeness=0.2),
        ColumnProfile(name="revenue", type="FLOAT64", row_count=3, null_count=0,
                       null_pct=0.0, distinct_count=3, min_value="50",
                       max_value="100", key_likeness=0.0),
    ])
    print("[seed] Firestore smoke dataset + profiles written (tenant=default)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
