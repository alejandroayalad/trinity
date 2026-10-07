import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getCatalog, runQuery } from '../../api/endpoints'
import { isApiError } from '../../api/client'
import { queryKeys } from '../../api/queryKeys'
import type { Dataset, QueryResponse } from '../../api/types'
import { Button } from '../../components/controls/Button'
import { ShortId } from '../../components/controls/ShortId'
import { PageHeader } from '../../components/layout/PageHeader'
import { errorMessage } from '../../api/messages'
import { useSession } from '../../session/SessionProvider'
import { DataTable, Diagnostics, PageError } from '../shared'
import { Waiting } from '../unavailable/Waiting'
import styles from './SqlExplorer.module.css'

export const defaultSql = 'SELECT period, facility, "facilityName", capacity, outage FROM facility_outages ORDER BY period, facility LIMIT 100'

/**
 * Example chips (spec UF-Q04). Each one puts real SQL in the editor; the
 * user still runs it. "Error" shows how the server rejects a table that is
 * not a published dataset.
 */
const EXAMPLES: [string, string][] = [
  ['Browns Ferry', `SELECT period, "facilityName", capacity, outage\nFROM facility_outages\nWHERE "facilityName" = 'Browns Ferry'\nORDER BY period`],
  ['Empty result', 'SELECT period, outage\nFROM national_outages\nWHERE outage < 0'],
  ['Error', 'SELECT *\nFROM settings'],
  ['Generators', 'SELECT period, facility, generator, capacity, outage\nFROM generator_outages\nORDER BY period DESC, facility, generator\nLIMIT 100'],
]

/** The schema aside: one expandable row per published dataset, with its columns. */
function SchemaTree({ datasets }: { datasets: Dataset[] }) {
  const [open, setOpen] = useState<Record<string, boolean>>({ facility_outages: true })
  return <>{datasets.map((d) => <div key={d.key}>
    <button type="button" className={styles.schemaRow} aria-expanded={open[d.key] ?? false} onClick={() => setOpen({ ...open, [d.key]: !open[d.key] })}><span>{d.key}</span><span className={styles.schemaSign} aria-hidden="true">{open[d.key] ? '−' : '+'}</span></button>
    {open[d.key] && <ul className={styles.columns}>{d.columns.map((c) => <li key={c.name}><span>{c.name}</span><span className={styles.type}>{c.type}{c.nullable ? ' · nullable' : ''}</span></li>)}</ul>}
  </div>)}</>
}

export function SqlExplorer() {
  const { me } = useSession()
  const [sql, setSql] = useState(defaultSql)
  const [result, setResult] = useState<QueryResponse | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const [wait, setWait] = useState(0)
  const [tables, setTables] = useState(true)
  const pending = useRef<AbortController | null>(null)
  const gutter = useRef<HTMLDivElement>(null)
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
  const lines = sql.split('\n').length
  // The editor grows with the text: 22px per line plus 28px padding, at least 5 lines.
  const height = `${Math.max(5, lines) * 22 + 28}px`
  const meta = busy ? 'Running…' : error !== null ? 'Did not run' : result ? `${result.returned_rows} rows · ${result.execution_ms} ms` : ''
  const reason = oversized ? 'The query is over 16 KiB. Shorten it to run.' : !sql.trim() ? 'Type a query to run.' : ''
  return <section>
    <PageHeader title="SQL Explorer" subtitle={<>Read-only queries against {me?.publication ? <ShortId value={me.publication.version_id} /> : 'published data'}.</>}
      aside={<button type="button" className={styles.tablesToggle} aria-expanded={tables} onClick={() => setTables(!tables)}>{tables ? 'Tables ▾' : 'Tables ▸'}</button>} />
    <div className={styles.layout}>
      <div className={styles.main}>
        <div className={styles.editor}>
          <div className={styles.editorBody}>
            <div ref={gutter} className={styles.gutter} aria-hidden="true" style={{ height }}>{sql.split('\n').map((_, i) => <div key={i}>{i + 1}</div>)}</div>
            <label htmlFor="sql-editor" className="sr-only">Query</label>
            <textarea id="sql-editor" className={styles.textarea} spellCheck={false} value={sql} style={{ height }} onScroll={(e) => { if (gutter.current) gutter.current.scrollTop = e.currentTarget.scrollTop }} onChange={(e) => setSql(e.target.value)} onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); void run() } }} />
          </div>
          <div className={styles.footer}>
            <span className={styles.examplesLabel}>Examples</span>
            {EXAMPLES.map(([label, text]) => <button key={label} type="button" className={styles.chip} onClick={() => setSql(text)}>{label}</button>)}
            <span className={styles.spacer} />
            {reason ? <span role={oversized ? 'alert' : undefined} className={oversized ? styles.reasonError : styles.hint}>{reason}</span> : <span className={styles.hint}>⌘/Ctrl + Enter</span>}
            <Button variant="primary" size="compact" disabled={disabled} onClick={() => { void run() }}>{busy ? 'Running…' : wait ? `Try again in ${wait}s` : 'Run query'}</Button>
          </div>
        </div>
        <div className={styles.resultsHead}><h2 className={styles.resultsTitle}>Results</h2><span role="status" className={styles.meta}>{meta}</span></div>
        <div aria-live="polite" className={styles.results} aria-busy={busy}>
          {busy && <div className={styles.skeleton}><span /><span /><span /></div>}
          {error !== null && (isApiError(error, 'data_unavailable') ? <Waiting /> : isApiError(error, 'rate_limited') ? <PageError error={error} /> : <div role="alert" className={styles.error}><strong>✕ Query error</strong><span>{errorMessage(error)}</span></div>)}
          {result && <><Diagnostics diagnostics={result.diagnostics} />{result.rows.length ? <DataTable columns={result.columns} rows={result.rows} sql /> : <div className={styles.empty}>The query ran and returned 0 rows.</div>}{result.truncated && <p className={styles.note}>Showing the first 1,000 rows. Add LIMIT or filters to see the rest.</p>}</>}
          {!busy && error === null && !result && <div className={[styles.empty, styles.idle].join(' ')}>Run a query to see results.</div>}
        </div>
      </div>
      {tables && <aside className={styles.schema} aria-label="Tables"><h2 className={styles.schemaTitle}>Tables</h2>{catalog.error && <PageError error={catalog.error} />}{catalog.data && <SchemaTree datasets={catalog.data.data.datasets} />}</aside>}
    </div>
  </section>
}
