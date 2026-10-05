/**
 * Exact decimal arithmetic for API values.
 *
 * The API sends measurements as decimal strings, for example "100056.000000".
 * A JavaScript number is a binary float and cannot hold every decimal value.
 * This module keeps a decimal as a scaled BigInt instead: the text "14.41"
 * becomes { units: 1441n, scale: 2 }, which means 1441 × 10^-2.
 *
 * Application state keeps the original strings. Code parses a string here
 * only to calculate or format it. A string that is not a decimal is an error,
 * never NaN or zero.
 */

export type Decimal = {
  /** The value multiplied by 10^scale, so it is always a whole number. */
  readonly units: bigint
  /** The number of digits after the decimal point. */
  readonly scale: number
}

export class DecimalError extends Error {
  constructor() {
    // The message does not repeat the input. Error text can reach logs.
    super('Value is not a decimal string.')
    this.name = 'DecimalError'
  }
}

// An optional minus sign, digits, then an optional point with digits.
// "100056.000000", "-12.5" and "0" match. "1e3", " 12", "12." and "" do not.
const DECIMAL_TEXT = /^(-?)(\d+)(?:\.(\d+))?$/

const ZERO: Decimal = { units: 0n, scale: 0 }
const HUNDRED: Decimal = { units: 100n, scale: 0 }

function powerOfTen(exponent: number): bigint {
  return 10n ** BigInt(exponent)
}

/** Parse API decimal text exactly. Throw DecimalError for any other text. */
export function parseDecimal(text: string): Decimal {
  const match = DECIMAL_TEXT.exec(text)
  if (match === null) throw new DecimalError()
  const [, sign, whole, fraction = ''] = match
  const magnitude = BigInt(whole + fraction)
  return { units: sign === '-' ? -magnitude : magnitude, scale: fraction.length }
}

/** Return true when the text is a decimal string that parseDecimal accepts. */
export function isDecimalText(text: string): boolean {
  return DECIMAL_TEXT.test(text)
}

/** Express a value with more fractional digits. The value does not change. */
function withScale(value: Decimal, scale: number): bigint {
  return value.units * powerOfTen(scale - value.scale)
}

/** Return -1, 0 or 1, as a is less than, equal to or greater than b. */
export function compare(a: Decimal, b: Decimal): -1 | 0 | 1 {
  const scale = Math.max(a.scale, b.scale)
  const left = withScale(a, scale)
  const right = withScale(b, scale)
  if (left < right) return -1
  return left > right ? 1 : 0
}

export function add(a: Decimal, b: Decimal): Decimal {
  const scale = Math.max(a.scale, b.scale)
  return { units: withScale(a, scale) + withScale(b, scale), scale }
}

export function subtract(a: Decimal, b: Decimal): Decimal {
  return add(a, { units: -b.units, scale: b.scale })
}

/** Add a list of decimals. An empty list gives zero. */
export function sum(values: readonly Decimal[]): Decimal {
  return values.reduce(add, ZERO)
}

export function isZero(value: Decimal): boolean {
  return value.units === 0n
}

/**
 * Divide two whole numbers and round half up, away from zero.
 *
 * BigInt division drops the remainder. Adding half of the divisor before
 * the division rounds the magnitude instead: 25 / 10 gives 3, 24 / 10 gives 2
 * and -25 / 10 gives -3. Python's Decimal ROUND_HALF_UP, which the backend
 * uses, rounds ties the same way.
 */
function divideHalfUp(numerator: bigint, denominator: bigint): bigint {
  const negative = numerator < 0n !== denominator < 0n
  const top = numerator < 0n ? -numerator : numerator
  const bottom = denominator < 0n ? -denominator : denominator
  const magnitude = (2n * top + bottom) / (2n * bottom)
  return negative ? -magnitude : magnitude
}

/** Round to a number of fractional digits, half up. */
export function round(value: Decimal, places: number): Decimal {
  if (value.scale <= places) return { units: withScale(value, places), scale: places }
  return { units: divideHalfUp(value.units, powerOfTen(value.scale - places)), scale: places }
}

/**
 * Divide a by b and round half up to a number of fractional digits.
 * Return null when b is zero, so the caller must state why no value exists.
 *
 * With a = A × 10^-sa and b = B × 10^-sb, the rounded result with p places is
 * A × 10^(p + sb) ÷ (B × 10^sa).
 */
export function divide(a: Decimal, b: Decimal, places: number): Decimal | null {
  if (b.units === 0n) return null
  const numerator = a.units * powerOfTen(places + b.scale)
  const denominator = b.units * powerOfTen(a.scale)
  return { units: divideHalfUp(numerator, denominator), scale: places }
}

export function multiply(a: Decimal, b: Decimal): Decimal {
  return { units: a.units * b.units, scale: a.scale + b.scale }
}

export type ShareResult = { readonly kind: 'value'; readonly value: Decimal } | { readonly kind: 'zero_capacity' }

/**
 * Calculate the offline share 100 × outage ÷ capacity, rounded half up to
 * two places (spec R17). Zero capacity has no share.
 *
 * Example: outage "14420" and capacity "100056" give 14.41.
 */
export function offlineShare(outage: Decimal, capacity: Decimal): ShareResult {
  const share = divide(multiply(outage, HUNDRED), capacity, 2)
  return share === null ? { kind: 'zero_capacity' } : { kind: 'value', value: share }
}

/**
 * Calculate a combined share as Σoutage ÷ Σcapacity, never as an average of
 * row percentages (spec R17). An empty list has no capacity, so no share.
 */
export function combinedShare(outages: readonly Decimal[], capacities: readonly Decimal[]): ShareResult {
  return offlineShare(sum(outages), sum(capacities))
}

/** Return true when a percentage is below 0 or above 100 (spec R18). */
export function isOutOfRange(percent: Decimal): boolean {
  return compare(percent, ZERO) < 0 || compare(percent, HUNDRED) > 0
}

/** Insert a comma between each group of three whole digits. */
function groupThousands(digits: string): string {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
}

/** Write a decimal as text with all its fractional digits. */
function toPlainText(value: Decimal, grouping: boolean): string {
  const negative = value.units < 0n
  const digits = (negative ? -value.units : value.units).toString().padStart(value.scale + 1, '0')
  const whole = digits.slice(0, digits.length - value.scale)
  const fraction = digits.slice(digits.length - value.scale)
  const wholeText = grouping ? groupThousands(whole) : whole
  // BigInt has no negative zero. A value that rounds to zero therefore has
  // no minus sign: -0.004 rounded to 2 places is "0.00", not "-0.00".
  const sign = negative ? '-' : ''
  return sign + wholeText + (fraction ? `.${fraction}` : '')
}

/**
 * Format a value rounded half up to a fixed number of places, with
 * thousands separators. Use it for calculated shares (2 places).
 */
export function formatFixed(value: Decimal, places: number): string {
  return toPlainText(round(value, places), true)
}

/**
 * Format API decimal text without changing its value: add thousands
 * separators and remove only trailing fractional zeros.
 * "100056.000000" gives "100,056", "-12.5" stays "-12.5" and "0" stays "0".
 */
export function formatExact(text: string): string {
  const value = parseDecimal(text)
  let { units, scale } = value
  while (scale > 0 && units % 10n === 0n) {
    units /= 10n
    scale -= 1
  }
  return toPlainText({ units, scale }, true)
}

/** Write a decimal as plain text without separators, for example "14.41". */
export function toText(value: Decimal): string {
  return toPlainText(value, false)
}

/**
 * Scale a value by a whole-number fraction numerator ÷ denominator, rounded
 * half up at the value's own scale. The KPI count-up uses it to show exact
 * intermediate values without a float conversion.
 */
export function scaleBy(value: Decimal, numerator: bigint, denominator: bigint): Decimal {
  return { units: divideHalfUp(value.units * numerator, denominator), scale: value.scale }
}

/**
 * Map a value to a whole-number position between min (0) and max (steps).
 * The chart uses it to place points without converting a measurement to a
 * float. Values outside min..max give positions outside 0..steps.
 * Return null when min equals max.
 */
export function positionBetween(value: Decimal, min: Decimal, max: Decimal, steps: bigint): bigint | null {
  const span = subtract(max, min)
  if (span.units === 0n) return null
  const offset = subtract(value, min)
  const scale = Math.max(offset.scale, span.scale)
  return divideHalfUp(withScale(offset, scale) * steps, withScale(span, scale))
}
