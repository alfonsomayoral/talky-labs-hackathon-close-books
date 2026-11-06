import { useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'
import type { DayStats } from '@/domain'
import { formatDate, formatMonth, formatNumber, formatPercent } from '@/lib/format'
import { dayChart, monthTicks, nearestIndex } from './model'
import styles from './DayChart.module.css'

const HEIGHT = 200
const GAP = 2

/** Movements per day: closed alone (green) stacked under those that went to the queue (amber). */
export function DayChart({ byDay }: { byDay: DayStats[] }) {
  const { days, max } = dayChart(byDay)
  const [active, setActive] = useState<number | null>(null)
  const plot = useRef<HTMLDivElement>(null)
  const n = days.length
  const scale = (HEIGHT - 1) / max
  const shown = active != null ? days[active] : null

  const onMove = (e: PointerEvent) => {
    const box = plot.current?.getBoundingClientRect()
    if (box) setActive(nearestIndex(e.clientX - box.left, box.width, n))
  }
  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      e.preventDefault()
      setActive((i) => Math.min(n - 1, Math.max(0, (i ?? (e.key === 'ArrowLeft' ? n : -1)) + (e.key === 'ArrowLeft' ? -1 : 1))))
    }
  }

  return (
    <div className={styles.chart}>
      <ul className={styles.legend}>
        <li>
          <span className={styles.key} style={{ background: 'var(--brand)' }} aria-hidden />
          Cerrados sin intervención
        </li>
        <li>
          <span className={styles.key} style={{ background: 'var(--warn)' }} aria-hidden />
          A la cola de revisión
        </li>
      </ul>
      <div className={styles.frame}>
        <div className={styles.yAxis} aria-hidden>
          <span>{formatNumber(max)}</span>
          <span>{formatNumber(Math.round(max / 2))}</span>
          <span>0</span>
        </div>
        <div
          ref={plot}
          className={styles.plot}
          style={{ height: HEIGHT }}
          tabIndex={0}
          role="img"
          aria-label={`Movimientos por día, ${n} días. Flechas izquierda y derecha para recorrerlos.`}
          onPointerMove={onMove}
          onPointerLeave={() => setActive(null)}
          onKeyDown={onKey}
          onBlur={() => setActive(null)}
        >
          <svg className={styles.svg} viewBox={`0 0 ${n} ${HEIGHT}`} preserveAspectRatio="none" aria-hidden>
            {[0.5, 1].map((f) => (
              <line key={f} className={styles.grid} x1={0} x2={n} y1={HEIGHT - (HEIGHT - 1) * f} y2={HEIGHT - (HEIGHT - 1) * f} vectorEffect="non-scaling-stroke" />
            ))}
            {active != null && <rect className={styles.band} x={active} y={0} width={1} height={HEIGHT} />}
            {days.map((d, i) => {
              const auto = d.auto * scale
              const queue = d.queue * scale
              const gap = auto > 0 && queue > 0 ? GAP / 2 : 0
              return (
                <g key={d.date}>
                  {auto > 0 && <rect x={i + 0.15} y={HEIGHT - auto} width={0.7} height={auto} fill="var(--brand)" />}
                  {queue > 0 && <rect x={i + 0.15} y={HEIGHT - auto - queue} width={0.7} height={Math.max(queue - gap, 0)} fill="var(--warn)" />}
                </g>
              )
            })}
            <line className={styles.base} x1={0} x2={n} y1={HEIGHT} y2={HEIGHT} vectorEffect="non-scaling-stroke" />
          </svg>
          {shown && active != null && (
            <div className={styles.tip} style={{ left: `${((active + 0.5) / n) * 100}%` }} data-flip={active > n * 0.7 || undefined}>
              <strong>{formatDate(shown.date)}</strong>
              <span>
                {formatNumber(shown.auto + shown.queue)} movimientos
                {shown.auto + shown.queue > 0 && ` · ${formatPercent(shown.auto / (shown.auto + shown.queue), { decimals: 0 })} sin intervención`}
              </span>
              <span className={styles.tipRow}>
                <i style={{ background: 'var(--brand)' }} aria-hidden />
                {formatNumber(shown.auto)} cerrados
              </span>
              <span className={styles.tipRow}>
                <i style={{ background: 'var(--warn)' }} aria-hidden />
                {formatNumber(shown.queue)} a la cola
              </span>
            </div>
          )}
          <div className={styles.xAxis} aria-hidden>
            {monthTicks(days).map((t) => (
              <span key={t.month} style={{ left: `${(t.index / n) * 100}%` }}>
                {formatMonth(t.month)}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
