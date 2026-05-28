# @insnav/embed (deferred)

Smaller iframe-only bundle for public share links + customer embedding.
Per PRD Phase 8 — not implemented yet. This folder is a placeholder so the
pnpm workspace `apps/*` glob doesn't break.

When implemented, this app should:
- Render a single ChartSpec (no chat, no pivot panel, no dashboards layout).
- Be < 100KB gzipped (vs apps/web ~ MB).
- Read auth from a one-time share token in the URL, not a full Firebase session.
- Honor the same brand-runtime + locale contract as apps/web.
