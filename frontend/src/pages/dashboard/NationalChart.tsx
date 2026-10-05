import { useEffect, useId, useRef, useState } from 'react'
import { useReducedMotion } from '../../lib/useReducedMotion'
import { chartDomain } from './chartGeometry'
import { dayNumber, fromDayNumber } from '../../lib/dates'
import type { NationalDay } from '../../api/types'
import { add, round, scaleBy, subtract, toText, formatFixed, isOutOfRange, parseDecimal, positionBetween } from '../../lib/decimal'

/** SVG receives integer pixel positions. Source measurements stay exact decimals. */
export function NationalChart({ days, selected, onSelect }: { days: NationalDay[]; selected: string | null; onSelect: (period: string | null) => void }) {
  const pattern = useId()
  const clip = useId()
  const [hover, setHover] = useState<number | null>(null)
  const values = days.flatMap((d) => d.offline_share_percent === null ? [] : [parseDecimal(d.offline_share_percent)])
  const target = chartDomain(values)
  const minText = toText(target.min), maxText = toText(target.max)
  const x0 = days.length ? dayNumber(days[0].period) : 0
  const x1 = days.length ? dayNumber(days.at(-1)!.period) : 0
  const reduced = useReducedMotion()
  const [domain, setDomain] = useState({ min: target.min, max: target.max, x0, x1, moving: false })
  const previous = useRef({ min: target.min, max: target.max, x0, x1 })
  useEffect(() => {
    const from = previous.current
    const to = { min: parseDecimal(minText), max: parseDecimal(maxText), x0, x1 }
    if (reduced) { previous.current = to; return }
    if (toText(from.min) === minText && toText(from.max) === maxText && from.x0 === x0 && from.x1 === x1) {
      const frame = requestAnimationFrame(() => setDomain({ ...to, moving: false }))
      return () => cancelAnimationFrame(frame)
    }
    let frame = 0
    let started: number | undefined
    const tick = (now: number) => {
      started ??= now
      const elapsed = Math.min(650, Math.round(now - started))
      // Cubic easing acts only on time. Decimal interpolation keeps source
      // magnitudes out of binary floating point, even for large outliers.
      const time = BigInt(elapsed), duration = 650n
      const numerator = duration ** 3n - (duration - time) ** 3n
      const fraction = 1 - (1 - elapsed / 650) ** 3
      const next = { min: add(from.min, scaleBy(round(subtract(to.min, from.min), 6), numerator, duration ** 3n)),
        max: add(from.max, scaleBy(round(subtract(to.max, from.max), 6), numerator, duration ** 3n)),
        x0: from.x0 + (x0 - from.x0) * fraction, x1: from.x1 + (x1 - from.x1) * fraction }
      previous.current = next
      setDomain({ ...next, moving: elapsed < 650 })
      if (elapsed < 650) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [minText, maxText, x0, x1, reduced])
  const { min, max } = reduced ? target : domain
  const left = reduced ? x0 : domain.x0, right = reduced ? x1 : domain.x1
  const moving = !reduced && domain.moving
  const ticks = target.ticks
  const x = (index: number) => left === right ? 400 : 40 + (dayNumber(days[index].period) - left) * 720 / (right - left)
  const gapLeft = (index: number) => Math.max(40, x(index) - 360 / Math.max(right - left, 1))
  const gapWidth = (index: number) => Math.max(0, Math.min(760, x(index) + 360 / Math.max(right - left, 1)) - gapLeft(index))
  const y = (value: string) => (260n - (positionBetween(parseDecimal(value), min, max, 220n) ?? 0n)).toString()
  const active = Math.min(Math.max(0, days.length - 1), hover ?? Math.max(0, days.findIndex((d) => d.period === selected)))
  const segments: { index: number; value: string }[][] = []
  for (const [index, day] of days.entries()) {
    if (day.offline_share_percent !== null) {
      if (!index || days[index - 1].offline_share_percent === null) segments.push([])
      segments[segments.length - 1].push({ index, value: day.offline_share_percent })
    }
  }
  return <div className="stack"><svg className="national-chart" viewBox="0 0 800 310" role="application" aria-label="National offline share. Use arrow keys to inspect dates, Enter to pin, Escape to clear." tabIndex={0} onKeyDown={(e) => {
    if (moving) return
    if (['ArrowLeft', 'ArrowRight', 'Enter', 'Escape'].includes(e.key)) e.preventDefault()
    if (e.key === 'ArrowLeft') setHover(Math.max(0, active - 1))
    if (e.key === 'ArrowRight') setHover(Math.min(days.length - 1, active + 1))
    if (e.key === 'Enter') onSelect(days[active]?.period ?? null)
    if (e.key === 'Escape') { onSelect(null); setHover(null) }
  }}>
    <defs><pattern id={pattern} width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="8" className="hatch" /></pattern><clipPath id={clip}><rect x="40" y="35" width="720" height="230" /></clipPath></defs>
    {ticks.map((tick) => <g key={tick}><line x1="40" x2="760" y1={y(tick)} y2={y(tick)} className="gridline" /><text x="2" y={y(tick)}>{tick}%</text></g>)}
    <g clipPath={`url(#${clip})`}><g className="chart-reveal">
    {days.map((day, i) => <g key={day.period}>{day.offline_share_percent === null && <rect x={gapLeft(i)} y="40" width={gapWidth(i)} height="220" fill={`url(#${pattern})`} />}
      <rect x={gapLeft(i)} y="35" width={gapWidth(i)} height="230" fill="transparent" onMouseEnter={() => { if (!moving) setHover(i) }} onMouseLeave={() => setHover(null)} onClick={() => { if (!moving) onSelect(day.period) }}><title>{day.period}: {day.offline_share_percent ?? 'Not reported'}</title></rect></g>)}
    {segments.map((segment) => <g key={segment[0].index} pointerEvents="none"><polyline className="chart-line" points={segment.map((point) => `${x(point.index)},${y(point.value)}`).join(' ')} />{segment.filter((point) => segment.length === 1 || isOutOfRange(parseDecimal(point.value))).map((point) => <circle key={point.index} cx={x(point.index)} cy={y(point.value)} r="3" className={isOutOfRange(parseDecimal(point.value)) ? 'outlier' : 'chart-dot'} />)}</g>)}
    </g></g>
    {!moving && (hover !== null || selected !== null) && <line x1={x(active)} x2={x(active)} y1="35" y2="265" className="crosshair" pointerEvents="none" />}
    <text x="40" y="295">{fromDayNumber(Math.round(left))}</text><text x="760" y="295" textAnchor="end">{fromDayNumber(Math.round(right))}</text>
  </svg><p aria-live="polite">{days[active]?.period} · {days[active]?.offline_share_percent == null ? '○ Not reported' : `${formatFixed(parseDecimal(days[active].offline_share_percent), 2)}%`}</p><p className="muted">Orange: reported share · Hatched: not reported · Ring: out of range</p></div>
}
