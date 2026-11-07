import { Badge, Tooltip } from '@/components'
import { CATEGORY_DESCRIPTION, EXCEPTION_DEFINITION, categoryLabel, exceptionLabel } from '@/domain'
import styles from './Terms.module.css'

/** An exception of the closed list: its Spanish name, with the code and definition in a tooltip. */
export function ExceptionTerm({ exception, badge }: { exception: string; badge?: boolean }) {
  const label = exceptionLabel(exception)
  return (
    <Tooltip content={`${exception}: ${EXCEPTION_DEFINITION[exception] ?? label}`}>
      <span className={styles.term} tabIndex={0}>
        {badge ? <Badge emphasis="medium">{label}</Badge> : label}
      </span>
    </Tooltip>
  )
}

/** A category of the master: its short name, with the code and description in a tooltip. */
export function CategoryTerm({ category }: { category: string }) {
  return (
    <Tooltip content={`${category}: ${CATEGORY_DESCRIPTION[category] ?? categoryLabel(category)}`}>
      <span className={styles.term} tabIndex={0}>
        {categoryLabel(category)}
      </span>
    </Tooltip>
  )
}
