/**
 * Cube configuration for Insights Navigator V2.0 (Phase 5b).
 *
 * The data model is NOT baked into this image. Instead it lives in GCS, written
 * by the backend's cube-model sync (insnav_cube_client.sync). This config reads
 * the model for the requesting tenant at compile time via `repositoryFactory`,
 * so approving a new edge → backend re-sync → Cube recompiles on its next query
 * without a redeploy.
 *
 * Multi-tenancy:
 *   - The backend mints a Cube API JWT whose payload is the securityContext,
 *     carrying `tenant_id`.
 *   - `contextToAppId` namespaces the compiled model per tenant, so tenant A
 *     can never see tenant B's cubes.
 *   - `schemaVersion` reads the per-tenant `__version__` marker so Cube knows
 *     when to recompile.
 *
 * GCS layout (written by the backend):
 *   gs://<INSNAV_CUBE_MODEL_BUCKET>/<INSNAV_CUBE_MODEL_PREFIX>/<tenant>/<cube>.js
 *   gs://<INSNAV_CUBE_MODEL_BUCKET>/<INSNAV_CUBE_MODEL_PREFIX>/<tenant>/__version__
 *
 * Auth/credentials: on Cloud Run, @google-cloud/storage and the BigQuery driver
 * both pick up the runtime service account via ADC — no key files.
 *
 * Required env:
 *   CUBEJS_DB_TYPE=bigquery
 *   CUBEJS_DB_BQ_PROJECT_ID=<gcp project>
 *   CUBEJS_API_SECRET=<shared secret, matches backend INSNAV_CUBE_API_SECRET>
 *   INSNAV_CUBE_MODEL_BUCKET=<gcs bucket>
 *   INSNAV_CUBE_MODEL_PREFIX=cube-model
 */
const { Storage } = require('@google-cloud/storage');

const storage = new Storage();
const BUCKET = process.env.INSNAV_CUBE_MODEL_BUCKET;
const PREFIX = process.env.INSNAV_CUBE_MODEL_PREFIX || 'cube-model';

function tenantOf(securityContext) {
  return (securityContext && securityContext.tenant_id) || 'default';
}

function modelPath(tenant) {
  return `${PREFIX}/${tenant}`;
}

async function readVersion(tenant) {
  if (!BUCKET) return 'no-bucket';
  try {
    const [buf] = await storage.bucket(BUCKET).file(`${modelPath(tenant)}/__version__`).download();
    return buf.toString('utf8').trim() || 'empty';
  } catch (e) {
    // No model published yet for this tenant — stable sentinel so Cube
    // compiles an empty model rather than throwing.
    return 'empty';
  }
}

async function readSchemaFiles(tenant) {
  if (!BUCKET) return [];
  try {
    const [files] = await storage.bucket(BUCKET).getFiles({ prefix: `${modelPath(tenant)}/` });
    const out = [];
    for (const f of files) {
      if (!f.name.endsWith('.js')) continue; // skip __version__ marker
      const [buf] = await f.download();
      out.push({ fileName: f.name.split('/').pop(), content: buf.toString('utf8') });
    }
    return out;
  } catch (e) {
    console.error(`[insnav-cube] failed to read model for tenant=${tenant}:`, e.message);
    return [];
  }
}

module.exports = {
  // Compile a separate model per tenant.
  contextToAppId: ({ securityContext }) => `INSNAV_${tenantOf(securityContext)}`,

  // Recompile when the tenant's published model version changes.
  schemaVersion: ({ securityContext }) => readVersion(tenantOf(securityContext)),

  // Load the tenant's model files from GCS at compile time.
  repositoryFactory: ({ securityContext }) => ({
    dataSchemaFiles: async () => readSchemaFiles(tenantOf(securityContext)),
  }),

  // Defense in depth: even though models are namespaced per tenant, refuse to
  // run a query without a tenant in the security context.
  queryRewrite: (query, { securityContext }) => {
    if (!securityContext || !securityContext.tenant_id) {
      throw new Error('Missing tenant_id in security context');
    }
    return query;
  },
};
