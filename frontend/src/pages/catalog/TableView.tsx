import { useEffect, useId, useMemo, useState } from 'react'
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams, useSearchParams } from 'react-router'
import { getCatalog, getPreview, type PreviewFilters } from '../../api/endpoints'
import { isApiError } from '../../api/client'
import { DATASET_KEYS, type DatasetKey } from '../../api/types'
import { queryKeys } from '../../api/queryKeys'
import { Button } from '../../components/controls/Button'
import { ShortId } from '../../components/controls/ShortId'
import { LoadingRows } from '../../components/feedback/States'
import { combinedShare, formatFixed, parseDecimal } from '../../lib/decimal'
import { FacilityChoices, GeneratorChoices } from './Choices'
import { DataTable, Diagnostics, PageError } from '../shared'

export function TableView() {
  const { datasetKey } = useParams()
  if (!DATASET_KEYS.includes(datasetKey as DatasetKey)) return <p>Dataset not found.</p>
  return <DatasetTable key={datasetKey} datasetKey={datasetKey as DatasetKey} />
}
function DatasetTable({ datasetKey }: { datasetKey: DatasetKey }) {
  const cache = useQueryClient()
  const [search] = useSearchParams()
  // This non-fetch cache entry belongs to the session and clears on sign-out.
  const [filters, setFilters] = useState<PreviewFilters>(() => search.has('facility') ? { facility: search.get('facility') ?? '', ...(datasetKey === 'generator_outages' && search.has('generator') ? { generator: search.get('generator') ?? '' } : {}) } : cache.getQueryData<PreviewFilters>(['filters', datasetKey]) ?? {})
  // From and To are a draft. The table fetches only when the user clicks
  // "Apply dates", so fast typing sends no preview requests.
  const [dates, setDates] = useState(() => ({ start: filters.start ?? '', end: filters.end ?? '' }))
  const [notice, setNotice] = useState('')
  const [loadAll, setLoadAll] = useState(false)
  const visitId = useId()
  const [visit, setVisit] = useState(0)
  const [reset, setReset] = useState(0)
  const catalog = useQuery({ queryKey: queryKeys.catalog, queryFn: getCatalog })
  const key = useMemo(() => [...queryKeys.preview(datasetKey, filters), visitId, visit], [datasetKey, filters, visitId, visit])
  const query = useInfiniteQuery({ queryKey: key, initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) => getPreview(datasetKey, filters, 1000, pageParam, signal),
    getNextPageParam: (last) => last.data.next_cursor ?? undefined })
  // Each explicit filter visit owns a new cursor chain. Keep other cached
  // datasets and saved filters intact, including browser-history navigation.
  const update = (next: PreviewFilters) => {
    void cache.cancelQueries({ queryKey: key, exact: true })
    setLoadAll(false); setVisit((value) => value + 1)
    setFilters(next); cache.setQueryData(['filters', datasetKey], next)
  }
  const applyDates = () => {
    const start = dates.start || undefined, end = dates.end || undefined
    if (start !== filters.start || end !== filters.end) update({ ...filters, start, end })
  }
  const resetFilters = () => { setDates({ start: '', end: '' }); setReset((value) => value + 1); update({}) }
  useEffect(() => {
    if (query.data?.pages.length && isApiError(query.error, 'publication_changed')) {
      const timer = window.setTimeout(() => {
        setNotice('The data was updated. The table restarted from the first page.')
        setLoadAll(false)
        void cache.resetQueries({ queryKey: key, exact: true })
      }, 0)
      return () => window.clearTimeout(timer)
    }
  }, [query.error, query.data?.pages.length, cache, key])
  const pages = query.data?.pages.map((p) => p.data) ?? []
  const first = pages[0]
  // Never render a mixed-publication table, including after background refresh.
  const mixed = pages.some((p) => p.publication.publication_event_id !== first?.publication.publication_event_id)
  useEffect(() => {
    if (loadAll && !mixed && query.hasNextPage && !query.isFetching && !query.error) void query.fetchNextPage()
  }, [loadAll, mixed, query])
  const rows = mixed ? [] : pages.flatMap((p) => p.rows)
  const dataset = catalog.data?.data.datasets.find((d) => d.key === datasetKey)
  let combined = 'Unavailable'
  if (first && rows.length) {
    const oi = first.columns.findIndex((c) => c.name === 'outage'), ci = first.columns.findIndex((c) => c.name === 'capacity')
    const complete = rows.every((r) => typeof r[oi] === 'string' && typeof r[ci] === 'string')
    if (complete) { const total = combinedShare(rows.map((r) => parseDecimal(r[oi] as string)), rows.map((r) => parseDecimal(r[ci] as string))); if (total.kind === 'value') combined = `${formatFixed(total.value, 2)}%` }
  }
  return <section className="stack"><Link to="/catalog">← Catalog</Link><h1 className="mono">{datasetKey}</h1><p>{dataset?.label}</p>
    {first && <p className="row">Rows from <ShortId value={first.publication.version_id} />.</p>}
    <div className="panel filters"><label>From<input type="date" value={dates.start} onChange={(e) => setDates({ ...dates, start: e.target.value })} /></label><label>To<input type="date" value={dates.end} onChange={(e) => setDates({ ...dates, end: e.target.value })} /></label><Button onClick={applyDates}>Apply dates</Button>{datasetKey !== 'national_outages' && <FacilityChoices key={`${reset}:${filters.start}:${filters.end}`} busy={query.isFetching} dataset={datasetKey} filters={filters} onChange={(facility) => update({ ...filters, facility, generator: undefined })} />}{datasetKey === 'generator_outages' && <GeneratorChoices key={`${reset}:${filters.start}:${filters.end}:${filters.facility}`} busy={query.isFetching} filters={filters} onChange={(generator) => update({ ...filters, generator })} />}<Button onClick={resetFilters}>Reset filters</Button></div>
    {notice && <p role="status">{notice}</p>}{query.isPending && <LoadingRows />}{query.error && (!query.data?.pages.length || !isApiError(query.error, 'publication_changed')) && <PageError error={query.error} busy={query.isFetching} onRetry={() => query.refetch({ cancelRefetch: false })} />}
    {mixed ? <div role="status">The data changed. <Button onClick={() => { setLoadAll(false); void cache.resetQueries({ queryKey: key, exact: true }) }}>Reload table</Button></div> : first && <div className="panel stack"><Diagnostics diagnostics={first.diagnostics} />{rows.length ? <DataTable columns={first.columns} rows={rows} /> : <p className="empty">No rows match these filters.</p>}
    {query.hasNextPage ? <><p>Showing {rows.length} rows. Load all rows to calculate the combined share.</p><div className="row"><Button disabled={query.isFetching} onClick={() => { void query.fetchNextPage() }}>Load more</Button><Button disabled={loadAll || query.isFetching} onClick={() => setLoadAll(true)}>{loadAll ? 'Loading all rows…' : 'Load all rows'}</Button></div></> : <p>{rows.length} rows · Combined share: {combined}</p>}<p className="muted">○ Not reported means missing. 0 is a reported value.</p></div>}
  </section>
}
