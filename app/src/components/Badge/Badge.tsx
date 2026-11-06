import type { HTMLAttributes, ReactNode } from 'react'
import clsx from 'clsx'
import { toneColor, type Tone } from '../status'
import styles from './Badge.module.css'

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone
  /** `soft` (tinted fill) for status, `outline` for quieter metadata. */
  variant?: 'soft' | 'outline'
  /** Leading coloured dot (use with `outline`). */
  dot?: boolean
  icon?: ReactNode
  children: ReactNode
}

/** Small rectangular label for a state or category. */
export function Badge({ tone = 'neutral', variant = 'soft', dot, icon, className, children, ...rest }: BadgeProps) {
  return (
    <span className={clsx(styles.badge, styles[variant], className)} data-tone={tone} {...rest}>
      {dot && <span className={styles.dot} style={{ background: toneColor(tone) }} aria-hidden />}
      {icon}
      <span className={styles.text}>{children}</span>
    </span>
  )
}
