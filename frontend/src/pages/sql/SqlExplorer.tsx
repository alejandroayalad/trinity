import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getCatalog, runQuery } from '../../api/endpoints'
import { isApiError } from '../../api/client'
import { queryKeys } from '../../api/queryKeys'
import type { QueryResponse } from '../../api/types'
import { Button } from '../../components/controls/Button'
import { LoadingRows } from '../../components/feedback/States'
import { DataTable, Diagnostics, PageError } from '../shared'

export const defaultSql = 'SELECT period, facility, "facilityName", capacity, outage FROM facility_outages ORDER BY period, facility LIMIT 100'
export function SqlExplorer() {
  const [sql, setSql] = useState(defaultSql)
  const [result, setResult] = useState<QueryResponse | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const [wait, setWait] = useState(0)
  const pending = useRef<AbortController | null>(null)
  const gutter = useRef<HTMLPreElement>(null)
  const catalog = useQuery({ queryKey: queryKeys.catalog, queryFn: getCatalog })
  useEffect(() => () => pending.current?.abort(), [])
  useEffect(() => { if (!wait) return; const timer = window.setTimeout(() => setWait((value) => Math.max(0, value - 1)), 1000); return () => window.clearTimeout(timer) }, [wait])
  const oversized = new TextEncoder().encode(sql).byteLength > 16384
  const disabled = busy || wait > 0 || !sql.trim() || oversized
  const run = async () => {
    if (disabled) return
    const controller = new AbortController(); pending.current = controller
    setBusy(true); setError(null); setResult(null)
    try { const response = await runQuery(sql, controller.signal); if (!controller.signal.aborted) setResult(response.data) }
    catch (failure) { if (!controller.signal.aborted) { setError(failure); if (isApiError(failure) && failure.status === 429) setWait(failure.retryAfter ?? 1) } }
    finally { if (!controller.signal.aborted) setBusy(false) }
  }
  return <section className="stack"><h1>SQL Explorer</h1><p className="muted">Read-only queries over published data.</p><div className="sql-layout"><div className="stack"><div className="panel stack">
    <label htmlFor="sql-editor">Query</label><div className="editor"><pre ref={gutter} aria-hidden="true">{sql.split('\n').map((_, i) => i + 1).join('\n')}</pre><textarea id="sql-editor" spellCheck={false} value={sql} rows={Math.max(8, sql.split('\n').length)} onScroll={(e) => { if (gutter.current) gutter.current.scrollTop = e.currentTarget.scrollTop }} onChange={(e) => setSql(e.target.value)} onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); void run() } }} /></div>
    <div className="row"><Button variant="primary" disabled={disabled} onClick={() => { void run() }}>{busy ? 'Running…' : wait ? `Try again in ${wait}s` : 'Run query'}</Button><span className="muted">⌘ / Ctrl + Enter</span><Button onClick={() => setSql('SELECT period, capacity, outage FROM national_outages ORDER BY period LIMIT 100')}>National example</Button></div>{oversized && <p role="alert">The query exceeds 16 KiB.</p>}</div>
    <div aria-live="polite">{busy && <LoadingRows label="Running…" />}{error !== null && <PageError error={error} />}{result && <div className="panel stack"><p>{result.returned_rows} rows · {result.execution_ms} ms</p><Diagnostics diagnostics={result.diagnostics} />{result.rows.length ? <DataTable columns={result.columns} rows={result.rows} sql /> : <p>The query ran and returned 0 rows.</p>}{result.truncated && <p>Showing the first 1,000 rows. Add LIMIT or filters to see the rest.</p>}</div>}</div></div>
    <aside className="panel stack"><h2>Schema</h2>{catalog.error && <PageError error={catalog.error} />}{catalog.data?.data.datasets.map((d) => <div key={d.key}><h3 className="mono">{d.key}</h3>{d.columns.map((c) => <p key={c.name}><code>{c.name}</code> · {c.type}{c.nullable ? ' · nullable' : ''}</p>)}</div>)}</aside></div></section>
}
