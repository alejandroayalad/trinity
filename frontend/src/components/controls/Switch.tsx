import styles from './Switch.module.css'

type SwitchProps = { checked: boolean; onChange: (checked: boolean) => void; labelledBy: string; disabled?: boolean }

/** An on/off control with role="switch". Space and Enter toggle it, as for any button. */
export function Switch({ checked, onChange, labelledBy, disabled = false }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-labelledby={labelledBy}
      disabled={disabled}
      className={styles.switch}
      onClick={() => onChange(!checked)}
    >
      <span className={styles.knob} />
    </button>
  )
}
