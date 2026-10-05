import { useEffect, useMemo, useState } from 'react'
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
  const [filters, setFilters] = useState<PreviewFilters>(() => search.has('facility') ? { facility: search.get('facility') ?? '' } : cache.getQueryData<PreviewFilters>(['filters', datasetKey]) ?? {})
  const [notice, setNotice] = useState('')
  const [loadAll, setLoadAll] = useState(false)
  const catalog = useQuery({ queryKey: queryKeys.catalog, queryFn: getCatalog })
  const key = useMemo(() => queryKeys.preview(datasetKey, filters), [datasetKey, filters])
  const query = useInfiniteQuery({ queryKey: key, initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => getPreview(datasetKey, filters, 1000, pageParam),
    getNextPageParam: (last) => last.data.next_cursor ?? undefined })
  const update = (next: PreviewFilters) => { setLoadAll(false); setFilters(next); cache.setQueryData(['filters', datasetKey], next) }
  useEffect(() => {
    if (isApiError(query.error, 'publication_changed')) {
      const timer = window.setTimeout(() => {
        setNotice('The data was updated. The table restarted from the first page.')
        setLoadAll(false)
        void cache.resetQueries({ queryKey: key, exact: true })
      }, 0)
      return () => window.clearTimeout(timer)
    }
  }, [query.error, cache, key])
  useEffect(() => {
    if (loadAll && query.hasNextPage && !query.isFetching && !query.error) void query.fetchNextPage()
  }, [loadAll, query])
  const pages = query.data?.pages.map((p) => p.data) ?? []
  const first = pages[0]
  // Never render a mixed-publication table, including after background refresh.
  const mixed = pages.some((p) => p.publication.publication_event_id !== first?.publication.publication_event_id)
  const rows = mixed ? [] : pages.flatMap((p) => p.rows)
  const dataset = catalog.data?.data.datasets.find((d) => d.key === datasetKey)
  const field = (name: keyof PreviewFilters, label: string, disabled = false) => <label>{label}<input type={name === 'start' || name === 'end' ? 'date' : 'text'} disabled={disabled} value={filters[name] ?? ''} onChange={(e) => update({ ...filters, [name]: e.target.value === '' ? undefined : e.target.value, ...(name === 'facility' ? { generator: undefined } : {}) })} /></label>
  let combined = 'Unavailable'
  if (first && rows.length) {
    const oi = first.columns.findIndex((c) => c.name === 'outage'), ci = first.columns.findIndex((c) => c.name === 'capacity')
    const complete = rows.every((r) => typeof r[oi] === 'string' && typeof r[ci] === 'string')
    if (complete) { const total = combinedShare(rows.map((r) => parseDecimal(r[oi] as string)), rows.map((r) => parseDecimal(r[ci] as string))); if (total.kind === 'value') combined = `${formatFixed(total.value, 2)}%` }
  }
  return <section className="stack"><Link to="/catalog">← Catalog</Link><h1 className="mono">{datasetKey}</h1><p>{dataset?.label}</p>
    {first && <p className="row">Rows from <ShortId value={first.publication.version_id} />.</p>}
    <div className="panel filters">{field('start', 'From')}{field('end', 'To')}{datasetKey !== 'national_outages' && <FacilityChoices dataset={datasetKey} filters={filters} onChange={(facility) => update({ ...filters, facility, generator: undefined })} />}{datasetKey === 'generator_outages' && <GeneratorChoices filters={filters} onChange={(generator) => update({ ...filters, generator })} />}<Button onClick={() => update({})}>Reset filters</Button></div>
    {notice && <p role="status">{notice}</p>}{query.isPending && <LoadingRows />}{query.error && !isApiError(query.error, 'publication_changed') && <PageError error={query.error} />}
    {mixed ? <div role="status">The data changed. <Button onClick={() => { void cache.resetQueries({ queryKey: key, exact: true }) }}>Reload table</Button></div> : first && <div className="panel stack"><Diagnostics diagnostics={first.diagnostics} />{rows.length ? <DataTable columns={first.columns} rows={rows} /> : <p className="empty">No rows match these filters.</p>}
    {query.hasNextPage ? <><p>Showing {rows.length} rows. Load all rows to calculate the combined share.</p><div className="row"><Button disabled={query.isFetching} onClick={() => { void query.fetchNextPage() }}>Load more</Button><Button disabled={loadAll} onClick={() => setLoadAll(true)}>{loadAll ? 'Loading all rows…' : 'Load all rows'}</Button></div></> : <p>{rows.length} rows · Combined share: {combined}</p>}<p className="muted">○ Not reported means missing. 0 is a reported value.</p></div>}
  </section>
}
