import { formatDayRange, formatShortDay } from '../../lib/dates'
import { formatExact, parseDecimal, positionBetween } from '../../lib/decimal'
import { chartDomain } from './chartGeometry'
import styles from './Chart.module.css'

const WIDTH = 300, HEIGHT = 64, INSET = 5

/**
 * Eight days of reported outage MW for one facility (spec UF-D21).
 * A day without a row is a gap band; it never becomes zero. The selected
 * date is the last day and gets the orange point.
 */
export function Sparkline({ days }: { days: { period: string; outage: string | null }[] }) {
  const { min, max } = chartDomain(days.flatMap((d) => d.outage === null ? [] : [parseDecimal(d.outage)]))
  const step = (WIDTH - 2 * INSET) / Math.max(days.length - 1, 1)
  const x = (i: number) => INSET + i * step
  const y = (value: string) => (BigInt(HEIGHT - INSET) - (positionBetween(parseDecimal(value), min, max, BigInt(HEIGHT - 2 * INSET)) ?? 0n)).toString()
  const last = days.length - 1
  if (!days.length) return null
  return <>
    <div className={styles.spark}>
      {days.map((day, i) => day.outage === null && <div key={day.period} className={styles.sparkGap} style={{ left: `${(Math.max(0, x(i) - step / 2) / WIDTH) * 100}%`, width: `${(step / WIDTH) * 100}%` }} />)}
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={`Reported outage MW for ${formatDayRange(days[0].period, days[last].period)}; gaps mean not reported`}>
        {days.map((day, i) => <g key={day.period}>
          <title>{formatShortDay(day.period)}: {day.outage === null ? 'not reported' : `${formatExact(day.outage)} MW`}</title>
          {day.outage !== null && i > 0 && days[i - 1].outage !== null && <line x1={x(i - 1)} x2={x(i)} y1={y(days[i - 1].outage as string)} y2={y(day.outage)} className={styles.sparkLine} />}
        </g>)}
        {days.map((day, i) => day.outage !== null && <circle key={day.period} cx={x(i)} cy={y(day.outage)} r={i === last ? 4.5 : 3} className={i === last ? styles.sparkSelected : styles.sparkPoint} />)}
      </svg>
    </div>
    <div className={styles.sparkAxis}><span>{formatShortDay(days[0].period)}</span><span>{formatShortDay(days[last].period)}</span></div>
    <p className={styles.sparkCaption}>Reported outage MW, {formatDayRange(days[0].period, days[last].period)}. Gaps stay empty.</p>
  </>
}
