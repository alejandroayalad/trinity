import { describe, expect, it } from 'vitest'
import {
  combinedShare,
  compare,
  DecimalError,
  divide,
  formatExact,
  formatFixed,
  isOutOfRange,
  offlineShare,
  parseDecimal,
  positionBetween,
  round,
  scaleBy,
  sum,
  toText,
} from './decimal'

const d = parseDecimal

function shareText(outage: string, capacity: string): string {
  const result = offlineShare(d(outage), d(capacity))
  return result.kind === 'value' ? toText(result.value) : result.kind
}

describe('exact decimals', () => {
  it('shows why floats are not used: binary floats change decimal sums', () => {
    // This is the failure the lint rule prevents in application code.
    expect(Number('0.1') + Number('0.2')).not.toBe(0.3)
    expect(toText(sum([d('0.1'), d('0.2')]))).toBe('0.3')
  })

  it('formats API values without changing them (S06)', () => {
    expect(formatExact('100056.000000')).toBe('100,056')
    expect(formatExact('-12.5')).toBe('-12.5')
    expect(formatExact('0')).toBe('0')
    expect(formatExact('0.000000')).toBe('0')
    expect(formatExact('1160.500000')).toBe('1,160.5')
    expect(formatExact('-1234567.890000')).toBe('-1,234,567.89')
  })

  it('calculates the share 100 × outage ÷ capacity to two places (S06)', () => {
    expect(shareText('14420', '100056')).toBe('14.41')
    expect(shareText('14420.000000', '100056.000000')).toBe('14.41')
    expect(shareText('863', '2108')).toBe('40.94')
  })

  it('returns no share for zero capacity instead of zero or infinity', () => {
    expect(shareText('0', '0')).toBe('zero_capacity')
    expect(shareText('12.5', '0.000000')).toBe('zero_capacity')
  })

  it('keeps a reported zero outage as 0.00, not as missing', () => {
    expect(shareText('0', '2108')).toBe('0.00')
  })

  it('rounds half up, away from zero, like the backend ROUND_HALF_UP', () => {
    expect(toText(round(d('2.345'), 2))).toBe('2.35')
    expect(toText(round(d('2.344'), 2))).toBe('2.34')
    expect(toText(round(d('-2.345'), 2))).toBe('-2.35')
    expect(toText(round(d('-0.004'), 2))).toBe('0.00')
    expect(toText(round(d('7'), 2))).toBe('7.00')
    // 1 ÷ 8 = 0.125 exactly: a tie rounds up to 0.13.
    expect(toText(divide(d('1'), d('8'), 2) ?? d('0'))).toBe('0.13')
  })

  it('preserves negative and out-of-range shares unchanged (R18)', () => {
    expect(shareText('102457', '100056')).toBe('102.40')
    expect(shareText('-125', '1000')).toBe('-12.50')
    expect(isOutOfRange(d('102.40'))).toBe(true)
    expect(isOutOfRange(d('-0.01'))).toBe(true)
    expect(isOutOfRange(d('100.00'))).toBe(false)
    expect(isOutOfRange(d('0'))).toBe(false)
  })

  it('combines shares as Σoutage ÷ Σcapacity, not as an average of percentages (R17)', () => {
    // Rows 1160/3480 (33.33%) and 0/2108 (0%) average to 16.67%, which is wrong.
    const result = combinedShare([d('1160'), d('0')], [d('3480'), d('2108')])
    expect(result.kind === 'value' ? toText(result.value) : result.kind).toBe('20.76')
    expect(combinedShare([], []).kind).toBe('zero_capacity')
  })

  it('rejects text that is not a decimal instead of producing NaN', () => {
    for (const text of ['', ' 1', '1 ', '1e3', '12.', '.5', 'abc', 'NaN', '1,000', '+5']) {
      expect(() => parseDecimal(text), text).toThrow(DecimalError)
    }
  })

  it('formats fixed places with separators and compares across scales', () => {
    expect(formatFixed(d('85636.000000'), 0)).toBe('85,636')
    expect(formatFixed(d('14.41193'), 2)).toBe('14.41')
    expect(compare(d('1.50'), d('1.5'))).toBe(0)
    expect(compare(d('-1'), d('0.000001'))).toBe(-1)
  })

  it('scales values for the count-up without float conversion', () => {
    expect(toText(scaleBy(d('14.41'), 500n, 1000n))).toBe('7.21')
    expect(toText(scaleBy(d('14420'), 1000n, 1000n))).toBe('14420')
  })

  it('maps values to whole-number chart positions', () => {
    expect(positionBetween(d('15'), d('10'), d('20'), 10000n)).toBe(5000n)
    expect(positionBetween(d('102.40'), d('0'), d('100'), 10000n)).toBe(10240n)
    expect(positionBetween(d('5'), d('5'), d('5'), 10000n)).toBeNull()
  })
})
