import type { ReactNode } from 'react'
import { Link } from 'react-router'
import styles from './ListTable.module.css'

type ListColumn = { header: string; track: string; align?: 'start' | 'end' }
type ListRow = { key: string; to: string; link: ReactNode; cells: ReactNode[] }

/**
 * A list of rows that each open one page, such as the catalog tables or the
 * refresh runs (spec UF-C03, UF-R03). The first cell holds the link. Its
 * ::after layer covers the whole row, so a click anywhere opens the page,
 * while the link's accessible name stays the short first-cell text.
 * `rowHeight` is 52px for the catalog and 50px for runs.
 */
export function ListTable({ label, columns, rows, rowHeight, empty }: { label: string; columns: ListColumn[]; rows: ListRow[]; rowHeight: 50 | 52; empty?: ReactNode }) {
  const template = `${columns.map((c) => c.track).join(' ')} 24px`
  const align = (index: number) => columns[index]?.align === 'end' ? styles.end : undefined
  return (
    <div className={styles.scroll}>
      <div className={styles.inner}>
        <div className={styles.head} style={{ gridTemplateColumns: template }} aria-hidden="true">
          {columns.map((c, i) => <span key={c.header} className={align(i)}>{c.header}</span>)}
          <span />
        </div>
        <ul aria-label={label} className={styles.list}>
          {rows.map((row) => (
            <li key={row.key} className={styles.row} style={{ gridTemplateColumns: template, height: `${rowHeight}px` }}>
              <Link to={row.to} className={styles.link}>{row.link}</Link>
              {row.cells.map((cell, i) => <span key={i} className={align(i + 1)}>{cell}</span>)}
              <span className={styles.arrow} aria-hidden="true">→</span>
            </li>
          ))}
        </ul>
        {rows.length === 0 && empty !== undefined && <p className={styles.empty}>{empty}</p>}
      </div>
    </div>
  )
}
