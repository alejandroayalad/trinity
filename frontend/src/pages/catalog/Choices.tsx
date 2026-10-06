import { useState } from 'react'
import { useInfiniteQuery } from '@tanstack/react-query'
import type { DatasetKey } from '../../api/types'
import { getFacilities, getGenerators, type PreviewFilters } from '../../api/endpoints'
import { Button } from '../../components/controls/Button'
import { PageError } from '../shared'

export function FacilityChoices({ dataset, filters, onChange }: { dataset: DatasetKey; filters: PreviewFilters; onChange: (facility: string | undefined) => void }) {
  const [search, setSearch] = useState('')
  // The facility list is large. Its first page loads only when the user first
  // opens the search box or the select. A linked facility ID stays visible
  // through the fallback option below even before the list arrives.
  const [opened, setOpened] = useState(false)
  const query = useInfiniteQuery({ queryKey: ['facilities', dataset, filters.start, filters.end, search], initialPageParam: undefined as string | undefined, enabled: opened,
    queryFn: ({ pageParam, signal }) => getFacilities(dataset, filters, search, pageParam, signal), getNextPageParam: (last) => last.data.next_cursor ?? undefined })
  const options = query.data?.pages.flatMap((p) => p.data.items) ?? []
  const first = query.data?.pages[0].data.publication.publication_event_id
  const mixed = query.data?.pages.some((p) => p.data.publication.publication_event_id !== first)
  return <div className="stack"><label>Search facilities<input type="search" maxLength={100} value={search} onFocus={() => setOpened(true)} onChange={(e) => setSearch(e.target.value)} /></label><label>Facility<select value={filters.facility ?? ''} onFocus={() => setOpened(true)} onMouseDown={() => setOpened(true)} onChange={(e) => onChange(e.target.value || undefined)}><option value="">All facilities</option>{filters.facility && !options.some((o) => o.facility === filters.facility) && <option value={filters.facility}>{filters.facility}</option>}{!mixed && options.map((o) => <option key={o.facility} value={o.facility}>{o.facilityName ?? o.facility} ({o.facility})</option>)}</select></label>
    {query.error && <PageError error={query.error} onRetry={() => void query.refetch()} />}{mixed && <p>Data changed. Search again to reload choices.</p>}{query.hasNextPage && <Button disabled={query.isFetching} onClick={() => { void query.fetchNextPage() }}>More facilities</Button>}</div>
}
export function GeneratorChoices({ filters, onChange }: { filters: PreviewFilters; onChange: (generator: string | undefined) => void }) {
  const query = useInfiniteQuery({ queryKey: ['generators', filters.start, filters.end, filters.facility], enabled: !!filters.facility, initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) => getGenerators('generator_outages', filters, pageParam, signal), getNextPageParam: (last) => last.data.next_cursor ?? undefined })
  const first = query.data?.pages[0].data.publication.publication_event_id
  const mixed = query.data?.pages.some((p) => p.data.publication.publication_event_id !== first)
  return <div className="stack"><label>Generator<select disabled={!filters.facility} value={filters.generator ?? ''} onChange={(e) => onChange(e.target.value || undefined)}><option value="">All generators</option>{!mixed && query.data?.pages.flatMap((p) => p.data.items).map((o) => <option key={o.generator} value={o.generator}>{o.generator}</option>)}</select></label>{query.error && <PageError error={query.error} onRetry={() => void query.refetch()} />}{mixed && <p>Data changed. Reload generator choices.</p>}{query.hasNextPage && <Button disabled={query.isFetching} onClick={() => { void query.fetchNextPage() }}>More generators</Button>}</div>
}
