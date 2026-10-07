import { useState } from 'react'
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router'
import { getCandidate, getRun, getRuns, recoverRun, sendCandidateCommand, startRefresh, type CandidateCommand } from '../../api/endpoints'
import { isApiError, type ApiResult } from '../../api/client'
import type { Action, ActionReceipt, Run, RunStatus, Step } from '../../api/types'
import { STEP_STAGES } from '../../api/types'
import { queryKeys } from '../../api/queryKeys'
import { useSession } from '../../session/SessionProvider'
import { Button, TextLink } from '../../components/controls/Button'
import { ConfirmDialog } from '../../components/overlay/Dialog'
import { Callout } from '../../components/feedback/Callout'
import { StatusBadge } from '../../components/feedback/StatusBadge'
import { LoadingRows } from '../../components/feedback/States'
import { useToast } from '../../components/feedback/Toast'
import { ListTable } from '../../components/data/ListTable'
import { StepTimeline, type StepState } from '../../components/data/StepTimeline'
import { PageHeader } from '../../components/layout/PageHeader'
import { formatDuration, formatUtcTime, secondsBetween } from '../../lib/dates'
import { shortId } from '../../lib/ids'
import { RUN_STATUS, STAGE_LABELS, STEP_STATUS_LABELS, blockReason, candidateCopy } from '../../lib/copy'
import { ShortId } from '../../components/controls/ShortId'
import { PageError, reviewWarnings } from '../shared'
import styles from './Refresh.module.css'

export function RunBadge({ status, large = false }: { status: RunStatus; large?: boolean }) { const { tone, glyph, label } = RUN_STATUS[status]; return <StatusBadge tone={tone} glyph={glyph} large={large}>{label}</StatusBadge> }

/** Retry a lost response once with the same key. A new confirmation gets a new key. */
export async function retryCommand(send: (key: string) => Promise<ApiResult<ActionReceipt>>, key: string) {
  try { return await send(key) } catch (failure) { if (!isApiError(failure) || !failure.isNetworkError) throw failure; return send(key) }
}
/**
 * Send one confirmed command, then refresh every read and open the run that
 * the receipt names. `done` is the short toast shown after acceptance.
 */
function useCommand() {
  const cache = useQueryClient(), { refresh } = useSession(), navigate = useNavigate(), toast = useToast()
  const [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(null)
  const execute = async (send: (key: string) => Promise<ApiResult<ActionReceipt>>, done?: string) => {
    setBusy(true); setError(null)
    try {
      const response = await retryCommand(send, crypto.randomUUID())
      await cache.invalidateQueries(); await refresh()
      await navigate(`/refresh/${response.data.run_id}`)
      if (done) toast(done)
      return true
    } catch (failure) { setError(failure); if (isApiError(failure) && failure.status === 412) await cache.invalidateQueries(); return false }
    finally { setBusy(false) }
  }
  return { busy, error, execute }
}
export function RefreshList() {
  const { me } = useSession()
  const query = useInfiniteQuery({ queryKey: queryKeys.runs, initialPageParam: undefined as string | undefined, queryFn: ({ pageParam }) => getRuns(pageParam), getNextPageParam: (last) => last.data.next_cursor ?? undefined, refetchInterval: (q) => q.state.data?.pages[0].data.active_run ? 3000 : false })
  const command = useCommand(), [confirm, setConfirm] = useState(false)
  if (query.isPending) return <LoadingRows />
  if (query.error) return <PageError error={query.error} />
  const current = query.data.pages[0].data, start = current.actions.find((a) => a.action === 'start_refresh')
  const active = current.active_run
  return <section>
    <PageHeader title="Refresh" subtitle="Past runs. The current publication stays up until a new candidate is approved." aside={<Button variant="primary" disabled={!start?.enabled || command.busy} onClick={() => setConfirm(true)}>Start refresh</Button>} />
    {!start?.enabled && <p className={styles.reason}>{blockReason(start?.reason_code)}</p>}
    <div className={styles.stack}>
      {current.blocker && <Callout tone="warning" title="Refresh blocked">{current.blocker.message}</Callout>}
      {current.unresolved_warning && <Callout tone="warning" title="! Unresolved warning">{current.unresolved_warning.message} <TextLink to={`/refresh/${current.unresolved_warning.run_id}`}>Open run →</TextLink></Callout>}
      {command.error !== null && <PageError error={command.error} />}
    </div>
    <div className={styles.strip}>
      <span><span className="muted">Current publication </span>{me?.publication ? <span className="mono"><ShortId value={me.publication.version_id} /></span> : 'none yet'}</span>
      {active && <span><span className="muted">{active.status === 'awaiting_approval' ? 'Awaiting review ' : 'Current run '}</span><TextLink to={`/refresh/${active.run_id}`} className="mono">Run {shortId(active.run_id)}</TextLink>{active.status !== 'awaiting_approval' && <> <RunBadge status={active.status} /></>}</span>}
      <span className="muted">Failed or unfinished runs never replace the current publication.</span>
    </div>
    <div className={styles.list}>
      <ListTable label="Refresh runs" rowHeight={50} columns={[{ header: 'Run', track: '1fr' }, { header: 'Started', track: '1.4fr' }, { header: 'Status', track: '1fr' }, { header: 'Finished', track: '1fr' }]}
        empty="No runs yet. Start a refresh to retrieve the first set of data."
        rows={query.data.pages.flatMap((p) => p.data.items).map((run) => ({ key: run.run_id, to: `/refresh/${run.run_id}`, link: shortId(run.run_id), cells: [formatUtcTime(run.requested_at), <RunBadge key="status" status={run.status} />, run.finished_at ? formatUtcTime(run.finished_at) : '—'] }))} />
    </div>
    {query.hasNextPage && <div className={styles.more}><Button size="compact" disabled={query.isFetching} onClick={() => { void query.fetchNextPage() }}>Load older</Button></div>}
    {confirm && <ConfirmDialog title="Start refresh?" confirmLabel="Start refresh" busy={command.busy} onCancel={() => setConfirm(false)} onConfirm={() => { void command.execute(startRefresh, 'Refresh started. The current publication stays up.').then((ok) => { if (ok) setConfirm(false) }) }}>The current publication stays available while new data is checked.</ConfirmDialog>}
  </section>
}

/** Map the latest attempt of a stage to a timeline circle state. */
function stepState(step: Step | undefined): StepState {
  if (!step) return 'pending'
  return ({ pending: 'pending', running: 'running', succeeded: 'done', failed: 'failed', abandoned: 'failed' } as const)[step.status]
}
/** Build the timeline rows: Accepted, then one row per stage (spec UF-R06, UF-R08). */
function timeline(run: Run, steps: Step[]) {
  const ended = !['requested', 'running', 'awaiting_approval', 'publishing'].includes(run.status)
  const accepted = { key: 'accepted', state: 'done' as StepState, title: 'Accepted', description: 'The request was taken. Nothing was published yet.', meta: formatUtcTime(run.requested_at) }
  const stages = STEP_STAGES.map((stage) => {
    const attempts = steps.filter((s) => s.stage === stage)
    const latest = attempts.at(-1)
    let state = stepState(latest)
    let description: string
    if (stage === 'publish' && !latest && run.status === 'awaiting_approval') { state = 'attention'; description = 'Waiting on you.' }
    else if (stage === 'publish' && run.status === 'discarded') { state = 'discarded'; description = 'Candidate discarded. Nothing was published.' }
    else if (state === 'failed') description = latest?.error_summary ?? 'This step did not finish.'
    else if (state === 'running') description = 'Working…'
    else if (state === 'pending') description = ended ? 'Not reached.' : 'Waiting.'
    else if (stage === 'extract') description = 'Country, plant, and unit data came in.'
    else if (stage === 'prepare') description = run.candidate ? `Files for ${shortId(run.candidate.version_id)} are set aside.` : 'Files are set aside.'
    else if (stage === 'validate') description = 'Checks finished.'
    else description = run.candidate ? `Published as ${shortId(run.candidate.version_id)}.` : 'Published.'
    const duration = latest ? secondsBetween(latest.started_at, latest.finished_at) : null
    // Show each attempt only when there is more than one or it reports progress.
    const lines = attempts.length > 1 || (latest && latest.status === 'running') ? <ul className={styles.attempts}>{attempts.map((s) => { const d = secondsBetween(s.started_at, s.finished_at); return <li key={s.step_id}>Attempt {s.attempt} · {STEP_STATUS_LABELS[s.status]} · {s.progress.processed_count} / {s.progress.total_count ?? 'unknown total'} {s.progress.unit}{d !== null ? ` · ${formatDuration(d)}` : ''}</li> })}</ul> : undefined
    return { key: stage, state, title: STAGE_LABELS[stage], description, meta: duration !== null ? formatDuration(duration) : undefined, children: lines }
  })
  return [accepted, ...stages]
}
/** The status sentence under the run title. A failed run names the stage that stopped. */
function runSummary(run: Run, steps: Step[]) {
  if (run.status === 'failed') {
    const failed = steps.find((s) => s.status === 'failed' || s.status === 'abandoned')
    return failed ? `Stopped at ${STAGE_LABELS[failed.stage]}. The current publication was not replaced.` : RUN_STATUS.failed.summary
  }
  return RUN_STATUS[run.status].summary
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
  const current = me?.publication ? shortId(me.publication.version_id) : null
  const active = ['requested', 'running', 'publishing'].includes(run.status)
  return <section>
    <PageHeader breadcrumb={<TextLink to="/refresh">← Refresh</TextLink>} mono title={`Run #${run.run_seq}`} titleAddon={<span aria-live="polite" className={styles.titleBadge}><RunBadge status={run.status} large /></span>}
      subtitle={<>{runSummary(run, steps)} Started {formatUtcTime(run.requested_at)}. <span className={styles.runId}><ShortId value={run.run_id} /></span></>} />
    {(run.status === 'failed' || run.status === 'publication_failed') && <div className={styles.block}><Callout tone="error" title="✕ Run failed">Nothing was published. {current ? <><span className="mono">{current}</span> remains the current publication.</> : 'There is still no publication.'}{run.warning && <span className={styles.warningLine}>{run.warning.message}</span>}</Callout></div>}
    {active && <p className={styles.activeNote}>{current ? <><span className="mono">{current}</span> stays current while this runs.</> : 'Nothing is published yet.'}</p>}
    {(run.actions.some((a) => a.action === 'rerun' && a.enabled) || run.actions.some((a) => a.action === 'delete_warning' && a.enabled)) && <div className={styles.actions}>{run.actions.some((a) => a.action === 'rerun' && a.enabled) && <Button onClick={() => setRecoveryAction('rerun')}>Run again</Button>}{run.actions.some((a) => a.action === 'delete_warning' && a.enabled) && <Button onClick={() => setRecoveryAction('warning')}>Resolve warning</Button>}</div>}
    {recovery.error !== null && <div className={styles.block}><PageError error={recovery.error} /></div>}
    {recoveryAction && <ConfirmDialog title={recoveryAction === 'rerun' ? 'Run again?' : 'Resolve warning?'} confirmLabel={recoveryAction === 'rerun' ? 'Run again' : 'Resolve warning'} busy={recovery.busy} onCancel={() => setRecoveryAction(null)} onConfirm={() => { const etag = query.data.etag; if (etag) void recovery.execute((key) => recoverRun(runId, recoveryAction, etag, key), recoveryAction === 'rerun' ? 'A new run started.' : 'Warning resolved. No new refresh started.').then(() => setRecoveryAction(null)) }}>Abandon the old unpublished candidate and preserve the current publication.{recoveryAction === 'rerun' ? ' A new full refresh will start.' : ' No new refresh will start.'}</ConfirmDialog>}
    <h2 className="sr-only">Progress</h2>
    <StepTimeline items={timeline(run, steps)} />
    {next && <div className={styles.more}><Button size="compact" disabled={loadingMore} onClick={() => { void more() }}>Show more attempts</Button></div>}
    {moreError !== null && <div className={styles.block}><PageError error={moreError} /></div>}
    {run.candidate && <CandidatePanel key={run.candidate.version_id} versionId={run.candidate.version_id} revision={run.revision} current={current} />}
  </section>
}
const candidateActions: { action: Action['action']; path: CandidateCommand; label: string }[] = [{ action: 'approve', path: 'approval', label: 'Approve' }, { action: 'publication_retry', path: 'publication-retry', label: 'Retry publication' }, { action: 'discard', path: 'discard', label: 'Discard' }]
function CandidatePanel({ versionId, revision, current }: { versionId: string; revision: string; current: string | null }) {
  const query = useQuery({ queryKey: [...queryKeys.candidate(versionId), revision], queryFn: () => getCandidate(versionId) })
  const command = useCommand(), [selected, setSelected] = useState<typeof candidateActions[number] | null>(null)
  if (query.isPending) return <div className={styles.card}><LoadingRows /></div>
  if (query.error) return <div className={styles.card}><PageError error={query.error} /></div>
  const candidate = query.data.data
  const cand = shortId(candidate.version_id)
  const enabled = candidateActions.filter((a) => candidate.actions.some((available) => available.action === a.action && available.enabled))
  const warnings = reviewWarnings(candidate.diagnostics)
  const allPassed = candidate.validation.passed_required_count === candidate.validation.expected_required_count
  const open = candidate.disposition === 'active' && candidate.publication.status !== 'published'
  // Dialog and toast copy name both versions, so the Admin sees what replaces what.
  const copy = (action: Action['action']) => {
    if (action === 'approve') return { title: `Approve ${cand}?`, confirm: 'Approve and publish', body: `${cand} will replace ${current ?? 'nothing'} as the current publication. Values with warnings are published as-is, with their warnings.`, toast: current ? `${cand} approved. ${current} stays current until publishing finishes.` : `${cand} approved. Publishing has started.` }
    if (action === 'discard') return { title: `Discard ${cand}?`, confirm: 'Discard candidate', body: `This drops ${cand} permanently. It can't be brought back, and nothing from this run will be published. ${current ? `${current} stays the current publication.` : 'There is still no publication.'}`, toast: current ? `${cand} discarded. ${current} is still current.` : `${cand} discarded. Nothing was published.` }
    return { title: `Retry publication of ${cand}?`, confirm: 'Retry publication', body: `Publishing ${cand} runs again with the same reviewed files. The current publication stays up until it finishes.`, toast: `Publication of ${cand} started again.` }
  }
  return <section className={styles.card} aria-label="Candidate review">
    <div className={styles.cardHead}><span className={styles.cardLabel}>Candidate</span><span className={styles.cardId}><ShortId value={candidate.version_id} /></span></div>
    <p className={styles.cardText}>{candidate.validation.passed_required_count} of {candidate.validation.expected_required_count} required checks passed.</p>
    {warnings.map((d) => <div key={d.code + d.scope} className={styles.callout}><Callout tone="warning" title="! Warning">{d.message}</Callout></div>)}
    {warnings.length === 0 && allPassed && open && <p className={styles.passed}>✓ All checks passed with no warnings.</p>}
    <p className={styles.cardText}>{candidateCopy(candidate)}</p>
    {enabled.some((a) => a.action === 'approve') && <p className={styles.cardText}>{current ? <>The current publication is still <span className="mono">{current}</span>. Approving publishes <span className="mono">{cand}</span> in its place.</> : <>There is no publication yet. Approving publishes <span className="mono">{cand}</span> as the first publication.</>}</p>}
    {enabled.length > 0 && <div className={styles.cardActions}>{enabled.map((a) => <Button key={a.action} variant={a.action === 'approve' ? 'primary' : a.action === 'discard' ? 'destructive' : 'secondary'} disabled={!query.data.etag || command.busy} onClick={() => setSelected(a)}>{a.label}</Button>)}</div>}
    {enabled.some((a) => a.action === 'discard') && <p className={styles.note}>Discard drops this candidate. It can&apos;t be brought back.</p>}
    {command.error !== null && <div className={styles.callout}>{isApiError(command.error) && command.error.status === 412 ? <Callout tone="warning">This candidate changed. Review it again.</Callout> : <PageError error={command.error} />}</div>}
    {selected && <ConfirmDialog title={copy(selected.action).title} confirmLabel={copy(selected.action).confirm} tone={selected.action === 'discard' ? 'destructive' : 'primary'} busy={command.busy} onCancel={() => setSelected(null)} onConfirm={() => {
      const etag = query.data.etag
      if (!etag) return
      void command.execute((key) => sendCandidateCommand(versionId, selected.path, etag, key), copy(selected.action).toast).then(() => setSelected(null))
    }}>{copy(selected.action).body}</ConfirmDialog>}
  </section>
}
