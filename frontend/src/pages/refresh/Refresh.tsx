import { useState } from 'react'
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router'
import { getCandidate, getRun, getRuns, recoverRun, sendCandidateCommand, startRefresh, type CandidateCommand } from '../../api/endpoints'
import { isApiError, type ApiResult } from '../../api/client'
import type { Action, ActionReceipt, Candidate, RunStatus, Step } from '../../api/types'
import { STEP_STAGES } from '../../api/types'
import { queryKeys } from '../../api/queryKeys'
import { useSession } from '../../session/SessionProvider'
import { Button } from '../../components/controls/Button'
import { ConfirmDialog } from '../../components/overlay/Dialog'
import { Callout } from '../../components/feedback/Callout'
import { StatusBadge, type Tone } from '../../components/feedback/StatusBadge'
import { LoadingRows } from '../../components/feedback/States'
import { formatDuration, formatUtcTime, secondsBetween } from '../../lib/dates'
import { ShortId } from '../../components/controls/ShortId'
import { Diagnostics, PageError } from '../shared'

const statuses: Record<RunStatus, [Tone, string, string]> = { requested: ['running', '◐', 'Running'], running: ['running', '◐', 'Running'], awaiting_approval: ['warning', '!', 'Awaiting review'], publishing: ['running', '◐', 'Publishing'], publication_failed: ['error', '✕', 'Publication failed'], failed: ['error', '✕', 'Failed'], succeeded: ['success', '✓', 'Published'], discarded: ['neutral', '–', 'Discarded'], superseded: ['neutral', '–', 'Superseded'] }
export function RunBadge({ status }: { status: RunStatus }) { const [tone, glyph, label] = statuses[status]; return <StatusBadge tone={tone} glyph={glyph}>{label}</StatusBadge> }

/** Retry a lost response once with the same key. A new confirmation gets a new key. */
export async function retryCommand(send: (key: string) => Promise<ApiResult<ActionReceipt>>, key: string) {
  try { return await send(key) } catch (failure) { if (!isApiError(failure) || !failure.isNetworkError) throw failure; return send(key) }
}
function useCommand() {
  const cache = useQueryClient(), { refresh } = useSession(), navigate = useNavigate()
  const [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(null)
  const execute = async (send: (key: string) => Promise<ApiResult<ActionReceipt>>) => {
    setBusy(true); setError(null)
    try {
      const response = await retryCommand(send, crypto.randomUUID())
      await cache.invalidateQueries(); await refresh()
      await navigate(`/refresh/${response.data.run_id}`)
      return true
    } catch (failure) { setError(failure); if (isApiError(failure) && failure.status === 412) await cache.invalidateQueries(); return false }
    finally { setBusy(false) }
  }
  return { busy, error, execute }
}
export function RefreshList() {
  const query = useInfiniteQuery({ queryKey: queryKeys.runs, initialPageParam: undefined as string | undefined, queryFn: ({ pageParam }) => getRuns(pageParam), getNextPageParam: (last) => last.data.next_cursor ?? undefined, refetchInterval: (q) => q.state.data?.pages[0].data.active_run ? 3000 : false })
  const command = useCommand(), [confirm, setConfirm] = useState(false)
  if (query.isPending) return <LoadingRows />
  if (query.error) return <PageError error={query.error} />
  const current = query.data.pages[0].data, start = current.actions.find((a) => a.action === 'start_refresh')
  return <section className="stack"><div className="row spread"><h1>Refresh</h1><Button variant="primary" disabled={!start?.enabled || command.busy} onClick={() => setConfirm(true)}>Start refresh</Button></div>
    {!start?.enabled && <p>{start?.reason_code ?? 'not_applicable'}</p>}
    {current.blocker && <Callout tone="warning" title={current.blocker.code}>{current.blocker.message}</Callout>}
    {current.active_run && <p>Current run: <Link to={`/refresh/${current.active_run.run_id}`}><ShortId value={current.active_run.run_id} /></Link> <RunBadge status={current.active_run.status} /></p>}
    {current.unresolved_warning && <Callout tone="error" title="Unresolved warning"><Link to={`/refresh/${current.unresolved_warning.run_id}`}>{current.unresolved_warning.message}</Link></Callout>}
    {command.error !== null && <PageError error={command.error} />}
    <div className="panel table-scroll"><table><thead><tr><th>Run</th><th>Requested</th><th>Status</th><th>Finished</th></tr></thead><tbody>{query.data.pages.flatMap((p) => p.data.items).map((run) => <tr key={run.run_id}><td><Link to={`/refresh/${run.run_id}`}>{run.run_id.slice(0, 8)}</Link></td><td>{formatUtcTime(run.requested_at)}</td><td><RunBadge status={run.status} /></td><td>{run.finished_at ? formatUtcTime(run.finished_at) : '—'}</td></tr>)}</tbody></table>{current.items.length === 0 && <p className="empty">No refresh runs yet.</p>}</div>
    {query.hasNextPage && <Button disabled={query.isFetching} onClick={() => { void query.fetchNextPage() }}>Load older</Button>}
    {confirm && <ConfirmDialog title="Start refresh?" confirmLabel="Start refresh" busy={command.busy} onCancel={() => setConfirm(false)} onConfirm={() => { void command.execute(startRefresh).then((ok) => { if (ok) setConfirm(false) }) }}>The current publication stays available while new data is checked.</ConfirmDialog>}
  </section>
}
const stageLabels = { extract: 'Retrieve', prepare: 'Prepare', validate: 'Validate', publish: 'Publish' }
function Steps({ steps }: { steps: Step[] }) {
  return <>{STEP_STAGES.map((stage) => <section key={stage} className="stack"><h3>{stageLabels[stage]}</h3>{steps.filter((s) => s.stage === stage).map((s) => {
    const duration = secondsBetween(s.started_at, s.finished_at)
    return <div key={s.step_id} className="row spread"><span>{s.work_key} · Attempt {s.attempt} · {s.status}</span><span>{s.progress.processed_count} / {s.progress.total_count ?? 'unknown total'} {s.progress.unit}{duration !== null ? ` · ${formatDuration(duration)}` : ''}</span>{s.error_summary && <p role="status">{s.error_summary}</p>}</div>
  })}</section>)}</>
}
export function RunDetail() { const { runId = '' } = useParams(); return <RunPage key={runId} runId={runId} /> }
function RunPage({ runId }: { runId: string }) {
  const { me, refresh } = useSession(), cache = useQueryClient()
  const recovery = useCommand(), [recoveryAction, setRecoveryAction] = useState<'rerun' | 'warning' | null>(null)
  const [older, setOlder] = useState<Step[]>([]), [cursor, setCursor] = useState<string | null | undefined>(undefined)
  const [moreError, setMoreError] = useState<unknown>(null), [loadingMore, setLoadingMore] = useState(false)
  const query = useQuery({ queryKey: queryKeys.run(runId), queryFn: async () => {
    const result = await getRun(runId)
    const previous = cache.getQueryData<ApiResult<typeof result.data>>(queryKeys.run(runId))
    if (previous && previous.data.status !== result.data.status) { void refresh().catch(() => undefined); void cache.invalidateQueries({ queryKey: queryKeys.runs }); if (result.data.status === 'succeeded') for (const key of ['catalog', 'dashboard', 'preview']) void cache.invalidateQueries({ queryKey: [key] }) }
    return result
  }, refetchInterval: (q) => { const seconds = q.state.data?.data.poll_after_seconds; return seconds == null ? false : seconds * 1000 } })
  if (query.isPending) return <LoadingRows />
  if (query.error) return <PageError error={query.error} />
  const run = query.data.data, next = cursor === undefined ? run.next_steps_cursor : cursor
  const steps = [...new Map([...older, ...run.steps].map((s) => [s.step_id, s])).values()].sort((a, b) => BigInt(a.step_seq) < BigInt(b.step_seq) ? -1 : 1)
  const more = async () => { if (!next) return; setLoadingMore(true); try { const result = await getRun(runId, next); setOlder((items) => [...items, ...result.data.steps]); setCursor(result.data.next_steps_cursor) } catch (failure) { setMoreError(failure) } finally { setLoadingMore(false) } }
  return <section className="stack"><Link to="/refresh">← Refresh</Link><div className="row spread"><h1>Run #{run.run_seq}</h1><div aria-live="polite"><RunBadge status={run.status} /></div></div><p className="row"><ShortId value={run.run_id} />Requested {formatUtcTime(run.requested_at)}</p>
    {(run.status === 'failed' || run.status === 'publication_failed') && <Callout tone="error" title="Refresh failed">{run.warning?.message ?? 'The refresh did not complete.'}<p>Current publication: {me?.publication?.version_id.slice(0, 8) ?? 'None'}</p></Callout>}
    <div className="row">{run.actions.some((a) => a.action === 'rerun' && a.enabled) && <Button onClick={() => setRecoveryAction('rerun')}>Run again</Button>}{run.actions.some((a) => a.action === 'delete_warning' && a.enabled) && <Button onClick={() => setRecoveryAction('warning')}>Resolve warning</Button>}</div>
    {recovery.error !== null && <PageError error={recovery.error} />}
    {recoveryAction && <ConfirmDialog title={recoveryAction === 'rerun' ? 'Run again?' : 'Resolve warning?'} confirmLabel={recoveryAction === 'rerun' ? 'Run again' : 'Resolve warning'} busy={recovery.busy} onCancel={() => setRecoveryAction(null)} onConfirm={() => { const etag = query.data.etag; if (etag) void recovery.execute((key) => recoverRun(runId, recoveryAction, etag, key)).then(() => setRecoveryAction(null)) }}>Abandon the old unpublished candidate and preserve the current publication.{recoveryAction === 'rerun' ? ' A new full refresh will start.' : ' No new refresh will start.'}</ConfirmDialog>}
    <div className="panel stack"><h2>Progress</h2><p>✓ Accepted · {formatUtcTime(run.requested_at)}</p><Steps steps={steps} />{next && <Button disabled={loadingMore} onClick={() => { void more() }}>Show more attempts</Button>}{moreError !== null && <PageError error={moreError} />}</div>
    {run.candidate && <CandidatePanel key={run.candidate.version_id} versionId={run.candidate.version_id} revision={run.revision} />}
  </section>
}
const candidateActions: { action: Action['action']; path: CandidateCommand; label: string }[] = [{ action: 'approve', path: 'approval', label: 'Approve' }, { action: 'publication_retry', path: 'publication-retry', label: 'Retry publication' }, { action: 'discard', path: 'discard', label: 'Discard' }]
/** Describe the server outcome without inferring permission to run an action. */
function candidateCopy(candidate: Candidate): string {
  if (candidate.disposition === 'discarded' || candidate.review_status === 'discarded') return 'This candidate was discarded and cannot be published.'
  if (candidate.disposition === 'superseded') return 'This candidate was superseded and will not replace the current publication.'
  if (candidate.publication.status === 'published') return 'This candidate was published successfully.'
  if (candidate.publication.status === 'failed') return 'Publication failed. This attempt did not replace the current publication.'
  if (candidate.publication.status === 'blocked' || candidate.validation_status === 'rejected') return 'Publication is blocked. Approval cannot bypass required checks.'
  if (candidate.publication.status === 'queued' || candidate.publication.status === 'publishing') return 'Publication is in progress. The current publication stays in place until this candidate is published successfully.'
  if (candidate.review_status === 'required') return 'Review warnings require Admin approval before publication. The current publication stays in place.'
  if (candidate.review_status === 'approved') return 'Review warnings were approved. The current publication stays in place until publication succeeds.'
  if (candidate.review_status === 'not_required') return 'No review approval is required. This candidate follows automatic publication after the required checks pass.'
  return 'Validation is not complete. Approval requirements are not yet known.'
}
function CandidatePanel({ versionId, revision }: { versionId: string; revision: string }) {
  const query = useQuery({ queryKey: [...queryKeys.candidate(versionId), revision], queryFn: () => getCandidate(versionId) })
  const command = useCommand(), [selected, setSelected] = useState<typeof candidateActions[number] | null>(null)
  if (query.isPending) return <LoadingRows />
  if (query.error) return <PageError error={query.error} />
  const candidate = query.data.data
  return <section className="panel stack"><h2>Candidate review</h2><ShortId value={candidate.version_id} /><p>{candidate.validation.passed_required_count} / {candidate.validation.expected_required_count} required checks passed</p><p>Review: {candidate.review_status} · Publication: {candidate.publication.status}</p><Diagnostics diagnostics={candidate.diagnostics} /><p>{candidateCopy(candidate)}</p>
    <div className="row">{candidateActions.filter((a) => candidate.actions.some((available) => available.action === a.action && available.enabled)).map((a) => <Button key={a.action} disabled={!query.data.etag || command.busy} onClick={() => setSelected(a)}>{a.label}</Button>)}</div>
    {command.error !== null && (isApiError(command.error) && command.error.status === 412 ? <p role="alert">This candidate changed. Review it again.</p> : <PageError error={command.error} />)}
    {selected && <ConfirmDialog title={`${selected.label} candidate?`} confirmLabel={selected.label} tone={selected.action === 'discard' ? 'destructive' : 'primary'} busy={command.busy} onCancel={() => setSelected(null)} onConfirm={() => {
      const etag = query.data.etag
      if (!etag) return
      void command.execute((key) => sendCandidateCommand(versionId, selected.path, etag, key)).then(() => setSelected(null))
    }}>{selected.action === 'discard' ? 'This candidate is permanently abandoned. The existing publication stays available.' : 'Use the reviewed candidate and its current validation evidence.'}</ConfirmDialog>}
  </section>
}
