import { useEffect, useId, useMemo, useState } from 'react'
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { useParams, useSearchParams } from 'react-router'
import { getCatalog, getPreview, type PreviewFilters } from '../../api/endpoints'
import { isApiError } from '../../api/client'
import { DATASET_KEYS, type DatasetKey } from '../../api/types'
import { queryKeys } from '../../api/queryKeys'
import { Button, TextLink } from '../../components/controls/Button'
import { Field, filterInputClass } from '../../components/controls/Field'
import { PageHeader } from '../../components/layout/PageHeader'
import { Callout } from '../../components/feedback/Callout'
import { ShortId } from '../../components/controls/ShortId'
import { EmptyState, LoadingRows } from '../../components/feedback/States'
import { combinedShare, formatExact, formatFixed, parseDecimal, sum, toText } from '../../lib/decimal'
import { FacilityChoices, GeneratorChoices } from './Choices'
import { DataTable, Diagnostics, PageError } from '../shared'
import styles from './Catalog.module.css'

export function TableView() {
  const { datasetKey } = useParams()
  if (!DATASET_KEYS.includes(datasetKey as DatasetKey)) return <section><PageHeader breadcrumb={<TextLink to="/catalog">← Catalog</TextLink>} title="Dataset not found" /><div className={styles.body}><EmptyState>Dataset not found. This dataset does not exist or is not available to your account.</EmptyState></div></section>
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
  // The combined share sums outage and capacity over the loaded rows, then
  // divides once (spec R38). A missing value makes the sum incomplete.
  let combined = 'Combined offline share for these rows: unavailable.'
  if (first && rows.length) {
    const oi = first.columns.findIndex((c) => c.name === 'outage'), ci = first.columns.findIndex((c) => c.name === 'capacity')
    const missing = rows.filter((r) => typeof r[oi] !== 'string' || typeof r[ci] !== 'string').length
    if (missing) combined = `Combined offline share for these rows: unavailable. ${missing} ${missing === 1 ? 'row is' : 'rows are'} not reported, so the sum is incomplete.`
    else {
      const outages = rows.map((r) => parseDecimal(r[oi] as string)), capacities = rows.map((r) => parseDecimal(r[ci] as string))
      const total = combinedShare(outages, capacities)
      if (total.kind === 'value') combined = `Combined offline share for these rows: ${formatExact(toText(sum(outages)))} MW ÷ ${formatExact(toText(sum(capacities)))} MW = ${formatFixed(total.value, 2)}% (summed outage ÷ summed capacity).`
    }
  }
  return <section>
    <PageHeader breadcrumb={<><TextLink to="/catalog">Catalog</TextLink><span>/</span><span className={styles.crumbCurrent}>{datasetKey}</span></>} title={dataset?.label ?? datasetKey}
      subtitle={<>{dataset?.description}{first && <> Rows from <ShortId value={first.publication.version_id} />.</>} Filters stay on this page.</>} />
    <div className={styles.filters}>
      <Field label="From" compact><input className={filterInputClass} type="date" value={dates.start} onChange={(e) => setDates({ ...dates, start: e.target.value })} /></Field>
      <Field label="To" compact><input className={filterInputClass} type="date" value={dates.end} onChange={(e) => setDates({ ...dates, end: e.target.value })} /></Field>
      <Button size="compact" onClick={applyDates}>Apply dates</Button>
      {datasetKey !== 'national_outages' && <FacilityChoices key={`${reset}:${filters.start}:${filters.end}`} busy={query.isFetching} dataset={datasetKey} filters={filters} onChange={(facility) => update({ ...filters, facility, generator: undefined })} />}
      {datasetKey === 'generator_outages' && <GeneratorChoices key={`${reset}:${filters.start}:${filters.end}:${filters.facility}`} busy={query.isFetching} filters={filters} onChange={(generator) => update({ ...filters, generator })} />}
      <Button size="compact" onClick={resetFilters}>Reset filters</Button>
      <span className={styles.spacer} />
      {first && !mixed && <span className={styles.count}>{rows.length} rows</span>}
    </div>
    {notice && <div className={styles.notice}><Callout tone="info">{notice}</Callout></div>}
    <div className={styles.body}>
      {query.isPending && <LoadingRows />}{query.error && (!query.data?.pages.length || !isApiError(query.error, 'publication_changed')) && <PageError error={query.error} busy={query.isFetching} onRetry={() => query.refetch({ cancelRefetch: false })} />}
      {mixed ? <div role="status" className={styles.footerActions}><Callout tone="warning">The data changed.</Callout><Button size="compact" onClick={() => { setLoadAll(false); void cache.resetQueries({ queryKey: key, exact: true }) }}>Reload table</Button></div> : first && <div><Diagnostics diagnostics={first.diagnostics} />{rows.length ? <DataTable columns={first.columns} rows={rows} /> : <EmptyState>No rows match these filters.</EmptyState>}
        <div className={styles.footer}>
          {query.hasNextPage ? <><p>Showing {rows.length} rows. Load all rows to calculate the combined share.</p><div className={styles.footerActions}><Button size="compact" disabled={query.isFetching} onClick={() => { void query.fetchNextPage() }}>Load more</Button><Button size="compact" disabled={loadAll || query.isFetching} onClick={() => setLoadAll(true)}>{loadAll ? 'Loading all rows…' : 'Load all rows'}</Button></div></> : rows.length > 0 && <p>{combined}</p>}
          <p className={styles.legend}>○ Not reported means no value was published for that day. 0 means the day was reported as zero.</p>
        </div></div>}
    </div>
  </section>
}
