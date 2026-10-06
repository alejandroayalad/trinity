import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router'
import { getDashboard, getMetric, getPreview } from '../../api/endpoints'
import { queryKeys } from '../../api/queryKeys'
import type { DashboardResponse, NationalDay, PreviewResponse } from '../../api/types'
import { useSession } from '../../session/SessionProvider'
import { useReducedMotion } from '../../lib/useReducedMotion'
import { Button } from '../../components/controls/Button'
import { MissingChip } from '../../components/feedback/StatusBadge'
import { LoadingRows } from '../../components/feedback/States'
import { addDays, datesBetween, daysInclusive, isDateText } from '../../lib/dates'
import { compare, formatExact, formatFixed, isOutOfRange, parseDecimal, scaleBy, subtract, sum, toText } from '../../lib/decimal'
import { Diagnostics, PageError, Share } from '../shared'
import { Sparkline } from './Sparkline'
import { NationalChart } from './NationalChart'

function Value({ value, percent = false }: { value: string | null; percent?: boolean }) {
  if (value === null) return <MissingChip />
  return <>{percent ? `${formatFixed(parseDecimal(value), 2)}%` : formatExact(value)}{percent && isOutOfRange(parseDecimal(value)) && <span> ⚠ Out of range</span>}</>
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
export function Dashboard() {
  const [range, setRange] = useState<{ preset?: string; start?: string; end?: string }>({ preset: '30d' })
  const [custom, setCustom] = useState(false), [start, setStart] = useState(''), [end, setEnd] = useState('')
  const query = useQuery({ queryKey: queryKeys.dashboard(JSON.stringify(range)), queryFn: ({ signal }) => getDashboard(range, signal), placeholderData: (previous) => previous })
  const valid = isDateText(start) && isDateText(end) && daysInclusive(start, end) > 0 && daysInclusive(start, end) <= 366
  return <section className="stack"><div><h1>National overview</h1><p className="muted">U.S. nuclear outages · Published observations</p></div><div className="row">{([['30d', '30 days'], ['90d', '90 days'], ['1y', 'Last 365 days']] as const).map(([preset, label]) => <Button key={preset} variant={range.preset === preset ? 'primary' : 'secondary'} onClick={() => { setCustom(false); setRange({ preset }) }}>{label}</Button>)}<Button onClick={() => setCustom(true)}>Custom range</Button></div>
    {custom && <form className="filters" onSubmit={(e) => { e.preventDefault(); if (valid) setRange({ start, end }) }}><label>From<input type="date" value={start} onChange={(e) => setStart(e.target.value)} /></label><label>To<input type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></label><Button type="submit" disabled={!valid}>Apply range</Button><p>Up to 366 dates.</p></form>}
    {query.isPending ? <LoadingRows /> : query.error ? <PageError error={query.error} onRetry={() => void query.refetch()} /> : <DashboardData key={query.data.data.publication.publication_event_id} data={query.data.data} />}
  </section>
}
function DashboardData({ data }: { data: DashboardResponse }) {
  const { me } = useSession(), [selected, setSelected] = useState<string | null>(null), [table, setTable] = useState(false)
  const day = data.days.find((d) => d.period === selected) ?? data.summary
  const previousDate = addDays(day.period, -1), previous = data.days.find((d) => d.period === previousDate)
  const metric = useQuery({ queryKey: queryKeys.metric(previousDate), queryFn: ({ signal }) => getMetric(previousDate, signal), enabled: !previous })
  const previousShare = previous ? previous.offline_share_percent : metric.data?.data.publication.publication_event_id === data.publication.publication_event_id ? metric.data.data.metric.value : undefined
  const previousReason = previous ? previous.reason : metric.data?.data.metric.reason
  return <><Diagnostics diagnostics={data.diagnostics} /><h2>Range end observation · {data.summary.period}</h2><div className="kpis"><div className="panel stack"><p>Offline share</p><strong className="hero-value"><CountValue value={data.summary.offline_share_percent} percent /></strong>{data.summary.reason && <p>{data.summary.reason === 'zero_capacity' ? 'Unavailable: zero capacity' : 'Not reported'}</p>}<div className="meter" role="img" aria-label={`Offline share: ${data.summary.offline_share_percent ?? 'Unavailable'}${data.summary.offline_share_percent === null ? '' : '%'}`}><span style={{ width: data.summary.offline_share_percent === null ? '0%' : `${data.summary.offline_share_percent}%` }} /></div></div><div className="panel stack"><p>Outage MW</p><strong className="kpi-value"><CountValue value={data.summary.outage} /></strong></div><div className="panel stack"><p>Capacity MW</p><strong className="kpi-value"><CountValue value={data.summary.capacity} /></strong></div></div>
    <div className="panel stack"><div className="row spread"><h2>Offline share over time</h2><div className="row"><Button onClick={() => setTable(false)}>Chart</Button><Button onClick={() => setTable(true)}>Daily values</Button></div></div>
    {table ? <div className="table-scroll"><table><thead><tr><th>Day</th><th>Outage MW</th><th>Capacity MW</th><th>Offline share</th></tr></thead><tbody>{data.days.map((d) => <tr key={d.period}><td><Button onClick={() => setSelected(d.period)}>{d.period}</Button></td><td><Value value={d.outage} /></td><td><Value value={d.capacity} /></td><td><Value value={d.offline_share_percent} percent /></td></tr>)}</tbody></table></div> : <NationalChart days={data.days} selected={data.days.some((d) => d.period === selected) ? selected : null} onSelect={setSelected} />}</div>
    <div className="panel stack"><div className="row spread"><h2>Selected observation · {day.period}</h2>{selected && <Button onClick={() => setSelected(null)}>Clear pin</Button>}</div><p>Outage: <Value value={day.outage} /> MW · Capacity: <Value value={day.capacity} /> MW · Share: <Value value={day.offline_share_percent} percent /></p>
      {previousShare === null ? <p>{previousReason === 'zero_capacity' ? `Previous-day share (${previousDate}) is unavailable: zero capacity.` : `Previous day (${previousDate}) was not reported.`}</p> : previousShare !== undefined && day.offline_share_percent !== null ? <p>Change from {previousDate}: {formatFixed(subtract(parseDecimal(day.offline_share_percent), parseDecimal(previousShare)), 2)} percentage points</p> : <p>Previous-day comparison unavailable.</p>}
    </div>{me?.capabilities.includes('preview:detail') && <Contributions key={day.period} day={day} publication={data.publication.publication_event_id} />}</>
}
/** Finish pagination before ranking, and reject any mixed-publication response. */
async function allFacilities(period: string, publication: string, signal?: AbortSignal) {
  let cursor: string | undefined; let first: PreviewResponse | undefined; const rows: PreviewResponse['rows'] = []; const seen = new Set<string>()
  do {
    const result = (await getPreview('facility_outages', { start: period, end: period }, 1000, cursor, signal)).data
    if (result.publication.publication_event_id !== publication) throw new Error('Publication changed')
    first ??= result; rows.push(...result.rows); cursor = result.next_cursor ?? undefined
    if (cursor && seen.has(cursor)) throw new Error('Invalid continuation')
    if (cursor) seen.add(cursor)
  } while (cursor)
  return { ...first, rows }
}
function Contributions({ day, publication }: { day: NationalDay; publication: string }) {
  const [facility, setFacility] = useState<string | null>(null)
  const query = useQuery({ queryKey: [...queryKeys.facilityDay(day.period), publication], queryFn: ({ signal }) => allFacilities(day.period, publication, signal) })
  const spark = useQuery({ queryKey: [...queryKeys.facilitySpark(facility ?? '', day.period), publication], enabled: facility !== null, queryFn: ({ signal }) => getPreview('facility_outages', { start: addDays(day.period, -7), end: day.period, facility: facility ?? undefined }, 1000, undefined, signal) })
  if (query.isPending) return <LoadingRows />
  if (query.error) return <PageError error={query.error} onRetry={() => void query.refetch()} />
  const columns = query.data.columns, index = (key: string) => columns.findIndex((c) => c.name === key)
  const rows = [...query.data.rows].sort((a, b) => -compare(parseDecimal(a[index('outage')] as string), parseDecimal(b[index('outage')] as string)))
  const selected = rows.find((r) => r[index('facility')] === facility)
  const sparkData = spark.data?.data.publication.publication_event_id === publication ? spark.data.data : null
  const sparkDays: NationalDay[] = datesBetween(addDays(day.period, -7), day.period).map((period) => { const row = sparkData?.rows.find((r) => r[0] === period); return { period, capacity: row?.[index('capacity')] as string ?? null, outage: row?.[index('outage')] as string ?? null, percentOutage: null, offline_share_percent: row?.[index('outage')] as string ?? null, reason: row ? null : 'not_reported' } })
  return <section className="panel stack"><h2>Reported facility contributions · {day.period}</h2><p>Facility total: {formatExact(toText(sum(rows.map((r) => parseDecimal(r[index('outage')] as string)))))} MW · National outage: <Value value={day.outage} /> MW</p><p className="muted">These source totals can differ. Only reported facilities are listed.</p><Diagnostics diagnostics={query.data.diagnostics} />
    {rows.map((row) => <div className="row spread" key={row[index('facility')] as string}><Button onClick={() => setFacility(row[index('facility')] as string)}>{row[index('facilityName')] ?? row[index('facility')]}</Button><span><Value value={row[index('outage')] as string} /> MW</span></div>)}
    {selected && <div className="stack"><h3>{selected[index('facilityName')] ?? facility}</h3><p>Capacity: <Value value={selected[index('capacity')] as string} /> MW · Offline share: <Share outage={selected[index('outage')]} capacity={selected[index('capacity')]} /></p>{spark.error && <PageError error={spark.error} onRetry={() => void spark.refetch()} />}{sparkData && <Sparkline days={sparkDays} />}<Link to={`/catalog/facility_outages?facility=${encodeURIComponent(facility ?? '')}`}>Open facility table</Link><Link to={`/catalog/generator_outages?facility=${encodeURIComponent(facility ?? '')}`}>Open generator table</Link></div>}
  </section>
}
