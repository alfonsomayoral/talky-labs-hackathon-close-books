import { Amount, Card, ProgressBar, Skeleton } from '@/components'
import { useAging } from '@/data'
import { AGING_BUCKETS, AGING_LABEL } from '@/domain'
import { agingSegments } from './model'
import styles from './AgingStrip.module.css'

/** What is owed to suppliers, by how late it is. EUR cents. */
export function AgingStrip({ runId, entity }: { runId: string; entity: string | null }) {
  const { data, error } = useAging(runId, entity, 'supplier')

  return (
    <Card title="Saldo total a proveedores por tramos" description={error && !data ? 'No se ha podido cargar el saldo.' : 'Todas las partidas abiertas, no solo las de incidencias.'}>
      {data ? (
        <div className={styles.strip}>
          <ProgressBar size="sm" segments={agingSegments(data.totals)} label="Saldo a proveedores por tramos" />
          <dl className={styles.buckets}>
            {AGING_BUCKETS.map((b) => (
              <div key={b} className={styles.bucket}>
                <dt>{AGING_LABEL[b]}</dt>
                <dd>
                  <Amount cents={data.totals[b]} currency="EUR" compact />
                </dd>
              </div>
            ))}
          </dl>
        </div>
      ) : error ? null : (
        <Skeleton height={48} />
      )}
    </Card>
  )
}
