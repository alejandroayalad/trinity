import { describe, expect, it } from 'vitest'
import { runLabel, shortId } from './ids'

describe('identifier display', () => {
  it('shows the first 8 characters of a UUID and "Run #N" for run_seq (R21)', () => {
    expect(shortId('4f1c2a9e-1111-4222-8333-444455556666')).toBe('4f1c2a9e')
    expect(runLabel('1044')).toBe('Run #1044')
  })
})
