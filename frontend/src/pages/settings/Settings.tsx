import { useId, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import { getScheduleStatus, getSettings, saveSettings } from '../../api/endpoints'
import { isApiError, type ApiResult } from '../../api/client'
import type { SettingsRequest, SettingsResponse } from '../../api/types'
import { queryKeys } from '../../api/queryKeys'
import { useSession } from '../../session/SessionProvider'
import { Button } from '../../components/controls/Button'
import { Field, inputClass } from '../../components/controls/Field'
import { Switch } from '../../components/controls/Switch'
import { Callout } from '../../components/feedback/Callout'
import { LoadingRows } from '../../components/feedback/States'
import { PageHeader } from '../../components/layout/PageHeader'
import { formatLocalTime } from '../../lib/dates'
import { PageError } from '../shared'
import styles from './Settings.module.css'

export function Settings({ setup = false }: { setup?: boolean }) {
  const query = useQuery({ queryKey: queryKeys.settings, queryFn: getSettings })
  const [notice, setNotice] = useState<{ tone: 'status' | 'warning'; text: string } | null>(null)
  if (query.isPending) return <LoadingRows />
  if (query.error) return <PageError error={query.error} />
  return <SettingsForm key={query.data.data.revision} result={query.data} setup={setup} notice={notice} onNotice={setNotice} />
}
type Notice = { tone: 'status' | 'warning'; text: string } | null
function SettingsForm({ result, setup, notice, onNotice }: { result: ApiResult<SettingsResponse>; setup: boolean; notice: Notice; onNotice: (notice: Notice) => void }) {
  const cache = useQueryClient(), navigate = useNavigate(), { refresh } = useSession()
  const original: SettingsRequest = { schedule_enabled: result.data.schedule_enabled, daily_time: result.data.daily_time ?? '06:00', timezone: result.data.timezone ?? 'UTC' }
  const [values, setValues] = useState(original), [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(null)
  const status = useQuery({ queryKey: queryKeys.scheduleStatus, queryFn: getScheduleStatus })
  const switchLabel = useId()
  const edited = JSON.stringify(values) !== JSON.stringify(original)
  const changed = result.data.setup_completed_at === null || edited
  const zones = [...new Set(['UTC', values.timezone, ...Intl.supportedValuesOf('timeZone')])].sort()
  const save = async () => {
    if (!result.etag) return
    setBusy(true); setError(null); onNotice(null)
    try { const next = await saveSettings(values, result.etag); cache.setQueryData(queryKeys.settings, next); await cache.invalidateQueries({ queryKey: queryKeys.scheduleStatus }); await refresh(); onNotice({ tone: 'status', text: 'Saved. No refresh was started.' }); if (setup) await navigate('/refresh') }
    catch (failure) {
      if (isApiError(failure) && failure.status === 412) { onNotice({ tone: 'warning', text: 'Settings changed in another session. Review and save again.' }); await cache.invalidateQueries({ queryKey: queryKeys.settings }) }
      else { setError(failure); if (isApiError(failure) && failure.isNetworkError) { onNotice({ tone: 'warning', text: 'The save response was lost. Reloaded settings show the current saved values.' }); await cache.invalidateQueries({ queryKey: queryKeys.settings }) } }
    } finally { setBusy(false) }
  }
  // The status line next to Save tells whether the form differs from the saved values.
  const saveStatus = busy ? 'Saving…' : edited ? 'Unsaved changes.' : notice?.tone === 'status' ? notice.text : 'No unsaved changes.'
  const schedule = status.data?.data
  return <section>
    <PageHeader title={setup ? 'Set up Trinity' : 'Schedule'} subtitle="When the daily refresh runs." />
    <form className={styles.form} onSubmit={(e) => { e.preventDefault(); void save() }}>
      <div className={styles.switchRow}>
        <div><span id={switchLabel} className={styles.switchLabel}>Schedule enabled</span><p className={styles.switchHint}>{values.schedule_enabled ? `Runs daily at ${values.daily_time} ${values.timezone}.` : 'Off. Refreshes only start by hand.'}</p></div>
        <Switch checked={values.schedule_enabled} labelledBy={switchLabel} onChange={(checked) => setValues({ ...values, schedule_enabled: checked })} />
      </div>
      <Field label="Time"><input className={inputClass} type="time" required value={values.daily_time} onChange={(e) => setValues({ ...values, daily_time: e.target.value })} /></Field>
      <Field label="Timezone"><select className={[inputClass, styles.select].join(' ')} value={values.timezone} onChange={(e) => setValues({ ...values, timezone: e.target.value })}>{zones.map((zone) => <option key={zone}>{zone}</option>)}</select></Field>
      <p className={styles.note}>This only sets the clock. It does not start a refresh.</p>
      {notice?.tone === 'warning' && <Callout tone="warning">{notice.text}</Callout>}
      {error !== null && <PageError error={error} />}
      <div className={styles.saveRow}><Button type="submit" variant="primary" disabled={!changed || busy || !result.etag}>{busy ? 'Saving…' : setup ? 'Complete setup' : 'Save'}</Button><p role="status" className={styles.saveStatus}>{saveStatus}</p></div>
      {status.error ? <PageError error={status.error} /> : schedule && <>
        {schedule.next_check_local && <p className={styles.next}>Next scheduled check: {formatLocalTime(schedule.next_check_local)}{schedule.timezone ? ` (${schedule.timezone})` : ''}.</p>}
        {schedule.blocker && <Callout tone="warning">{schedule.blocker.message}</Callout>}
      </>}
    </form>
  </section>
}
