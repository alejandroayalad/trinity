import type { ReactNode } from 'react'
import styles from './PageHeader.module.css'

type PageHeaderProps = {
  title: ReactNode
  subtitle?: ReactNode
  aside?: ReactNode
  breadcrumb?: ReactNode
  mono?: boolean
  titleAddon?: ReactNode
}

/**
 * The top of a page: an optional breadcrumb, the 32px title, a muted
 * subtitle and an optional block on the right, such as a button or the
 * publication details. `mono` sets the title in the code font for run labels.
 * `titleAddon` sits beside the title, outside the heading, such as a status badge.
 */
export function PageHeader({ title, subtitle, aside, breadcrumb, mono = false, titleAddon }: PageHeaderProps) {
  return (
    <header className={styles.header}>
      <div className={styles.main}>
        {breadcrumb !== undefined && <div className={styles.breadcrumb}>{breadcrumb}</div>}
        <div className={styles.titleRow}>
          <h1 className={[styles.title, mono ? styles.mono : ''].join(' ')}>{title}</h1>
          {titleAddon}
        </div>
        {subtitle !== undefined && <p className={styles.subtitle}>{subtitle}</p>}
      </div>
      {aside !== undefined && <div className={styles.aside}>{aside}</div>}
    </header>
  )
}
