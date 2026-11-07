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

const RULE_DESCRIPTION: Record<string, string> = {
  'FILE-DD-BATCH': 'Remesa de recibos: el fichero dice qué facturas cobra',
  'FILE-DD-RETURN': 'Recibo devuelto: el fichero de la remesa dice cuál',
  'FILE-CARD': 'Liquidación de tarjetas: el fichero dice qué ventas paga',
  'FILE-CARD-CHARGEBACK': 'Contracargo de tarjeta, según el fichero de liquidación',
  'FILE-CHEQUE': 'Ingreso de cheques: el fichero dice qué facturas cobra',
  'FILE-CHEQUE-RETURN': 'Cheque devuelto, según el fichero del ingreso',
  'FILE-PAYMENT-RUN': 'Remesa de pagos: el fichero dice qué facturas de proveedor paga',
  'FILE-PAYMENT-RETURN': 'Transferencia a proveedor devuelta por el banco',
  'REF-TEXT': 'El texto del banco cita los números de factura',
  'REF-NUMBER': 'El texto cita el número entero y el importe cuadra, aunque no se reconozca al tercero',
  'REF-SUBSET': 'Las facturas citadas en el texto suman el importe del movimiento',
  'REF-COMPLETED': 'El texto cita parte de las facturas; las demás completan el importe',
  'PARTY-AMOUNT': 'Sin referencia: una partida abierta del tercero tiene ese importe; si hay varias, la del mes citado o la más antigua',
  'PARTY-SUBSET': 'Sin referencia: varias partidas abiertas del tercero suman ese importe',
  'PARTY-SHORT': 'Sin referencia: el importe es una factura del tercero menos su descuento, retención o comisión',
  'PARTY-BLOCK': 'Sin referencia: facturas consecutivas del tercero suman ese importe',
  'PARTY-PLAN': 'Sin referencia: el importe es el que dice el PDF de la factura (plazo, retención o anticipo)',
  'CAT-CODE': 'Sin partida: la categoría sale del código del banco',
  'CAT-TEXT': 'Sin partida: la categoría sale del texto del movimiento',
  'CAT-SUPPLIER-REFUND': 'Reembolso de un proveedor que liquida su abono',
  'FALLBACK-UNIDENTIFIED': 'Sin evidencia: se deja como cobro sin identificar, no se fuerza',
  'FALLBACK-CATEGORY': 'Sin evidencia de partida: la categoría más frecuente de su código',
  'MEMORY-RULE': 'Aplicada una regla que enseñó una persona',
}

const RULE_FAMILY: Record<string, string> = {
  ADVICE: 'Aviso de remesa: el documento del cliente dice qué paga',
  FILE: 'Fichero de detalle: dice qué partidas liquida',
  REF: 'Referencia: el texto del banco cita la partida',
  PARTY: 'Tercero e importe: sin referencia, cuadra con sus partidas abiertas',
  HISTORY: 'Historia de la partida: pago repetido o reabierto',
  CAT: 'Sin partida: categoría del movimiento',
  FALLBACK: 'Sin evidencia: no se fuerza ninguna casación',
}

/** What a rule means, for a tooltip next to its code. The family covers rules this list does not know yet. */
export const ruleDescription = (rule: string): string | undefined => RULE_DESCRIPTION[rule] ?? RULE_FAMILY[rule.split('-')[0]]

const PARTY_HOW_LABEL: Record<string, string> = {
  counterparty: 'Por el nombre del ordenante',
  iban: 'Por el IBAN del ordenante',
  name: 'Por parecido del nombre',
  mandate: 'Por el mandato del recibo',
  group: 'Por el grupo del cliente',
  confirming: 'Por el confirming',
  agency: 'Por la agencia que paga',
  factor: 'Por el factor que paga',
  file: 'Por un fichero de detalle',
  advice: 'Por un aviso de remesa',
  memoryRule: 'Por una regla de memoria',
}

export const partyHowLabel = (how: string) => PARTY_HOW_LABEL[how] ?? how
