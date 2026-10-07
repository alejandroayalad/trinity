import { compare, parseDecimal, subtract, type Decimal } from '../../lib/decimal'

/** Choose readable 5/10/25 grid steps without rounding the displayed observations. */
export function chartDomain(values: Decimal[]) {
  const zero = parseDecimal('0')
  const lower = values.reduce((a, b) => compare(a, b) < 0 ? a : b, zero)
  const upper = values.reduce((a, b) => compare(a, b) > 0 ? a : b, parseDecimal('5'))
  const span = subtract(upper, lower)
  let step = compare(span, parseDecimal('25')) <= 0 ? 5n : compare(span, parseDecimal('50')) <= 0 ? 10n : 25n
  // Extreme source values remain visible. Grow by whole multiples of 25 so
  // the chart does not allocate millions of ticks for an anomalous share.
  const ceil = (value: Decimal) => { const divisor = 10n ** BigInt(value.scale); return value.units >= 0 ? (value.units + divisor - 1n) / divisor : value.units / divisor }
  const floor = (value: Decimal) => -ceil({ units: -value.units, scale: value.scale })
  while (ceil(span) > step * 10n) step *= 10n
  const lo = floor(lower), hi = ceil(upper)
  const min = (lo < 0 ? -((-lo + step - 1n) / step) : lo / step) * step
  const max = ((hi + step - 1n) / step) * step
  const ticks: string[] = []
  for (let value = min; value <= max; value += step) ticks.push(value.toString())
  return { min: parseDecimal(min.toString()), max: parseDecimal(max.toString()), ticks }
}

/**
 * Choose the day indexes that get an x-axis label: the first day, the days
 * at one third and two thirds, and the last day (handoff B.3). A plot under
 * 480px wide keeps only the first and last label, so labels never overlap
 * at 320px. Duplicate indexes are removed for short ranges.
 *
 * Example: 90 days on a 900px plot give [0, 30, 59, 89].
 */
export function xTickIndexes(count: number, plotWidth: number): number[] {
  if (count <= 0) return []
  const last = count - 1
  const picks = plotWidth < 480 ? [0, last] : [0, Math.round(last / 3), Math.round((2 * last) / 3), last]
  return [...new Set(picks)]
}
