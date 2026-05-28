# tools/brand-build (deferred)

Orchestrates `vite build --mode <brand>` across all configured brands and
wires Firebase Hosting multi-target deploy (`.firebaserc`).

Per PRD Phase 13 — implement when a second brand actually ships. Until
then, `pnpm build --mode <brand>` from `apps/web` is enough.

## Future shape

```bash
node tools/brand-build/index.js --brand nebula --deploy
# builds apps/web with --mode nebula
# runs firebase deploy --only hosting:nebula
```
