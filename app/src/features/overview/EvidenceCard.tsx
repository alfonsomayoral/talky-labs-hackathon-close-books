import { Card } from '@/components'
import { EVIDENCE_GROUP_LABEL, type RunStats } from '@/domain'
import { formatNumber, formatPercent } from '@/lib/format'
import { evidenceBreakdown } from './model'
import { RankList } from './RankList'
import styles from './EvidenceCard.module.css'

/** How every movement was resolved: the share with documents behind it, and the sources one by one. */
export function EvidenceCard({ byRule, total }: { byRule: RunStats['byRule']; total: number }) {
  const { groups, sources } = evidenceBreakdown(byRule, total)
  return (
    <Card padding="none">
      <div className={styles.groups}>
        {groups.map((g) => (
          <div key={g.group} className={styles.group}>
            <span className={styles.share}>{formatPercent(g.share, { decimals: 1 })}</span>
            <span className={styles.label}>{EVIDENCE_GROUP_LABEL[g.group]}</span>
            <span className={styles.count}>{formatNumber(g.txns)} movimientos</span>
          </div>
        ))}
      </div>
      <RankList rows={sources.map((s) => ({ key: s.source, label: s.source, value: s.txns, detail: formatPercent(s.share, { decimals: 1 }) }))} />
    </Card>
  )
}
