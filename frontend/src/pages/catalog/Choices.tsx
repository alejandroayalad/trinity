import { useEffect, useId, useState } from 'react'
import { useInfiniteQuery, useQueryClient, type QueryKey } from '@tanstack/react-query'
import type { DatasetKey } from '../../api/types'
import { isApiError } from '../../api/client'
import { getFacilities, getGenerators, type PreviewFilters } from '../../api/endpoints'
import { Button } from '../../components/controls/Button'
import { PageError } from '../shared'

// Wait for a short pause in typing. Changing the draft immediately detaches
// the old observer, so an old response cannot populate the current choices.
export const FACILITY_SEARCH_DELAY_MS = 300

// Only a failed continuation restarts automatically. A first-page failure
// stays manual, so a persistent publication error cannot create a retry loop.
function useChoiceRestart(error: unknown, mixed: boolean, hasPages: boolean, key: QueryKey) {
  const cache = useQueryClient()
  useEffect(() => {
    if (!mixed && !(hasPages && isApiError(error, 'publication_changed'))) return
    const timer = window.setTimeout(() => { void cache.resetQueries({ queryKey: key, exact: true }) }, 0)
    return () => window.clearTimeout(timer)
  }, [cache, error, mixed, hasPages, key])
}

export function FacilityChoices({ dataset, filters, onChange, busy = false }: { dataset: DatasetKey; filters: PreviewFilters; onChange: (facility: string | undefined) => void; busy?: boolean }) {
  const [search, setSearch] = useState('')
  const [settled, setSettled] = useState('')
  const [visit, setVisit] = useState(0)
  const instance = useId()
  // Reset remounts this control. It closes the list and clears this timer.
  // Linked IDs remain visible before the user opens the choices.
  const [opened, setOpened] = useState(false)
  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(search), FACILITY_SEARCH_DELAY_MS)
    return () => window.clearTimeout(timer)
  }, [search])
  // A cached choice page stays valid within this visit. Preview activity must
  // not refetch it merely because the control becomes enabled again.
  const key = ['facilities', dataset, filters.start, filters.end, search, instance, visit]
  const query = useInfiniteQuery({ queryKey: key, staleTime: Infinity, initialPageParam: undefined as string | undefined, enabled: opened && !busy && search === settled,
    queryFn: ({ pageParam, signal }) => getFacilities(dataset, filters, search, pageParam, signal), getNextPageParam: (last) => last.data.next_cursor ?? undefined })
  const first = query.data?.pages[0].data.publication.publication_event_id
  const mixed = query.data?.pages.some((p) => p.data.publication.publication_event_id !== first) ?? false
  useChoiceRestart(query.error, mixed, !!query.data?.pages.length, key)
  const options = mixed || search !== settled ? [] : query.data?.pages.flatMap((p) => p.data.items) ?? []
  return <div className="stack"><label>Search facilities<input type="search" maxLength={100} value={search} onFocus={() => setOpened(true)} onChange={(e) => { setSearch(e.target.value); setVisit((value) => value + 1) }} /></label><label>Facility<select value={filters.facility ?? ''} onFocus={() => setOpened(true)} onMouseDown={() => setOpened(true)} onChange={(e) => onChange(e.target.value || undefined)}><option value="">All facilities</option>{filters.facility && !options.some((o) => o.facility === filters.facility) && <option value={filters.facility}>{filters.facility}</option>}{options.map((o) => <option key={o.facility} value={o.facility}>{o.facilityName ?? o.facility} ({o.facility})</option>)}</select></label>
    {query.error && (!query.data?.pages.length || !isApiError(query.error, 'publication_changed')) && <PageError error={query.error} busy={busy || query.isFetching} onRetry={() => query.refetch({ cancelRefetch: false })} />}{(mixed || (!!query.data?.pages.length && isApiError(query.error, 'publication_changed'))) && <p role="status">Data changed. Restarting choices.</p>}{query.hasNextPage && <Button disabled={busy || query.isFetching} onClick={() => { void query.fetchNextPage() }}>More facilities</Button>}</div>
}
export function GeneratorChoices({ filters, onChange, busy = false }: { filters: PreviewFilters; onChange: (generator: string | undefined) => void; busy?: boolean }) {
  const instance = useId()
  const [opened, setOpened] = useState(false)
  const key = ['generators', filters.start, filters.end, filters.facility, instance]
  const query = useInfiniteQuery({ queryKey: key, staleTime: Infinity, enabled: opened && !!filters.facility && !busy, initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) => getGenerators('generator_outages', filters, pageParam, signal), getNextPageParam: (last) => last.data.next_cursor ?? undefined })
  const first = query.data?.pages[0].data.publication.publication_event_id
  const mixed = query.data?.pages.some((p) => p.data.publication.publication_event_id !== first) ?? false
  useChoiceRestart(query.error, mixed, !!query.data?.pages.length, key)
  const options = mixed ? [] : query.data?.pages.flatMap((p) => p.data.items) ?? []
  return <div className="stack"><label>Generator<select disabled={!filters.facility} value={filters.generator ?? ''} onFocus={() => setOpened(true)} onMouseDown={() => setOpened(true)} onChange={(e) => onChange(e.target.value || undefined)}><option value="">All generators</option>{filters.generator && !options.some((o) => o.generator === filters.generator) && <option value={filters.generator}>{filters.generator}</option>}{options.map((o) => <option key={o.generator} value={o.generator}>{o.generator}</option>)}</select></label>{query.error && (!query.data?.pages.length || !isApiError(query.error, 'publication_changed')) && <PageError error={query.error} busy={busy || query.isFetching} onRetry={() => query.refetch({ cancelRefetch: false })} />}{(mixed || (!!query.data?.pages.length && isApiError(query.error, 'publication_changed'))) && <p role="status">Data changed. Restarting choices.</p>}{query.hasNextPage && <Button disabled={busy || query.isFetching} onClick={() => { void query.fetchNextPage() }}>More generators</Button>}</div>
}
