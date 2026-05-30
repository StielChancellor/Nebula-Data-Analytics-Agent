"""
Cube smoke-test seeder (Phase 5b).

Creates a tiny BigQuery table, publishes a matching Cube model to GCS, and
prints a freshly-minted Cube API token. Run against live GCP with ADC:

    CUBE_SECRET=$(gcloud secrets versions access latest --secret=cube-api-secret) \
      backend/.venv/Scripts/python.exe infra/scripts/cube_smoke.py

Then query the deployed Cube service with the printed token. Idempotent —
re-running just recreates the table + republishes the model.
"""
import json
import os

from google.cloud import bigquery

from insnav_cube_client import mint_cube_token, sync_cube_model

PROJECT = os.environ.get("INSNAV_GCP_PROJECT", "insights-navigator-v2")
BUCKET = f"{PROJECT}-staging"


def main() -> int:
    bq = bigquery.Client(project=PROJECT)

    # 1) tiny raw table with data
    bq.create_dataset(bigquery.Dataset(f"{PROJECT}.raw"), exists_ok=True)
    bq.query(
        f"CREATE OR REPLACE TABLE `{PROJECT}.raw.smoke` (city STRING, revenue FLOAT64)"
    ).result()
    bq.query(
        f"INSERT INTO `{PROJECT}.raw.smoke` (city, revenue) "
        f"VALUES ('Mumbai', 100.0), ('Pune', 50.0), ('Mumbai', 25.0)"
    ).result()
    print("[smoke] BQ table raw.smoke created with 3 rows")

    # 2) publish a matching Cube model to GCS (tenant 'default')
    res = sync_cube_model(
        tenant_id="default",
        datasets=[{
            "id": "smoke", "tenant_id": "default", "label": "Smoke",
            "bq_table": f"{PROJECT}.raw.smoke", "locale_hint": "US",
        }],
        columns_by_dataset={"smoke": [
            {"name": "city", "type": "STRING", "key_likeness": 0.2},
            {"name": "revenue", "type": "FLOAT64", "key_likeness": 0.0},
        ]},
        edges=[],
        bucket=BUCKET,
        prefix="cube-model",
        offline=False,
    )
    print("[smoke] published model:", json.dumps(res))

    # 3) mint a token for the smoke test
    secret = os.environ["CUBE_SECRET"]
    token = mint_cube_token(secret=secret, security_context={"tenant_id": "default"})
    print("CUBE_TOKEN=" + token)
    print("CUBE_NAME=" + res["cube_names"][0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
