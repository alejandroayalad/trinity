import { useEffect, useRef, useState } from 'react'
import { useReducedMotion } from '../../lib/useReducedMotion'
import { chartDomain, xTickIndexes } from './chartGeometry'
import { dayNumber, formatDay, formatShortDay } from '../../lib/dates'
import type { NationalDay } from '../../api/types'
import { add, round, scaleBy, subtract, toText, formatExact, formatFixed, isOutOfRange, parseDecimal, positionBetween } from '../../lib/decimal'
import styles from './Chart.module.css'

/** Plot height and the inset that keeps the 12px pinned dot inside the plot. */
const PLOT_HEIGHT = 260
const INSET = 6

/** "29 Sep" for short ranges; "29 Sep 25" when the range has more than 120 days. */
function tickLabel(period: string, long: boolean) {
  return long ? `${formatShortDay(period)} ${period.slice(2, 4)}` : formatShortDay(period)
}

/**
 * The national offline-share chart (spec UF-D07–D12, R26).
 *
 * The y labels sit in an HTML gutter left of the plot. The SVG covers only
 * the plot, and its viewBox width equals its displayed width, so one SVG unit
 * is one pixel. Gap bands and the tooltip are HTML layers over the SVG.
 * Source measurements stay exact decimals; SVG receives integer positions.
 */
export function NationalChart({ days, selected, onSelect }: { days: NationalDay[]; selected: string | null; onSelect: (period: string | null) => void }) {
  const viewport = useRef<SVGSVGElement>(null)
  const [width, setWidth] = useState(800)
  // Match SVG coordinates to its displayed width. A fixed desktop viewBox
  // shrinks text on phones even when CSS gives the chart enough height.
  useEffect(() => {
    const svg = viewport.current
    if (!svg || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width > 0) setWidth(Math.round(entry.contentRect.width))
    })
    observer.observe(svg)
    return () => observer.disconnect()
  }, [])
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

  // Horizontal geometry in pixels. A day spans plotWidth ÷ (days − 1); a gap
  // band reaches half a day to each side of its point.
  const plotLeft = INSET, plotRight = Math.max(INSET + 1, width - INSET), plotWidth = plotRight - plotLeft
  const dayWidth = plotWidth / Math.max(right - left, 1)
  const x = (index: number) => left === right ? width / 2 : plotLeft + (dayNumber(days[index].period) - left) * plotWidth / (right - left)
  const bandLeft = (index: number) => Math.max(0, x(index) - dayWidth / 2)
  const bandWidth = (index: number) => Math.max(0, Math.min(width, x(index) + dayWidth / 2) - bandLeft(index))
  // Vertical geometry: the decimal position becomes integer pixel text.
  const y = (value: string) => (BigInt(PLOT_HEIGHT - INSET) - (positionBetween(parseDecimal(value), min, max, BigInt(PLOT_HEIGHT - 2 * INSET)) ?? 0n)).toString()
  const gutter = Math.max(44, Math.max(...ticks.map((tick) => tick.length + 1)) * 7 + 10)

  const active = Math.min(Math.max(0, days.length - 1), hover ?? Math.max(0, days.findIndex((d) => d.period === selected)))
  const pinned = days.findIndex((d) => d.period === selected)
  const segments: { index: number; value: string }[][] = []
  for (const [index, day] of days.entries()) {
    if (day.offline_share_percent !== null) {
      if (!index || days[index - 1].offline_share_percent === null) segments.push([])
      segments[segments.length - 1].push({ index, value: day.offline_share_percent })
    }
  }
  // Adjacent missing days form one band with one dashed edge on each side.
  const gaps: [number, number][] = []
  for (const [index, day] of days.entries()) {
    if (day.offline_share_percent !== null) continue
    const open = gaps.at(-1)
    if (open && open[1] === index - 1) open[1] = index
    else gaps.push([index, index])
  }
  const long = days.length > 120
  const tickIndexes = xTickIndexes(days.length, width)
  const hovered = hover !== null && !moving ? days[hover] : undefined
  const tooltipSide = hover === null ? 'center' : x(hover) < width * 0.14 ? 'right' : x(hover) > width * 0.86 ? 'left' : 'center'
  const activeDay = days[active]

  if (!values.length) return <div className={styles.empty}>No reported values in this range.</div>
  return <div>
    <div className={styles.grid} style={{ gridTemplateColumns: `${gutter}px minmax(0, 1fr)` }}>
      <div className={styles.gutter} aria-hidden="true">{ticks.map((tick) => <span key={tick} data-part="tick-y" className={styles.tickY} style={{ top: `${y(tick)}px` }}>{tick}%</span>)}</div>
      <div className={styles.plot}>
        {gaps.map(([first, last]) => <div key={first} data-part="gap" className={styles.gap} style={{ left: `${bandLeft(first)}px`, width: `${bandLeft(last) + bandWidth(last) - bandLeft(first)}px` }} />)}
        <svg ref={viewport} className={styles.svg} viewBox={`0 0 ${width} ${PLOT_HEIGHT}`} role="application" aria-label="Daily offline share chart. Use left and right arrows to inspect, Enter to pin, Escape to clear." tabIndex={0} onKeyDown={(e) => {
          if (moving) return
          if (['ArrowLeft', 'ArrowRight', 'Enter', 'Escape'].includes(e.key)) e.preventDefault()
          if (e.key === 'ArrowLeft') setHover(Math.max(0, active - 1))
          if (e.key === 'ArrowRight') setHover(Math.min(days.length - 1, active + 1))
          if (e.key === 'Enter') onSelect(days[active]?.period ?? null)
          if (e.key === 'Escape') { onSelect(null); setHover(null) }
        }} onBlur={() => setHover(null)}>
          {ticks.map((tick) => <line key={tick} x1="0" x2={width} y1={y(tick)} y2={y(tick)} className={styles.gridline} />)}
          <g className={styles.reveal}>
            {segments.map((segment) => <g key={segment[0].index} pointerEvents="none">
              {segment.length > 1 && <polyline className={styles.line} points={segment.map((point) => `${x(point.index)},${y(point.value)}`).join(' ')} />}
              {segment.filter((point) => segment.length === 1 && !isOutOfRange(parseDecimal(point.value))).map((point) => <circle key={point.index} cx={x(point.index)} cy={y(point.value)} r="3" className={styles.dot} />)}
              {segment.filter((point) => isOutOfRange(parseDecimal(point.value))).map((point) => <circle key={`o${point.index}`} data-part="outlier" cx={x(point.index)} cy={y(point.value)} r="5" className={styles.outlier}><title>Outside 0–100, left as-is</title></circle>)}
            </g>)}
          </g>
          {days.map((day, i) => <rect key={day.period} x={bandLeft(i)} y="0" width={bandWidth(i)} height={PLOT_HEIGHT} fill="transparent" onMouseEnter={() => { if (!moving) setHover(i) }} onMouseLeave={() => setHover(null)} onClick={() => { if (!moving) onSelect(day.period) }} />)}
          {!moving && pinned >= 0 && <g pointerEvents="none">
            <line x1={x(pinned)} x2={x(pinned)} y1="0" y2={PLOT_HEIGHT} className={styles.pinLine} />
            {days[pinned].offline_share_percent !== null && <circle cx={x(pinned)} cy={y(days[pinned].offline_share_percent)} r="6" className={styles.pinDot} />}
          </g>}
          {hovered !== undefined && hover !== null && <g pointerEvents="none">
            <line x1={x(hover)} x2={x(hover)} y1="0" y2={PLOT_HEIGHT} className={styles.crosshair} />
            {hovered.offline_share_percent !== null && <circle cx={x(hover)} cy={y(hovered.offline_share_percent)} r="5" className={styles.hoverDot} />}
          </g>}
        </svg>
        {hovered !== undefined && hover !== null && <div aria-hidden="true" className={[styles.tooltip, styles[tooltipSide]].join(' ')} style={{ left: `${x(hover)}px` }}>
          <div className={styles.tooltipDate}>{formatDay(hovered.period)}</div>
          {hovered.offline_share_percent === null ? <div>○ Not reported</div> : <div className={styles.tooltipGrid}>
            <span>Offline share</span><b>{formatFixed(parseDecimal(hovered.offline_share_percent), 2)}%</b>
            <span>Outage</span><b>{hovered.outage === null ? '—' : `${formatExact(hovered.outage)} MW`}</b>
            <span>Capacity</span><b>{hovered.capacity === null ? '—' : `${formatExact(hovered.capacity)} MW`}</b>
          </div>}
          {hovered.offline_share_percent !== null && isOutOfRange(parseDecimal(hovered.offline_share_percent)) && <div className={styles.tooltipWarning}>! Outside 0–100, left as-is</div>}
        </div>}
      </div>
      <span />
      <div className={styles.ticksX} aria-hidden="true">{tickIndexes.map((index, n) => <span key={index} data-part="tick-x" className={styles.tickX} style={{ left: `${x(index)}px`, transform: n === 0 ? 'none' : n === tickIndexes.length - 1 ? 'translateX(-100%)' : 'translateX(-50%)' }}>{tickLabel(days[index].period, long)}</span>)}</div>
    </div>
    <p aria-live="polite" className="sr-only">{activeDay && formatDay(activeDay.period)} · {activeDay?.offline_share_percent == null ? '○ Not reported' : `${formatFixed(parseDecimal(activeDay.offline_share_percent), 2)}%`}</p>
    <div className={styles.legend}>
      <span className={styles.legendItems}><span><i className={styles.swatchLine} />Reported offline share</span><span><i className={styles.swatchGap} />Gap = not reported</span></span>
      <span>Hover to inspect · Click to pin · Arrow keys when focused</span>
    </div>
  </div>
}
