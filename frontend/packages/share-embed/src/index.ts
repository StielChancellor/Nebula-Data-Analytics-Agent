/**
 * @insnav/share-embed
 *
 * Public share-link viewer + customer embedding SDK consumer.
 * Pairs with apps/embed (the smaller iframe-only bundle).
 *
 * SECURITY (PRD critique): share-link permissions MUST intersect with Cube's
 * securityContext + BQ row-level policies. A shared dashboard joining N
 * datasets via the graph must NOT leak rows the share recipient shouldn't see.
 *
 * TODO Phase 8.
 */

export const SHARE_EMBED_VERSION = "0.1.0";
