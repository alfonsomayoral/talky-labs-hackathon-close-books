import { useId } from 'react'
import clsx from 'clsx'
import styles from './TextField.module.css'

interface TextFieldProps {
  label: string
  /** The label stays for assistive tech but is not drawn (a search box, a one-line note). */
  hideLabel?: boolean
  value: string
  onChange: (value: string) => void
  /** Renders a textarea with this many rows. */
  rows?: number
  placeholder?: string
  readOnly?: boolean
  type?: 'text' | 'search'
  className?: string
}

/** Labelled text input or textarea for the forms of the screens. */
export function TextField({ label, hideLabel, value, onChange, rows, placeholder, readOnly, type = 'text', className }: TextFieldProps) {
  const id = useId()
  const props = { id, value, placeholder, readOnly, onChange: (e: { target: { value: string } }) => onChange(e.target.value) }
  return (
    <div className={clsx(styles.field, className)}>
      <label htmlFor={id} className={hideLabel ? styles.hidden : styles.label}>
        {label}
      </label>
      {rows ? <textarea {...props} rows={rows} className={styles.control} /> : <input {...props} type={type} className={styles.control} />}
    </div>
  )
}
