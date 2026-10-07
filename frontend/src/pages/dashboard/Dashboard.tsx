import { useEffect, useId, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getDashboard, getMetric, getPreview } from '../../api/endpoints'
import { ApiError, isApiError } from '../../api/client'
import { queryKeys } from '../../api/queryKeys'
import type { DashboardResponse, NationalDay, PreviewResponse } from '../../api/types'
import { useSession } from '../../session/SessionProvider'
import { useReducedMotion } from '../../lib/useReducedMotion'
import { Button, TextButton, TextLink } from '../../components/controls/Button'
import { Field, filterInputClass } from '../../components/controls/Field'
import { Segmented } from '../../components/controls/Segmented'
import { ShortId } from '../../components/controls/ShortId'
import { Tabs } from '../../components/controls/Tabs'
import { PageHeader } from '../../components/layout/PageHeader'
import { MissingChip, Tag, UnavailableValue } from '../../components/feedback/StatusBadge'
import { EmptyState, LoadingRows } from '../../components/feedback/States'
import { addDays, datesBetween, daysInclusive, formatDay, formatDayRange, formatShortDay, formatUtcTime, isDateText } from '../../lib/dates'
import { compare, formatExact, formatFixed, isOutOfRange, parseDecimal, scaleBy, subtract, sum, toText } from '../../lib/decimal'
import { Diagnostics, OutOfRangeTag, PageError, Share, sharedStyles } from '../shared'
import { Sparkline } from './Sparkline'
import { NationalChart } from './NationalChart'
import styles from './Dashboard.module.css'

/** Format a calendar date, or return the text unchanged when it is not a date. */
function day(text: string) {
  return isDateText(text) ? formatDay(text) : text
}
function shortDay(text: string) {
  return isDateText(text) ? formatShortDay(text) : text
}

function Value({ value, percent = false }: { value: string | null; percent?: boolean }) {
  if (value === null) return <MissingChip />
  return <>{percent ? `${formatFixed(parseDecimal(value), 2)}%` : formatExact(value)}{percent && isOutOfRange(parseDecimal(value)) && <OutOfRangeTag />}</>
}
function CountValue({ value, percent = false }: { value: string | null; percent?: boolean }) {
  const [progress, setProgress] = useState(0)
  const reduced = useReducedMotion()
  useEffect(() => {
    if (value === null || reduced) return
    let frame = 0; let start: number | undefined
    const tick = (now: number) => { start ??= now; const elapsed = Math.min(900, Math.round(now - start)); setProgress(elapsed); if (elapsed < 900) frame = requestAnimationFrame(tick) }
    frame = requestAnimationFrame(tick); return () => cancelAnimationFrame(frame)
  }, [value, reduced])
  const display = value === null || reduced ? value : toText(scaleBy(parseDecimal(value), 900n ** 3n - (900n - BigInt(progress)) ** 3n, 900n ** 3n))
  return <Value value={display} percent={percent} />
}

type RangeChoice = '30d' | '90d' | '1y' | 'custom'
const RANGE_OPTIONS = [{ value: '30d', label: '30 days' }, { value: '90d', label: '90 days' }, { value: '1y', label: 'Last 365 days' }, { value: 'custom', label: 'Custom range' }] as const

export function Dashboard() {
  const { me } = useSession()
  const [range, setRange] = useState<{ preset?: string; start?: string; end?: string }>({ preset: '30d' })
  const [custom, setCustom] = useState(false), [start, setStart] = useState(''), [end, setEnd] = useState('')
  const query = useQuery({ queryKey: queryKeys.dashboard(JSON.stringify(range)), queryFn: ({ signal }) => getDashboard(range, signal), placeholderData: (previous) => previous })
  const valid = isDateText(start) && isDateText(end) && daysInclusive(start, end) > 0 && daysInclusive(start, end) <= 366
  const choice: RangeChoice = custom ? 'custom' : (range.preset as RangeChoice | undefined) ?? 'custom'
  const loaded = query.data?.data.range
  // The range row sits in the chart section. It is the same element in every
  // state, so a click during the first load still changes the request.
  const controls = <div className={styles.rangeRow}>
    <Segmented label="Range" options={RANGE_OPTIONS} value={choice} onChange={(value) => { if (value === 'custom') setCustom(true); else { setCustom(false); setRange({ preset: value }) } }} />
    {custom && <form className={styles.customRange} onSubmit={(e) => { e.preventDefault(); if (valid) setRange({ start, end }) }}>
      <Field label="From" compact><input className={filterInputClass} type="date" value={start} onChange={(e) => setStart(e.target.value)} /></Field>
      <Field label="To" compact><input className={filterInputClass} type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></Field>
      <Button type="submit" size="compact" disabled={!valid}>Apply range</Button>
      <span className={styles.hint}>Up to 366 dates.</span>
    </form>}
    {loaded && isDateText(loaded.start) && isDateText(loaded.end) && <span className={styles.rangeLabel}>{formatDayRange(loaded.start, loaded.end)} · {daysInclusive(loaded.start, loaded.end)} days{query.isFetching && ' · Updating…'}</span>}
  </div>
  const publication = me?.publication
  return <section>
    <PageHeader title="U.S. nuclear fleet" subtitle="Latest published observation" aside={publication && <dl className={styles.meta}>
      <dt>Publication</dt><dd className="mono"><ShortId value={publication.version_id} /></dd>
      <dt>Published</dt><dd>{formatUtcTime(publication.published_at)}</dd>
      <dt>Observation</dt><dd>{day(query.data?.data.summary.period ?? publication.latest_observation_date)}</dd>
    </dl>} />
    <p role="status" aria-live="polite" className="sr-only">{query.isFetching ? (query.data ? 'Updating range. Showing previous data until the selected range loads.' : 'Loading selected range…') : query.error ? 'Selected range could not load.' : 'Selected range loaded.'}</p>
    <div aria-busy={query.isFetching}>{query.isPending ? <div className={styles.firstSection}>{controls}<LoadingRows /></div> : query.error ? <div className={styles.firstSection}>{controls}<PageError error={query.error} busy={query.isFetching} onRetry={() => query.refetch({ cancelRefetch: false })} /></div> : <DashboardData key={query.data.data.publication.publication_event_id} data={query.data.data} updating={query.isFetching} controls={controls} onRestart={() => query.refetch({ cancelRefetch: false })} />}</div>
  </section>
}

/** The previous-day line under the selected observation (spec UF-D16). */
function previousLine(date: string, share: string | null | undefined, reason: string | null | undefined, current: string | null): string {
  if (share === null) return reason === 'zero_capacity' ? `Previous day (${shortDay(date)}): share unavailable, zero capacity.` : `Previous day (${shortDay(date)}) was not reported.`
  if (share === undefined) return 'Previous-day comparison unavailable.'
  const text = `${formatFixed(parseDecimal(share), 2)}%`
  if (current === null) return `Previous day (${shortDay(date)}): ${text}.`
  const change = subtract(parseDecimal(current), parseDecimal(share))
  const sign = compare(change, parseDecimal('0')) >= 0 ? '+' : ''
  return `Previous day (${shortDay(date)}): ${text} · change ${sign}${formatFixed(change, 2)} pts.`
}

function DashboardData({ data, updating, controls, onRestart }: { data: DashboardResponse; updating: boolean; controls: ReactNode; onRestart: () => unknown }) {
  const { me } = useSession(), [selected, setSelected] = useState<string | null>(null), [view, setView] = useState<'chart' | 'table'>('chart')
  const tabs = useId()
  const current = data.days.find((d) => d.period === selected) ?? data.summary
  const pinned = data.days.some((d) => d.period === selected)
  const previousDate = addDays(current.period, -1), previous = data.days.find((d) => d.period === previousDate)
  const metric = useQuery({ queryKey: [...queryKeys.metric(previousDate), updating], queryFn: ({ signal }) => getMetric(previousDate, signal), enabled: !updating && !previous })
  const previousShare = previous ? previous.offline_share_percent : metric.data?.data.publication.publication_event_id === data.publication.publication_event_id ? metric.data.data.metric.value : undefined
  const previousReason = previous ? previous.reason : metric.data?.data.metric.reason
  const summary = data.summary, share = summary.offline_share_percent
  const latest = summary.period === data.publication.latest_observation_date
  // Meter: the fill stops at the track end for a share above 100 (spec R25).
  const shareValue = share === null ? null : parseDecimal(share)
  const fill = shareValue === null || compare(shareValue, parseDecimal('0')) < 0 ? '0%' : compare(shareValue, parseDecimal('100')) > 0 ? '100%' : `${share}%`
  const inRange = shareValue !== null && !isOutOfRange(shareValue)
  return <>
    <Diagnostics diagnostics={data.diagnostics} />
    <section className={styles.firstSection} aria-label="Latest observation">
      <h2 className={styles.kpiHeading}>{latest ? 'Latest observation' : 'Range end observation'} · {day(summary.period)}</h2>
      <div className={styles.kpis}>
        <div className={styles.kpi}><span className={styles.kpiLabel}>Fleet offline</span><strong className={styles.hero}>{share === null ? <UnavailableValue /> : <CountValue value={share} percent />}</strong>{summary.reason && <span className={styles.kpiNote}>{summary.reason === 'zero_capacity' ? 'Capacity is 0 MW, so the share is unavailable.' : 'Not reported.'}</span>}</div>
        <div className={[styles.kpi, styles.kpiRule].join(' ')}><span className={styles.kpiLabel}>Reported outage</span><strong className={styles.kpiValue}><CountValue value={summary.outage} />{summary.outage !== null && <span className={styles.unit}> MW</span>}</strong></div>
        <div className={[styles.kpi, styles.kpiRule].join(' ')}><span className={styles.kpiLabel}>Reported capacity</span><strong className={styles.kpiValue}><CountValue value={summary.capacity} />{summary.capacity !== null && <span className={styles.unit}> MW</span>}</strong></div>
      </div>
      <div className={styles.meter} role="img" aria-label={share === null ? 'Offline share unavailable' : `Offline ${formatFixed(parseDecimal(share), 2)}% of reported capacity`}><span style={{ width: fill }} /></div>
      <div className={styles.meterLegend}>
        <span><i className={styles.swatchFill} />{share === null ? 'Unavailable' : `Offline ${formatFixed(parseDecimal(share), 2)}%`}</span>
        {inRange && shareValue !== null && summary.capacity !== null && summary.outage !== null && <span><i className={styles.swatchTrack} />Remaining reported capacity {formatFixed(subtract(parseDecimal('100'), shareValue), 2)}% · {formatExact(toText(subtract(parseDecimal(summary.capacity), parseDecimal(summary.outage))))} MW</span>}
      </div>
      <p className={styles.formula}>Offline share = reported outage ÷ reported capacity.</p>
    </section>
    <section className={sharedStyles.section}>
      <div className={sharedStyles.sectionHead}><h2 className={sharedStyles.sectionTitle}>Daily offline share</h2><Tabs label="Daily offline share view" idPrefix={tabs} tabs={[{ value: 'chart', label: 'Chart' }, { value: 'table', label: 'Daily values' }]} value={view} onChange={setView} /></div>
      {controls}
      <div id={`${tabs}-panel`} role="tabpanel" aria-labelledby={`${tabs}-tab-${view}`}>
        {view === 'table' ? <div className={styles.dailyScroll} tabIndex={0} role="region" aria-label="Daily values"><table className={styles.daily}><thead><tr><th>Day</th><th>Outage MW</th><th>Capacity MW</th><th>Offline share</th></tr></thead><tbody>{[...data.days].reverse().map((d) => <tr key={d.period} className={d.period === selected ? styles.pinnedRow : undefined} onClick={() => setSelected(d.period)}><td><TextButton className={styles.dayButton} onClick={(e) => { e.stopPropagation(); setSelected(d.period) }}>{day(d.period)}</TextButton>{d.period === summary.period && <Tag>Latest</Tag>}{d.period === selected && <Tag pinned>Pinned</Tag>}</td><td><Value value={d.outage} /></td><td><Value value={d.capacity} /></td><td>{d.offline_share_percent === null && d.reason === 'zero_capacity' ? <UnavailableValue /> : <Value value={d.offline_share_percent} percent />}</td></tr>)}</tbody></table></div> : <NationalChart days={data.days} selected={pinned ? selected : null} onSelect={setSelected} />}
      </div>
      <div className={styles.selected}>
        <div className={styles.selectedMain}>
          <div className={styles.selectedHead}><h3 className={styles.selectedTitle}>Selected observation · {day(current.period)}</h3><span className={pinned ? styles.badgePinned : styles.badgeLatest}>{pinned ? 'Pinned' : 'Latest observation'}</span></div>
          {current.offline_share_percent === null && current.outage === null ? <p className={styles.selectedMissing}>○ Not reported. No outage or capacity was published for this day.</p> : <div className={styles.selectedValues}>
            <span><span className="muted">Offline </span><b>{current.offline_share_percent === null ? 'Unavailable' : `${formatFixed(parseDecimal(current.offline_share_percent), 2)}%`}</b></span>
            <span><span className="muted">Outage </span><Value value={current.outage} /> MW</span>
            <span><span className="muted">Capacity </span><Value value={current.capacity} /> MW</span>
          </div>}
          {current.offline_share_percent !== null && isOutOfRange(parseDecimal(current.offline_share_percent)) && <p className={styles.selectedWarning}>! This value is outside 0–100. It was retained as published.</p>}
          {!updating && !previous && metric.error ? <PageError error={metric.error} busy={metric.isFetching} onRetry={() => metric.refetch({ cancelRefetch: false })} /> : <p className={styles.previous}>{previousLine(previousDate, previousShare, previousReason, current.offline_share_percent)}</p>}
        </div>
        <Button size="compact" disabled={!pinned} onClick={() => setSelected(null)}>Latest observation</Button>
      </div>
    </section>
    {me?.capabilities.includes('preview:detail') && <Contributions key={current.period} day={current} publication={data.publication.publication_event_id} updating={updating} onRestart={onRestart} />}
  </>
}
/** Finish pagination before ranking, and reject any mixed-publication response. */
async function allFacilities(period: string, publication: string, signal?: AbortSignal) {
  let cursor: string | undefined; let first: PreviewResponse | undefined; const rows: PreviewResponse['rows'] = []; const seen = new Set<string>()
  do {
    signal?.throwIfAborted()
    const result = (await getPreview('facility_outages', { start: period, end: period }, 1000, cursor, signal)).data
    if (result.publication.publication_event_id !== publication) throw new ApiError({ status: 409, code: 'publication_changed' })
    first ??= result; rows.push(...result.rows); cursor = result.next_cursor ?? undefined
    if (cursor && seen.has(cursor)) throw new Error('Invalid continuation')
    if (cursor) seen.add(cursor)
  } while (cursor)
  return { ...first, rows }
}
function Contributions({ day: observation, publication, updating, onRestart }: { day: NationalDay; publication: string; updating: boolean; onRestart: () => unknown }) {
  const [facility, setFacility] = useState<string | null>(null)
  // Keep previous contributions visible during range loading. Switching to
  // a disabled observer cancels its work; returning to the same day reuses
  // its completed publication-bound result without a competing read.
  const query = useQuery<Awaited<ReturnType<typeof allFacilities>>>({ queryKey: [...queryKeys.facilityDay(observation.period), publication, updating], enabled: !updating, staleTime: Infinity, placeholderData: (previous) => previous, queryFn: ({ signal }) => allFacilities(observation.period, publication, signal) })
  const spark = useQuery({ queryKey: [...queryKeys.facilitySpark(facility ?? '', observation.period), publication, updating], enabled: !updating && facility !== null, queryFn: async ({ signal }) => {
    const result = await getPreview('facility_outages', { start: addDays(observation.period, -7), end: observation.period, facility: facility ?? undefined }, 1000, undefined, signal)
    if (result.data.publication.publication_event_id !== publication) throw new ApiError({ status: 409, code: 'publication_changed' })
    return result
  } })
  const heading = <div className={styles.contribHead}><h2 className={sharedStyles.sectionTitle}>Facility outage contributions <span className={styles.contribDate}>{day(observation.period)}</span></h2></div>
  if (query.isPending) return <section className={sharedStyles.section}>{heading}<LoadingRows /></section>
  if (query.error) return <section className={sharedStyles.section}>{heading}<PageError error={query.error} busy={updating || query.isFetching} onRetry={isApiError(query.error, 'publication_changed') ? onRestart : () => query.refetch({ cancelRefetch: false })} /></section>
  const columns = query.data.columns, index = (key: string) => columns.findIndex((c) => c.name === key)
  const rows = [...query.data.rows].sort((a, b) => -compare(parseDecimal(a[index('outage')] as string), parseDecimal(b[index('outage')] as string)))
  const selected = rows.find((r) => r[index('facility')] === facility)
  const sparkData = spark.data?.data.publication.publication_event_id === publication ? spark.data.data : null
  const sparkDays = datesBetween(addDays(observation.period, -7), observation.period).map((period) => { const row = sparkData?.rows.find((r) => r[0] === period); return { period, outage: row?.[index('outage')] as string ?? null } })
  // Bars scale to the largest outage. Width is a CSS percent from exact decimals.
  const largest = rows.length ? parseDecimal(rows[0][index('outage')] as string) : parseDecimal('0')
  const width = (outage: string) => largest.units === 0n ? '0%' : `${formatFixed(scaleBy(parseDecimal(outage), 100n * 10n ** BigInt(largest.scale), largest.units), 2)}%`
  const total = formatExact(toText(sum(rows.map((r) => parseDecimal(r[index('outage')] as string)))))
  return <section className={sharedStyles.section}>{heading}<Diagnostics diagnostics={query.data.diagnostics} />
    {rows.length === 0 ? <div className={styles.contribEmpty}><EmptyState>No facility rows for {day(observation.period)}.</EmptyState></div> : <div className={styles.contribBody}>
      <div>
        <div className={styles.barHead}><span>Facility, ranked by reported outage</span><span>MW</span></div>
        {rows.map((row) => { const id = row[index('facility')] as string, outage = row[index('outage')] as string; return <button type="button" key={id} aria-pressed={id === facility} className={styles.barRow} onClick={() => setFacility(id)}><span className={styles.barName}>{row[index('facilityName')] ?? id}</span><span className={styles.barTrack}><span style={{ width: width(outage) }} /></span><span className={styles.barValue}>{formatExact(outage)}</span></button> })}
        <p className={styles.barNote}>{rows.length} facilities reported {total} MW on this day. The national outage is {observation.outage === null ? 'not reported' : `${formatExact(observation.outage)} MW`}. The two totals can differ.</p>
      </div>
      <div className={styles.detail}>
        {selected ? <>
          <span className={styles.detailLabel}>Facility detail · {day(observation.period)}</span>
          <h3 className={styles.detailName}>{selected[index('facilityName')] ?? facility}</h3>
          <p className={styles.detailLine}>{formatExact(selected[index('outage')] as string)} MW reported offline · <Share outage={selected[index('outage')]} capacity={selected[index('capacity')]} /> of {formatExact(selected[index('capacity')] as string)} MW</p>
          {spark.error && <PageError error={spark.error} busy={updating || spark.isFetching} onRetry={isApiError(spark.error, 'publication_changed') ? onRestart : () => spark.refetch({ cancelRefetch: false })} />}
          {sparkData && <Sparkline days={sparkDays} />}
          <div className={styles.detailLinks}><TextLink to={`/catalog/facility_outages?facility=${encodeURIComponent(facility ?? '')}`}>Open in facility_outages →</TextLink><TextLink to={`/catalog/generator_outages?facility=${encodeURIComponent(facility ?? '')}`}>View generators →</TextLink></div>
        </> : <p className={styles.detailHint}>Select a facility to see its last eight days.</p>}
      </div>
    </div>}
  </section>
}
