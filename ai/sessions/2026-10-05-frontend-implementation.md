# Frontend implementation — steps 1 to 10

## Objective

Implement the Trinity web frontend from the approved [design](../../sdd/frontend/design.md) and [tasks](../../sdd/frontend/tasks.md). Connect it to the existing API through the Vite `/api` proxy. Add the backend parts that steps 7–9 need. Commit each slice.

## Human and AI contributions

[ME] Alayala requested the implementation on October 5, 2026. He approved the proposed package versions, Node.js 24.21.0 and TypeScript 6.0.3, and asked for one or more commits per slice. The interface design inputs keep their attribution under [A25](../../DECISIONS.md#a25--figma-design-and-brand-handoff); the [handoff package](../../docs/design-reference/2026-10-04-explorer-handoff/PROVENANCE.md) author remains pending.

[YOU] Claude writes the code, tests and evidence notes recorded below. Claude's adaptation of the design is AI work. It is separate from alayala's Figma design and the ChatGPT brand reference.

## Decision references

- [A26](../../DECISIONS.md#a26--frontend-stack): React, TypeScript, Vite.
- Spec D01–D04 (accepted): `sessionStorage` token, existing rows only, reported facilities only, contract copy.
- A17: exact versions and a committed lockfile.

## Slices

Each slice records what changed, which checks ran and their results.
