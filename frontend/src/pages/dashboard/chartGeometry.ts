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
