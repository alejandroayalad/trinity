// @vitest-environment node
import { ESLint } from 'eslint'
import { describe, expect, it } from 'vitest'

describe('exact-number lint rules', () => {
  it('reject every float conversion of API text in application code', async () => {
    // `ignore: false` lints the probe file that the normal lint run skips.
    const eslint = new ESLint({ ignore: false })
    const [result] = await eslint.lintFiles(['src/test/lint-probe/banned-conversions.ts'])
    const failures = result.messages.map((message) => `${message.line}:${message.ruleId}`)
    expect(failures).toEqual([
      '7:no-restricted-syntax',
      '8:no-restricted-globals',
      '9:no-restricted-properties',
      '10:no-restricted-syntax',
    ])
  }, 30_000)
})
