/**
 * Calendar dates and UTC event times.
 *
 * An observation date such as "2026-09-27" is a calendar date, not a moment
 * in time. `new Date("2026-09-27")` would give midnight UTC, which a browser
 * in Los Angeles shows as 26 Sep. This module therefore keeps dates as
 * YYYY-MM-DD strings, does day arithmetic on UTC day numbers and formats
 * with fixed month names. Event times (published_at, requested_at) are shown
 * in UTC with a "UTC" suffix (spec R19).
 */

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'] as const
const DAY_MS = 86_400_000
const DATE_TEXT = /^(\d{4})-(\d{2})-(\d{2})$/

type CalendarDate = { year: number; month: number; day: number }

export class DateTextError extends Error {
  constructor() {
    super('Value is not a YYYY-MM-DD date.')
    this.name = 'DateTextError'
  }
}

/**
 * Read YYYY-MM-DD text. Reject dates that do not exist, such as 2026-02-30:
 * Date.UTC would move that date to 2 Mar, so the round trip must match.
 */
function parseCalendarDate(text: string): CalendarDate {
  const match = DATE_TEXT.exec(text)
  if (match === null) throw new DateTextError()
  const year = Number.parseInt(match[1], 10)
  const month = Number.parseInt(match[2], 10)
  const day = Number.parseInt(match[3], 10)
  const check = new Date(Date.UTC(year, month - 1, day))
  if (check.getUTCFullYear() !== year || check.getUTCMonth() !== month - 1 || check.getUTCDate() !== day) {
    throw new DateTextError()
  }
  return { year, month, day }
}

export function isDateText(text: string): boolean {
  try {
    parseCalendarDate(text)
    return true
  } catch {
    return false
  }
}

/** Return the number of whole days since 1970-01-01 for a calendar date. */
export function dayNumber(text: string): number {
  const { year, month, day } = parseCalendarDate(text)
  return Date.UTC(year, month - 1, day) / DAY_MS
}

/** Return the YYYY-MM-DD text for a day number. */
export function fromDayNumber(days: number): string {
  return new Date(days * DAY_MS).toISOString().slice(0, 10)
}

export function addDays(text: string, days: number): string {
  return fromDayNumber(dayNumber(text) + days)
}

/** Count the dates from start to end, both included. 1 Sep to 30 Sep is 30. */
export function daysInclusive(start: string, end: string): number {
  return dayNumber(end) - dayNumber(start) + 1
}

/** Return every date from start to end, both included, in order. */
export function datesBetween(start: string, end: string): string[] {
  const first = dayNumber(start)
  const count = dayNumber(end) - first + 1
  return Array.from({ length: Math.max(0, count) }, (_, index) => fromDayNumber(first + index))
}

/** "2026-09-27" gives "27 Sep 2026". */
export function formatDay(text: string): string {
  const { year, month, day } = parseCalendarDate(text)
  return `${day} ${MONTHS[month - 1]} ${year}`
}

/** "2026-09-27" gives "27 Sep". */
export function formatShortDay(text: string): string {
  const { month, day } = parseCalendarDate(text)
  return `${day} ${MONTHS[month - 1]}`
}

/** "2026-08-29" to "2026-09-27" gives "29 Aug – 27 Sep 2026". */
export function formatDayRange(start: string, end: string): string {
  return `${formatShortDay(start)} – ${formatDay(end)}`
}

/**
 * Format an RFC 3339 event time in UTC: "28 Sep 2026, 14:10 UTC".
 * The Date object is correct here because the value is a moment in time.
 * Return the input unchanged when it cannot be read, so no value is invented.
 */
export function formatUtcTime(text: string): string {
  const moment = new Date(text)
  if (Number.isNaN(moment.getTime())) return text
  const pad = (value: number) => String(value).padStart(2, '0')
  return (
    `${moment.getUTCDate()} ${MONTHS[moment.getUTCMonth()]} ${moment.getUTCFullYear()}, ` +
    `${pad(moment.getUTCHours())}:${pad(moment.getUTCMinutes())} UTC`
  )
}

/** Return the whole seconds from start to end, or null when either is missing or unreadable. */
export function secondsBetween(start: string | null, end: string | null): number | null {
  if (start === null || end === null) return null
  const from = new Date(start).getTime()
  const to = new Date(end).getTime()
  if (Number.isNaN(from) || Number.isNaN(to) || to < from) return null
  return Math.round((to - from) / 1000)
}

/** Format a duration in the handoff style: "38s", "4m 12s", "1h 12m". */
export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, '0')}s`
  return `${Math.floor(seconds / 3600)}h ${String(Math.floor((seconds % 3600) / 60)).padStart(2, '0')}m`
}

/**
 * Format a local wall-clock time such as "2026-09-30T06:15:00-04:00" as
 * "30 Sep 2026, 06:15". The text already holds the time in the schedule's
 * own timezone, so this function reads its digits and never creates a Date:
 * a browser in another timezone therefore cannot shift it (spec R19).
 * Return the input unchanged when it does not start with a date and time.
 */
export function formatLocalTime(text: string): string {
  const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})/.exec(text)
  if (match === null || !isDateText(match[1])) return text
  return `${formatDay(match[1])}, ${match[2]}:${match[3]}`
}
