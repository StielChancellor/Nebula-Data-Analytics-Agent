# Phase 5c status — Cube Store for production

> **UPDATE — NOW LIVE (scale-to-zero).** The earlier `exit(101)` panic was Cube
> Store's GCS driver (it needs a base64 SA key — no Cloud Run ADC). Fix: drop the
> `CUBESTORE_GCS_*` env and let Cube Store use **local ephemeral storage** (it's a
> cache/router, not the source of truth — BigQuery is — so it just rebuilds on
> scale-up). Deployed with `enable_cube_store=true`. Live smoke test in
> **production mode** returned correct data with `"extDbType":"cubestore"`
> (HTTP 200) — confirming the query ran through Cube Store, not dev mode. Public
> but **JWT-enforced** (safe in prod mode), `min_instance_count=0` → **$0 idle**.
> The cost decision below now only applies if you later want always-on (min=1) for
> cold-start-free latency.

---

> Goal: run Cube in **production mode** (JWT enforced, no Playground) instead of
> the dev-mode embedded store. On Cloud Run that means a Cube Store **sidecar**
> in the same service (Cube↔Cube Store uses a non-HTTP protocol, so they can't
> be split across services).
>
> **Outcome: IaC implemented + validated. Live deploy attempted (2×) and hit a
> Cube Store GCS-config panic — reverted to the working dev-mode.** The
> production Cube Store path is one config-fix + a cost decision away.

## What shipped (committed, gated `enable_cube_store=false`)

- `infra/terraform/main.tf` — the Cube service gains, when `enable_cube_store`:
  - a `cubestore` sidecar container (`cubejs/cubestore:latest`) sharing
    localhost, with `CUBESTORE_GCS_BUCKET` / `CUBESTORE_GCS_SUB_PATH`;
  - `CUBEJS_DEV_MODE=false` forced (prod mode), `CUBEJS_CUBESTORE_HOST/PORT`
    pointing at `localhost:3030`;
  - a generous `startup_probe` + `startup_cpu_boost` on the cube container
    (two-container cold start is slow);
  - `max_instance_count = 1` when the store runs (metastore single-instance
    safety).
- Cube SA: `storage.objectViewer` → `storage.objectUser` (Cube Store needs
  write).
- `enable_cube_store` variable with the cost note below. `terraform validate` ✅.

## The two live attempts (diagnosis)

1. **Attempt 1:** Both containers actually booted — Cube Store logged
   `Http Server is listening on 0.0.0.0:3030`, Cube logged
   `Cube API server is listening on 8080` — but the **startup TCP probe on 8080
   fired too early** ("STARTUP TCP probe failed … instance was not started").
   → Added a longer startup probe + CPU boost.
2. **Attempt 2:** Cube Store **panicked**: `Container called exit(101)` in
   `cubestore::config::injection` (Rust). → Its GCS remote-storage config is
   incomplete/invalid with just the bucket env; Cube Store needs more (likely
   `CUBESTORE_GCS_CREDENTIALS` or a different storage config), and panics on the
   partial config rather than falling back.

Both times the platform was reverted to the **working dev-mode + private** Cube
(`Ready=True`), so nothing is broken.

## Why it's parked here (honest)

1. **Config iteration.** Cube Store's GCS setup on Cloud Run needs the exact
   `CUBESTORE_*` env combination nailed down (credentials handling, data dir).
   That's a few more deploy/debug cycles — deferred to keep budget for Phase 6.
2. **Cost guardrail.** A *production* Cube Store really wants
   `min_instance_count = 1` (always-on) so the metastore doesn't cold-start per
   request. An always-on 2-container service (~2 vCPU / 2 GiB) is **~$30–50/mo**,
   which **exceeds the $5/mo hard guardrail and needs your explicit approval.**
   The scale-to-zero variant we attempted is $0 idle but is exactly where the
   cold-start/metastore fragility bites.

## The decision for you

| Option | Cost | Trade-off |
|---|---|---|
| **Keep dev-mode + private** (current) | $0 idle | Works today; not "production-grade" (relaxed JWT, Playground present — mitigated by keeping the service private) |
| **Finish scale-to-zero Cube Store** | $0 idle | Prod mode, but cold-start latency + metastore-on-cold-start fragility; needs the GCS-config fix |
| **Always-on Cube Store** | ~$30–50/mo | Production-correct; **exceeds $5/mo guardrail → needs your OK** |

Until you choose, **dev-mode + private remains the deployed Cube** and the rest
of the platform (incl. Phase 6's agent → Cube queries) works against it.

## Verification

| Check | Result |
|---|---|
| `terraform validate` (sidecar + probe + var) | ✅ |
| Live deploy of Cube Store sidecar | ⚠️ 2 attempts, GCS-config panic — reverted |
| Cube service after revert | ✅ Ready (dev-mode, private) |
| Cost guardrail respected (no always-on deployed) | ✅ |
