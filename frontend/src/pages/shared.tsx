import { useEffect, useRef, useState } from 'react'
import type { Cell, Column, Diagnostic } from '../api/types'
import { isApiError } from '../api/client'
import { Button } from '../components/controls/Button'
import { MissingChip, UnavailableValue } from '../components/feedback/StatusBadge'
import { ErrorState } from '../components/feedback/States'
import { Callout } from '../components/feedback/Callout'
import { Waiting } from './unavailable/Waiting'
import { formatExact, formatFixed, isOutOfRange, offlineShare, parseDecimal } from '../lib/decimal'
import { formatDay } from '../lib/dates'
import styles from './shared.module.css'

export { styles as sharedStyles }

/** Keep unavailable and denied reads separate from recoverable failures. */
export function PageError({ error, onRetry, busy = false, title }: { error: unknown; onRetry?: () => unknown; busy?: boolean; title?: string }) {
  if (isApiError(error, 'data_unavailable')) return <Waiting />
  const denied = isApiError(error) && (error.status === 401 || error.status === 403 || error.status === 404)
  return <div className={styles.retryRow}><ErrorState error={error} title={title} />{onRetry !== undefined && !denied && <ReadRetry error={error} busy={busy} onRetry={onRetry} />}</div>
}

/** A manual read retry waits for the server and shares one in-flight action. */
function ReadRetry({ error, busy, onRetry }: { error: unknown; busy: boolean; onRetry: () => unknown }) {
  const [expired, setExpired] = useState<unknown>(null)
  const [pending, setPending] = useState(false)
  const active = useRef(false)
  const seconds = isApiError(error) ? error.retryAfter ?? 0 : 0
  const waiting = seconds > 0 && expired !== error
  useEffect(() => {
    if (!waiting) return
    const timer = window.setTimeout(() => setExpired(error), seconds * 1000)
    return () => window.clearTimeout(timer)
  }, [error, seconds, waiting])
  const retry = async () => {
    if (active.current || busy || waiting) return
    active.current = true; setPending(true)
    try { await onRetry() } finally { active.current = false; setPending(false) }
  }
  return <Button disabled={busy || pending || waiting} onClick={() => void retry()}>{waiting ? `Retry after ${seconds}s` : 'Retry'}</Button>
}
// Show only review warnings. A review warning has severity 'warning' and
// affected_count above zero. The backend counts warnings with the same rule.
// The candidate API also returns passed checks with affected_count '0'.
// Counter text is canonical, so '0' is the only text for zero.
// The callout title comes from the severity; the code is never shown (R22).
export function reviewWarnings(diagnostics: Diagnostic[]) {
  return diagnostics.filter((d) => d.severity === 'warning' && d.affected_count !== '0')
}
export function Diagnostics({ diagnostics }: { diagnostics: Diagnostic[] }) {
  return <>{reviewWarnings(diagnostics).map((d) => <Callout key={d.code + d.scope} tone="warning" title="! Warning">{d.message}</Callout>)}</>
}

/** The tag for a share outside 0–100. The value stays as published (spec R18). */
export function OutOfRangeTag() {
  return <span className={styles.outOfRange} title="Outside 0–100, left as-is">! Outside 0–100</span>
}

export function Share({ outage, capacity }: { outage: Cell | undefined; capacity: Cell | undefined }) {
  if (typeof outage !== 'string' || typeof capacity !== 'string') return <MissingChip />
  const share = offlineShare(parseDecimal(outage), parseDecimal(capacity))
  if (share.kind !== 'value') return <UnavailableValue />
  return <span>{formatFixed(share.value, 2)}%{isOutOfRange(share.value) && <OutOfRangeTag />}</span>
}
const labels: Record<string, string> = { period: 'Day', facility: 'Facility ID', facilityName: 'Facility', generator: 'Unit', capacity: 'Capacity MW', outage: 'Outage MW', percentOutage: 'Source %' }

/** Show one table cell. Decimals use exact grouping; dates use "27 Sep 2026" outside SQL. */
function cellText(cell: Cell, column: Column, sql: boolean): string {
  if (sql) return String(cell)
  if (typeof cell === 'string' && column.type === 'decimal') return formatExact(cell)
  if (typeof cell === 'string' && column.type === 'date') {
    try { return formatDay(cell) } catch { return cell }
  }
  return String(cell)
}
export function DataTable({ columns, rows, sql = false }: { columns: Column[]; rows: Cell[][]; sql?: boolean }) {
  // SQL may return duplicate column names. Position identifies each header
  // because rows follow the same ordered column array, without renaming it.
  const outage = columns.findIndex((c) => c.name === 'outage')
  const capacity = columns.findIndex((c) => c.name === 'capacity')
  const numeric = (column: Column) => !sql && (column.type === 'decimal' || column.type === 'integer')
  return <div className={sql ? styles.sqlScroll : styles.tableScroll} tabIndex={0} role="region" aria-label={sql ? 'SQL results' : 'Dataset rows'}><table className={sql ? styles.sqlTable : styles.table}><thead><tr>{columns.map((c, index) => <th key={index} className={numeric(c) ? styles.number : undefined}>{sql ? c.name : labels[c.name] ?? c.name}{sql && c.unit ? <span className={styles.unit}> ({c.unit})</span> : ''}</th>)}{!sql && <th className={styles.number}>Offline share</th>}</tr></thead>
    <tbody>{rows.map((row, index) => <tr key={index}>{row.map((cell, i) => <td key={i} className={numeric(columns[i]) ? styles.number : undefined}>{cell === null ? <MissingChip label={sql ? 'NULL' : undefined} /> : cellText(cell, columns[i], sql)}</td>)}{!sql && <td className={styles.number}><Share outage={row[outage]} capacity={row[capacity]} /></td>}</tr>)}</tbody></table></div>
}
