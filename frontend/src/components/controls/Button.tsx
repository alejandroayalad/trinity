import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Link, type LinkProps } from 'react-router'
import styles from './Button.module.css'

type Variant = 'primary' | 'secondary' | 'destructive' | 'destructiveSolid'
type Size = 'default' | 'compact' | 'small' | 'full'

function classes(variant: Variant, size: Size, extra?: string): string {
  return [
    styles.button,
    variant === 'secondary' ? '' : styles[variant],
    size === 'default' ? '' : styles[size],
    extra ?? '',
  ]
    .filter(Boolean)
    .join(' ')
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size }

/** A native button with the handoff styles. Disabled buttons keep their label and show not-allowed. */
export function Button({ variant = 'secondary', size = 'default', className, type = 'button', ...props }: ButtonProps) {
  return <button type={type} className={classes(variant, size, className)} {...props} />
}

type ButtonLinkProps = LinkProps & { variant?: Variant; size?: Size; children: ReactNode }

/** A router link that looks like a button, for navigation such as "Go to Refresh". */
export function ButtonLink({ variant = 'secondary', size = 'default', className, ...props }: ButtonLinkProps) {
  return <Link className={classes(variant, size, className)} {...props} />
}

/** An underlined text link for in-page navigation such as "← Refresh". */
export function TextLink({ className, ...props }: LinkProps) {
  return <Link className={[styles.link, className ?? ''].join(' ')} {...props} />
}

/** An underlined text button for actions that do not navigate. */
export function TextButton({ className, type = 'button', ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button type={type} className={[styles.link, className ?? ''].join(' ')} {...props} />
}
