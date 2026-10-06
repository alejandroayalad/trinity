// Lint probe: every line below must fail the exact-number rules.
// eslint.config.js ignores this folder, and src/lint.test.ts lints it on
// purpose to prove that the rules reject these float conversions.
const capacity = '100056.000000'

export const probes = [
  Number(capacity),
  parseFloat(capacity),
  Number.parseFloat(capacity),
  +capacity,
]
