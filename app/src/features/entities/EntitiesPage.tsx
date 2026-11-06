// Sociedades: few objects, each the door to its own scope, so they are cards rather than a table.
import { refKey, useData } from '@/data'
import { matchCountsByEntity } from '@/features/overview/model'
import { formatNumber } from '@/lib/format'
import { useEntityScope, useOpenObject } from '@/lib/urlState'
import { EntityCard } from './EntityCard'
import styles from './EntitiesPage.module.css'

export function EntitiesPage() {
  const dataset = useData((s) => s.dataset)!
  const run = useData((s) => s.run)
  const [entity] = useEntityScope()
  const [, open] = useOpenObject()
  const byEntity = matchCountsByEntity(dataset, run)
  const entities = entity ? dataset.entities.filter((e) => e.id === entity) : dataset.entities
  const currencies = [...new Set(dataset.entities.map((e) => e.currency))]
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>Sociedades</h1>
        <p className={styles.sub}>
          {formatNumber(dataset.entities.length)} sociedades en {formatNumber(new Set(dataset.entities.map((e) => e.country)).size)} países, con {currencies.join(' y ')} como monedas de sus libros. Cada tarjeta abre la ficha de la sociedad.
        </p>
      </header>
      <div className={styles.grid}>
        {entities.map((e) => (
          <EntityCard key={e.id} entity={e} dataset={dataset} run={run} counts={byEntity.get(e.id)!} onOpen={() => open(refKey({ kind: 'entity', id: e.id }))} openLabel="Ver ficha" />
        ))}
      </div>
    </div>
  )
}
