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

### Steps 1–2 — toolchain and foundations

[YOU] Verified all 22 approved package versions and their peer ranges with `npm view`. Downloaded the official Node.js 24.21.0 macOS arm64 build into a temporary folder and checked its SHA-256 against nodejs.org `SHASUMS256.txt`; local Node stays v26.3.0. Created `frontend/` with exact versions, `.nvmrc`, `engines`, `package-lock.json`, strict TypeScript 6.0.3, the `/api` proxy and ESLint with the exact-number ban. Added tokens, base styles, brand images, exact decimal/date/ID helpers, hand-written contract types, the API client, error messages and base components.

Choices within the design:
- No `@types/node`: Vite's `loadEnv` reads `TRINITY_API_TARGET`, and the OpenAPI enum test imports the contract with Vite's `?raw` suffix. Test mode alone may read `../docs`.
- The ban covers `Number(…)`, `new Number`, `parseFloat`, `Number.parseFloat` and unary `+` in `src/`; `src/lib/**/*.test.ts` is the only exemption. `no-console` is an error in `src/`.
- Rounding is half up, away from zero, to match Python `ROUND_HALF_UP`.
- Error screens show the message for the API `code`. The backend's `detail` is only the HTTP status phrase.

Checks: `npm ci`; `npm audit` (0 vulnerabilities); `typecheck`; `lint`; `test` (51 passed, O evidence); `build` plus the S26 scan — all passed. npm warned that `fsevents@2.3.3` has an unapproved install script; it was not run. Not run yet: Playwright and any R check (later steps).
