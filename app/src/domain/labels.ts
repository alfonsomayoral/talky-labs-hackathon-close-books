// Spanish names of the contract's closed vocabularies, and the derived values every screen shares.
import type { CaseKind, CaseStatus, CasePriority } from './run'
import type { AgingBucket, RunStats } from './api'

export const CASE_KIND_LABEL: Record<CaseKind, string> = {
  unidentified_receipt: 'Cobro sin identificar',
  ambiguous_match: 'Casación ambigua',
  dispute: 'Disputa',
  short_payment: 'Pago parcial sin explicar',
  duplicate_payment: 'Pago duplicado',
  overpayment: 'Sobrepago',
  returned: 'Devolución',
  fx_difference: 'Diferencia de cambio',
  supplier_invoice_mismatch: 'Factura de proveedor con incidencia',
  supplier_credit_pending: 'Abono de proveedor pendiente',
  unknown_debit: 'Cargo sin identificar',
  overdue_customer: 'Cliente con saldo vencido',
  new_bank_details: 'Datos bancarios nuevos',
}

export const CASE_STATUS_LABEL: Record<CaseStatus, string> = {
  auto: 'Automático',
  needs_review: 'Por revisar',
  question: 'Pregunta',
  fallback: 'Sin casación',
  done: 'Gestionado',
}

export const CASE_STATUS_TONE: Record<CaseStatus, 'ok' | 'warn' | 'info' | 'danger' | 'neutral'> = {
  auto: 'ok',
  needs_review: 'warn',
  question: 'info',
  fallback: 'danger',
  done: 'neutral',
}

export const PRIORITY_LABEL: Record<CasePriority, string> = { 1: 'Alta', 2: 'Media', 3: 'Baja' }

export const INBOX_STATUSES: CaseStatus[] = ['needs_review', 'question', 'fallback']

export const AGING_BUCKETS: AgingBucket[] = ['not_due', 'd1_30', 'd31_60', 'd61_90', 'd90_plus']

export const AGING_LABEL: Record<AgingBucket, string> = {
  not_due: 'No vencido',
  d1_30: '1–30 días',
  d31_60: '31–60 días',
  d61_90: '61–90 días',
  d90_plus: 'Más de 90 días',
}

export const EXCEPTION_LABEL: Record<string, string> = {
  SHORT_DISCOUNT: 'Pronto pago',
  SHORT_DISPUTE: 'Disputa',
  SHORT_WITHHOLDING: 'Retención',
  SHORT_BANK_CHARGES: 'Comisión bancaria',
  PARTIAL: 'Pago parcial',
  OVERPAYMENT: 'Sobrepago',
  DUPLICATE_PAYMENT: 'Pago duplicado',
  RETURNED: 'Devuelto',
  FX_DIFFERENCE: 'Diferencia de cambio',
  UNIDENTIFIED: 'Sin identificar',
}

/** Short names of the categories in masters/categories.csv; the master's description is the long form. */
export const CATEGORY_LABEL: Record<string, string> = {
  BANK_FEES: 'Comisiones bancarias',
  INTEREST_INCOME: 'Intereses a favor',
  INTEREST_EXPENSE: 'Intereses de deudas',
  PAYROLL: 'Nóminas',
  SOCIAL_SECURITY: 'Seguridad social',
  TAX_PAYMENT: 'Impuestos',
  TAX_REFUND: 'Devolución de impuestos',
  LOAN_DRAWDOWN: 'Disposición de préstamo',
  LOAN_REPAYMENT: 'Cuota de préstamo',
  LEASING: 'Leasing',
  FX_DEAL: 'Compraventa de divisa',
  CASH_POOL: 'Cash pooling',
  INTERCOMPANY: 'Intragrupo',
  INTERNAL_TRANSFER: 'Traspaso entre cuentas',
  CUSTOMER_ADVANCE: 'Anticipo de cliente',
  CUSTOMER_REFUND: 'Devolución a cliente',
  SUPPLIER_REFUND: 'Reembolso de proveedor',
  CARD_EXPENSES: 'Tarjetas de empresa',
  INSURANCE: 'Seguros',
  BANK_REVERSAL: 'Apunte erróneo del banco',
  UNIDENTIFIED: 'Sin identificar',
}

/** Unknown values stay readable: the vocabulary may grow with the contract. */
export const exceptionLabel = (exception: string) => EXCEPTION_LABEL[exception] ?? exception
export const categoryLabel = (category: string) => CATEGORY_LABEL[category] ?? category
export const caseKindLabel = (kind: string) => CASE_KIND_LABEL[kind as CaseKind] ?? kind

/** Share of movements closed with no intervention, 0..1. */
export const autoRate = (s: Pick<RunStats, 'txns' | 'txnsAuto'>) => (s.txns > 0 ? s.txnsAuto / s.txns : null)
