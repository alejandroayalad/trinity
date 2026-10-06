import type { Cell, Column, Diagnostic } from '../api/types'
import { isApiError } from '../api/client'
import { Button } from '../components/controls/Button'
import { MissingChip } from '../components/feedback/StatusBadge'
import { ErrorState } from '../components/feedback/States'
import { Callout } from '../components/feedback/Callout'
import { Waiting } from './unavailable/Waiting'
import { formatExact, formatFixed, isOutOfRange, offlineShare, parseDecimal } from '../lib/decimal'

/**
 * A failed read. `data_unavailable` is a server state with its own Waiting
 * screen. Every other error can offer a Retry when the caller can refetch.
 */
export function PageError({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  if (isApiError(error, 'data_unavailable')) return <Waiting />
  return <div className="stack"><ErrorState error={error} />{onRetry !== undefined && <Button onClick={onRetry}>Retry</Button>}</div>
}
// Show only review warnings. A review warning has severity 'warning' and
// affected_count above zero. The backend counts warnings with the same rule.
// The candidate API also returns passed checks with affected_count '0'.
// Counter text is canonical, so '0' is the only text for zero.
export function Diagnostics({ diagnostics }: { diagnostics: Diagnostic[] }) {
  return <>{diagnostics.filter((d) => d.severity === 'warning' && d.affected_count !== '0').map((d) => <Callout key={d.code + d.scope} tone="warning" title={d.code}>{d.message}</Callout>)}</>
}
export function Share({ outage, capacity }: { outage: Cell | undefined; capacity: Cell | undefined }) {
  if (typeof outage !== 'string' || typeof capacity !== 'string') return <MissingChip />
  const share = offlineShare(parseDecimal(outage), parseDecimal(capacity))
  if (share.kind !== 'value') return <>Unavailable</>
  return <span>{formatFixed(share.value, 2)}%{isOutOfRange(share.value) && <span title="Outside 0–100%"> ⚠ Out of range</span>}</span>
}
const labels: Record<string, string> = { period: 'Day', facility: 'Facility ID', facilityName: 'Facility', generator: 'Unit', capacity: 'Capacity MW', outage: 'Outage MW', percentOutage: 'Source %' }
export function DataTable({ columns, rows, sql = false }: { columns: Column[]; rows: Cell[][]; sql?: boolean }) {
  const outage = columns.findIndex((c) => c.name === 'outage')
  const capacity = columns.findIndex((c) => c.name === 'capacity')
  return <div className="table-scroll" tabIndex={0} role="region" aria-label={sql ? 'SQL results' : 'Dataset rows'}><table><thead><tr>{columns.map((c) => <th key={c.name}>{sql ? c.name : labels[c.name] ?? c.name}{sql && c.unit ? ` (${c.unit})` : ''}</th>)}{!sql && <th>Offline share</th>}</tr></thead>
    <tbody>{rows.map((row, index) => <tr key={index}>{row.map((cell, i) => <td key={i}>{cell === null ? <MissingChip label={sql ? 'NULL' : undefined} /> : typeof cell === 'string' && columns[i].type === 'decimal' && !sql ? formatExact(cell) : String(cell)}</td>)}{!sql && <td><Share outage={row[outage]} capacity={row[capacity]} /></td>}</tr>)}</tbody></table></div>
}
