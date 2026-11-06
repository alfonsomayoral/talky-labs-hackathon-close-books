// Spanish labels and status colours for the Run's vocabulary (CONTRACT.md).
import type { AlertType, MatchStatus, ObjectKind, Severity } from '@/domain'
import type { Tone } from '@/components'

export const SEVERITY: Record<Severity, { label: string; tone: Tone }> = {
  high: { label: 'Alta', tone: 'danger' },
  medium: { label: 'Media', tone: 'warn' },
  low: { label: 'Baja', tone: 'info' },
}

export const SEVERITY_ORDER: Severity[] = ['high', 'medium', 'low']

export const ALERT_TYPE: Record<AlertType, string> = {
  bank_change: 'Cambio bancario',
  duplicate: 'Duplicado',
  tax_error: 'Error fiscal',
  po_mismatch: 'Pedido no cuadra',
  unmatched: 'Sin conciliar',
  other: 'Otro',
}

export const MATCH_STATUS: Record<MatchStatus, { label: string; tone: Tone }> = {
  matched: { label: 'Casada', tone: 'ok' },
  suggested: { label: 'Sugerida', tone: 'warn' },
  unmatched: { label: 'Sin casar', tone: 'danger' },
}

export const OBJECT_LABEL: Record<ObjectKind, string> = {
  entity: 'Sociedad',
  vendor: 'Proveedor',
  contract: 'Contrato',
  purchaseOrder: 'Orden de compra',
  invoice: 'Factura',
  bankTransaction: 'Transacción bancaria',
  ledgerEntry: 'Apunte',
  erpEvent: 'Evento del ERP',
}
