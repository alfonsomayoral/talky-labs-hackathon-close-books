// One entity of the group as a card: what it holds and how far its bank reconciliation got. Opens its scope.
import { ArrowRight } from 'lucide-react'
import { Badge, Mono } from '@/components'
import type { Dataset, Entity, Run } from '@/domain'
import { formatNumber, formatPercent } from '@/lib/format'
import type { MatchCounts } from '@/features/overview/model'
import { ReconBar } from './ReconBar'
import styles from './EntityCard.module.css'

export function EntityCard({ entity, dataset, run, counts, onOpen, openLabel = 'Filtrar por esta sociedad' }: { entity: Entity; dataset: Dataset; run: Run | null; counts: MatchCounts; onOpen: () => void; openLabel?: string }) {
  const alerts = run?.alerts.filter((a) => a.entityId === entity.id).length ?? 0
  const invoices = dataset.invoices.filter((i) => i.entityId === entity.id).length
  const vendors = dataset.vendors.filter((v) => v.entityId === entity.id).length
  return (
    <button type="button" className={styles.card} onClick={onOpen}>
      <div className={styles.top}>
        <Mono muted>{entity.id}</Mono>
        <span className={styles.meta}>
          {entity.country} · {entity.currency}
        </span>
      </div>
      <div className={styles.name}>{entity.name}</div>
      <div className={styles.role}>{entity.parentId ? `Dependiente de ${entity.parentId}` : 'Cabecera del grupo'}</div>
      <dl className={styles.stats}>
        <div>
          <dt>Facturas</dt>
          <dd>{formatNumber(invoices)}</dd>
        </div>
        <div>
          <dt>Proveedores</dt>
          <dd>{formatNumber(vendors)}</dd>
        </div>
        <div>
          <dt>Movimientos</dt>
          <dd>{formatNumber(counts.total)}</dd>
        </div>
      </dl>
      <div className={styles.recon}>
        <div className={styles.reconHead}>
          <span>Conciliación</span>
          <span className={styles.reconValue}>{run && counts.total ? formatPercent(counts.matched / counts.total) : '—'}</span>
        </div>
        <ReconBar counts={counts} size="sm" />
      </div>
      <div className={styles.foot}>
        {run ? alerts > 0 ? <Badge tone="warn">{`${alerts} ${alerts === 1 ? 'alerta' : 'alertas'}`}</Badge> : <Badge tone="ok">Sin alertas</Badge> : <Badge>Sin ejecución</Badge>}
        <span className={styles.open}>
          {openLabel} <ArrowRight aria-hidden />
        </span>
      </div>
    </button>
  )
}
