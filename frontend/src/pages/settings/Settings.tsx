import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import { getScheduleStatus, getSettings, saveSettings } from '../../api/endpoints'
import { isApiError, type ApiResult } from '../../api/client'
import type { SettingsRequest, SettingsResponse } from '../../api/types'
import { queryKeys } from '../../api/queryKeys'
import { useSession } from '../../session/SessionProvider'
import { Button } from '../../components/controls/Button'
import { LoadingRows } from '../../components/feedback/States'
import { PageError } from '../shared'

export function Settings({ setup = false }: { setup?: boolean }) {
  const query = useQuery({ queryKey: queryKeys.settings, queryFn: getSettings })
  const [notice, setNotice] = useState('')
  if (query.isPending) return <LoadingRows />
  if (query.error) return <PageError error={query.error} />
  return <SettingsForm key={query.data.data.revision} result={query.data} setup={setup} notice={notice} onNotice={setNotice} />
}
function SettingsForm({ result, setup, notice, onNotice }: { result: ApiResult<SettingsResponse>; setup: boolean; notice: string; onNotice: (text: string) => void }) {
  const cache = useQueryClient(), navigate = useNavigate(), { refresh } = useSession()
  const original: SettingsRequest = { schedule_enabled: result.data.schedule_enabled, daily_time: result.data.daily_time ?? '06:00', timezone: result.data.timezone ?? 'UTC' }
  const [values, setValues] = useState(original), [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(null)
  const status = useQuery({ queryKey: queryKeys.scheduleStatus, queryFn: getScheduleStatus })
  const changed = result.data.setup_completed_at === null || JSON.stringify(values) !== JSON.stringify(original)
  const zones = [...new Set(['UTC', values.timezone, ...Intl.supportedValuesOf('timeZone')])].sort()
  const save = async () => {
    if (!result.etag) return
    setBusy(true); setError(null); onNotice('')
    try { const next = await saveSettings(values, result.etag); cache.setQueryData(queryKeys.settings, next); await cache.invalidateQueries({ queryKey: queryKeys.scheduleStatus }); await refresh(); onNotice('Schedule saved.'); if (setup) await navigate('/refresh') }
    catch (failure) {
      if (isApiError(failure) && failure.status === 412) { onNotice('Settings changed in another session. Review and save again.'); await cache.invalidateQueries({ queryKey: queryKeys.settings }) }
      else { setError(failure); if (isApiError(failure) && failure.isNetworkError) { onNotice('The save response was lost. Reloaded settings show the current saved values.'); await cache.invalidateQueries({ queryKey: queryKeys.settings }) } }
    } finally { setBusy(false) }
  }
  return <section className="stack"><h1>{setup ? 'Set up Trinity' : 'Schedule'}</h1><form className="panel stack settings-form" onSubmit={(e) => { e.preventDefault(); void save() }}>
    <label className="row"><input type="checkbox" role="switch" checked={values.schedule_enabled} onChange={(e) => setValues({ ...values, schedule_enabled: e.target.checked })} />Schedule enabled</label>
    <label>Time<input type="time" required value={values.daily_time} onChange={(e) => setValues({ ...values, daily_time: e.target.value })} /></label><label>Timezone<select value={values.timezone} onChange={(e) => setValues({ ...values, timezone: e.target.value })}>{zones.map((zone) => <option key={zone}>{zone}</option>)}</select></label>
    <Button type="submit" variant="primary" disabled={!changed || busy || !result.etag}>{busy ? 'Saving…' : setup ? 'Complete setup' : 'Save schedule'}</Button><p role="status">{notice}</p>{error !== null && <PageError error={error} />}<p className="muted">This only sets the clock. It does not start a refresh.</p>
  </form>{status.error ? <PageError error={status.error} /> : status.data && <div className="panel stack"><h2>Schedule status</h2>{status.data.data.next_check_local && <p>Next check: {status.data.data.next_check_local} ({status.data.data.timezone})</p>}{status.data.data.blocker && <p>{status.data.data.blocker.message}</p>}</div>}</section>
}
