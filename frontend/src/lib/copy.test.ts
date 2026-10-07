import { describe, expect, it } from 'vitest'
import { BLOCK_CODES, ROLES, RUN_STATUSES, STEP_STAGES, STEP_STATUSES } from '../api/types'
import { BLOCK_REASONS, GENERIC_REASON, ROLE_LABELS, RUN_STATUS, STAGE_LABELS, STEP_STATUS_LABELS, blockReason } from './copy'
import { formatLocalTime } from './dates'
import { xTickIndexes } from '../pages/dashboard/chartGeometry'

// A snake_case token such as "review_required" is a machine code. Visible
// copy must never contain one, so each mapped sentence is checked for "_".
const isSentence = (text: string) => text.trim().length > 0 && !text.includes('_')

describe('copy map', () => {
  it('gives every contract value a sentence without a raw code', () => {
    for (const code of BLOCK_CODES) expect(isSentence(BLOCK_REASONS[code])).toBe(true)
    for (const status of RUN_STATUSES) {
      expect(isSentence(RUN_STATUS[status].label)).toBe(true)
      expect(isSentence(RUN_STATUS[status].summary)).toBe(true)
    }
    for (const stage of STEP_STAGES) expect(isSentence(STAGE_LABELS[stage])).toBe(true)
    for (const status of STEP_STATUSES) expect(isSentence(STEP_STATUS_LABELS[status])).toBe(true)
    for (const role of ROLES) expect(isSentence(ROLE_LABELS[role])).toBe(true)
  })

  it('uses the general sentence for a missing or unknown code', () => {
    expect(blockReason('review_required')).toBe('Resolve the candidate awaiting review first.')
    expect(blockReason(null)).toBe(GENERIC_REASON)
    // A code from a newer server must not reach the screen.
    expect(blockReason('future_code')).toBe(GENERIC_REASON)
    // An inherited object key is not a known code either.
    expect(blockReason('toString')).toBe(GENERIC_REASON)
  })
})

describe('formatLocalTime', () => {
  it('reads the wall-clock digits without converting the timezone', () => {
    // -04:00 is New York summer time. A browser in UTC must still show 06:15.
    expect(formatLocalTime('2026-09-30T06:15:00-04:00')).toBe('30 Sep 2026, 06:15')
    expect(formatLocalTime('2026-10-05T06:15:00')).toBe('5 Oct 2026, 06:15')
  })

  it('returns unreadable text unchanged', () => {
    expect(formatLocalTime('soon')).toBe('soon')
    expect(formatLocalTime('2026-02-30T06:15:00Z')).toBe('2026-02-30T06:15:00Z')
  })
})

describe('xTickIndexes', () => {
  it('labels the first, one-third, two-thirds and last day on a wide plot', () => {
    expect(xTickIndexes(90, 900)).toEqual([0, 30, 59, 89])
  })

  it('keeps only the ends on a narrow plot and removes duplicates', () => {
    expect(xTickIndexes(90, 300)).toEqual([0, 89])
    expect(xTickIndexes(1, 900)).toEqual([0])
    expect(xTickIndexes(0, 900)).toEqual([])
  })
})
