import { chartDomain } from './chartGeometry'
import { parseDecimal, positionBetween } from '../../lib/decimal'

/** Draw missing dates as gaps. A single reported day remains a visible point. */
export function Sparkline({ days }: { days: { period: string; outage: string | null }[] }) {
  const { min, max } = chartDomain(days.flatMap((d) => d.outage === null ? [] : [parseDecimal(d.outage)]))
  const x = (i: number) => 8 + i * 284 / Math.max(1, days.length - 1)
  const y = (value: string) => (72n - (positionBetween(parseDecimal(value), min, max, 60n) ?? 0n)).toString()
  return <svg viewBox="0 0 300 85" className="sparkline" role="img" aria-label="Eight-day facility outage in MW; gaps mean not reported">{days.map((day, i) => <g key={day.period}><title>{day.period}: {day.outage === null ? 'not reported' : day.outage + ' MW'}</title>{day.outage !== null && <><circle cx={x(i)} cy={y(day.outage)} r="3" className="chart-dot" />{i > 0 && days[i - 1].outage !== null && <line x1={x(i - 1)} x2={x(i)} y1={y(days[i - 1].outage as string)} y2={y(day.outage)} className="chart-line" />}</>}</g>)}</svg>
}
