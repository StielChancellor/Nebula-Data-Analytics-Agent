# tools/openapi-codegen (deferred)

Pulls `/v1/openapi.json` from the backend on prebuild and emits typed methods
+ models into `packages/api-client/src/generated/`. Plus a SSE event-schema
client from `/v1/events-schema.json`.

Per PRD Phase 6 — implement once the backend exposes a stable OpenAPI doc.
