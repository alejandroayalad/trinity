import styles from './BrandLockup.module.css'

type BrandLockupProps = { size: 'nav' | 'signin' }

/**
 * The Trinity logo: the orange mark, the letter wordmark and a small
 * uppercase caption. `nav` is the sidebar size; `signin` is the larger card
 * size. The caption text differs per size, as in the handoff.
 */
export function BrandLockup({ size }: BrandLockupProps) {
  return (
    <div className={[styles.lockup, styles[size]].join(' ')}>
      <img src="/brand/mark-orange.png" alt="" className={styles.mark} />
      <span className={styles.words}>
        <img src="/brand/wordmark-letters.png" alt="Trinity" className={styles.letters} />
        <span className={styles.caption}>{size === 'nav' ? 'Outage Explorer' : 'Nuclear Outage Explorer'}</span>
      </span>
    </div>
  )
}
