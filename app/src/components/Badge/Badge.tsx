import type { HTMLAttributes, ReactNode } from 'react'
import clsx from 'clsx'
import { toneColor, type Emphasis, type Tone } from '../status'
import styles from './Badge.module.css'

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone
  /** `soft` (tinted fill) for status, `outline` for quieter metadata. */
  variant?: 'soft' | 'outline'
  /** Rank of a priority, status or risk: `strong` filled, `medium` outlined, `quiet` text only. Replaces `tone` and `variant`. */
  emphasis?: Emphasis
  /** Leading coloured dot (use with `outline`). */
  dot?: boolean
  icon?: ReactNode
  children: ReactNode
}

/** Small rectangular label for a state or category. */
export function Badge({ tone = 'neutral', variant = 'soft', emphasis, dot, icon, className, children, ...rest }: BadgeProps) {
  return (
    <span className={clsx(styles.badge, emphasis ? styles[emphasis] : styles[variant], className)} data-tone={emphasis ? undefined : tone} {...rest}>
      {dot && <span className={styles.dot} style={{ background: toneColor(tone) }} aria-hidden />}
      {icon}
      <span className={styles.text}>{children}</span>
    </span>
  )
}
