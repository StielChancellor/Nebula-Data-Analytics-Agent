# infra/cube-schema/

Generated Cube `.js` schema files. **DO NOT hand-edit.** Files here are
emitted by the `services/cube_gen/` Cloud Run job from the approved edges
in the knowledge graph (PRD § L2 → L3 pipeline).

Revenue-touching changes (any cube that exposes `revenue`, `roas`,
`cost_per_cookie`, etc.) require a human PR review — the cube_gen job opens
a PR rather than committing directly for those.

Phase 0: empty. Phase 5 fills this in.
