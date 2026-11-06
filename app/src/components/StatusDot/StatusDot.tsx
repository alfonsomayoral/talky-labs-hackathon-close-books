import clsx from 'clsx'
import { toneColor, type Tone } from '../status'
import styles from './StatusDot.module.css'

export interface StatusDotProps {
  tone?: Tone
  /** Accessible label. Omit for purely decorative dots next to text. */
  label?: string
  /** Soft halo animation for "in progress". */
  pulse?: boolean
  className?: string
}

export function StatusDot({ tone = 'neutral', label, pulse, className }: StatusDotProps) {
  const t = tone
  const name = label
  return (
    <span
      className={clsx(styles.dot, pulse && styles.pulse, className)}
      style={{ ['--dot-color' as string]: toneColor(t) }}
      role={name ? 'img' : undefined}
      aria-label={name}
      aria-hidden={name ? undefined : true}
      title={name}
    />
  )
}
