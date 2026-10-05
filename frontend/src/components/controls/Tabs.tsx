import { useRef, type KeyboardEvent } from 'react'
import styles from './Tabs.module.css'

type Tab<T extends string> = { value: T; label: string }

type TabsProps<T extends string> = {
  label: string
  idPrefix: string
  tabs: readonly Tab<T>[]
  value: T
  onChange: (value: T) => void
}

/**
 * Text tabs that follow the WAI-ARIA tabs pattern. Only the selected tab is
 * in the Tab order; ← and → move to the next tab and select it. The panel
 * uses the id `${idPrefix}-panel` and is labelled by the selected tab.
 */
export function Tabs<T extends string>({ label, idPrefix, tabs, value, onChange }: TabsProps<T>) {
  const buttons = useRef<(HTMLButtonElement | null)[]>([])

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return
    event.preventDefault()
    const step = event.key === 'ArrowRight' ? 1 : -1
    const next = (index + step + tabs.length) % tabs.length
    onChange(tabs[next].value)
    buttons.current[next]?.focus()
  }

  return (
    <div role="tablist" aria-label={label} className={styles.list}>
      {tabs.map((tab, index) => {
        const selected = tab.value === value
        return (
          <button
            key={tab.value}
            ref={(element) => {
              buttons.current[index] = element
            }}
            id={`${idPrefix}-tab-${tab.value}`}
            type="button"
            role="tab"
            className={styles.tab}
            aria-selected={selected}
            aria-controls={`${idPrefix}-panel`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(tab.value)}
            onKeyDown={(event) => onKeyDown(event, index)}
          >
            {tab.label}
          </button>
        )
      })}
    </div>
  )
}
