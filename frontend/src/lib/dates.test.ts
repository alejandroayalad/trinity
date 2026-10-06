import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  addDays,
  datesBetween,
  dayNumber,
  daysInclusive,
  DateTextError,
  formatDay,
  formatDayRange,
  formatDuration,
  formatShortDay,
  formatUtcTime,
  isDateText,
  secondsBetween,
} from './dates'

describe('calendar dates', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('shows period 2026-09-27 as 27 Sep 2026 in every browser time zone (S09)', () => {
    for (const zone of ['America/Los_Angeles', 'Asia/Tokyo', 'UTC']) {
      // Node reads TZ again when it changes. The local hour of a fixed UTC
      // moment proves that the zone took effect for this assertion.
      vi.stubEnv('TZ', zone)
      expect(formatDay('2026-09-27'), zone).toBe('27 Sep 2026')
      expect(formatShortDay('2026-09-27'), zone).toBe('27 Sep')
    }
    vi.stubEnv('TZ', 'America/Los_Angeles')
    expect(new Date(Date.UTC(2026, 8, 27)).getDate()).toBe(26)
  })

  it('does day arithmetic on UTC day numbers, including leap years', () => {
    expect(addDays('2024-02-28', 1)).toBe('2024-02-29')
    expect(addDays('2024-02-29', 1)).toBe('2024-03-01')
    expect(addDays('2026-03-08', 1)).toBe('2026-03-09')
    expect(daysInclusive('2026-08-29', '2026-09-27')).toBe(30)
    expect(daysInclusive('2025-09-28', '2026-09-27')).toBe(365)
    expect(dayNumber('1970-01-02')).toBe(1)
    expect(datesBetween('2026-09-20', '2026-09-22')).toEqual(['2026-09-20', '2026-09-21', '2026-09-22'])
    expect(datesBetween('2026-09-22', '2026-09-20')).toEqual([])
  })

  it('rejects dates that do not exist', () => {
    expect(isDateText('2026-02-29')).toBe(false)
    expect(isDateText('2024-02-29')).toBe(true)
    expect(isDateText('2026-13-01')).toBe(false)
    expect(isDateText('26-09-27')).toBe(false)
    expect(() => formatDay('2026-02-30')).toThrow(DateTextError)
  })

  it('formats ranges and UTC event times', () => {
    expect(formatDayRange('2026-08-29', '2026-09-27')).toBe('29 Aug – 27 Sep 2026')
    expect(formatUtcTime('2026-09-28T14:10:00Z')).toBe('28 Sep 2026, 14:10 UTC')
    expect(formatUtcTime('2026-09-28T14:10:00.123456Z')).toBe('28 Sep 2026, 14:10 UTC')
    expect(formatUtcTime('not a time')).toBe('not a time')
  })

  it('formats durations in the handoff style', () => {
    expect(secondsBetween('2026-10-05T06:15:00Z', '2026-10-05T06:19:12Z')).toBe(252)
    expect(secondsBetween('2026-10-05T06:15:00Z', null)).toBeNull()
    expect(formatDuration(38)).toBe('38s')
    expect(formatDuration(252)).toBe('4m 12s')
    expect(formatDuration(65)).toBe('1m 05s')
    expect(formatDuration(4320)).toBe('1h 12m')
  })
})
