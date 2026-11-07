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

export const CASE_STATUS_EMPHASIS: Record<CaseStatus, 'positive' | 'strong' | 'medium' | 'quiet'> = {
  auto: 'positive',
  needs_review: 'medium',
  question: 'strong',
  fallback: 'strong',
  done: 'quiet',
}

/** A closed movement that still has an email to write is not done: the system opened that case on its own. */
export function caseStatusBadge(c: { status: CaseStatus; suggestedAction: string }) {
  if (c.status === 'auto' && c.suggestedAction.startsWith('email_')) return { label: 'Abierto por el sistema', emphasis: 'medium' as const }
  return { label: CASE_STATUS_LABEL[c.status], emphasis: CASE_STATUS_EMPHASIS[c.status] }
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

/** The closed list of POLICIES.md §3, for a tooltip next to the label. */
export const EXCEPTION_DEFINITION: Record<string, string> = {
  PARTIAL: 'Tras este pago la partida sigue con saldo abierto y no aplica ninguna otra razón: pago a cuenta, plazo que no es el último, retención de garantía o anticipo por deducir.',
  SHORT_DISCOUNT: 'Descuento por pronto pago dentro de plazo: la factura se liquida completa.',
  SHORT_BANK_CHARGES: 'Un banco intermediario descontó su comisión en una transferencia de fuera de SEPA: hasta 60 EUR y 2 % de la partida. La factura se liquida completa.',
  SHORT_WITHHOLDING: 'El cliente retuvo impuestos en origen: el certificado cubre la diferencia y la factura se liquida completa.',
  SHORT_DISPUTE: 'El cliente descontó un importe con un motivo declarado: el importe es lo pagado y la parte disputada sigue abierta.',
  OVERPAYMENT: 'El cliente pagó más que el saldo de una factura: se liquida completa y el exceso queda en su cuenta.',
  DUPLICATE_PAYMENT: 'La partida ya estaba liquidada y se paga otra vez: la excepción va en el pago posterior.',
  RETURNED: 'Un cobro o un pago vuelve y reabre la partida: recibo devuelto, cheque devuelto, contracargo o transferencia rechazada.',
  UNIDENTIFIED: 'Cobro para el que no existe partida abierta: no se fuerza ninguna casación, aunque el importe coincida con otra factura.',
  FX_DIFFERENCE: 'El movimiento va en otra divisa que la factura: el banco convierte a su tipo y la diferencia con el de referencia no es un pago parcial.',
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

/** The descriptions of masters/categories.csv. */
export const CATEGORY_DESCRIPTION: Record<string, string> = {
  BANK_FEES: 'Comisiones y gastos bancarios',
  INTEREST_INCOME: 'Intereses a favor',
  INTEREST_EXPENSE: 'Intereses de deudas o descubiertos',
  PAYROLL: 'Nóminas (remesa de transferencias)',
  SOCIAL_SECURITY: 'Seguridad social y cargas sociales',
  TAX_PAYMENT: 'Impuestos (IVA, retenciones, sociedades)',
  TAX_REFUND: 'Devolución de impuestos',
  LOAN_DRAWDOWN: 'Disposición de préstamo o póliza',
  LOAN_REPAYMENT: 'Cuota de préstamo (capital e intereses)',
  LEASING: 'Cuota de leasing o renting financiero',
  FX_DEAL: 'Compraventa de divisa o liquidación de forward',
  CASH_POOL: 'Barrido de cash pooling (cabecera y filial)',
  INTERCOMPANY: 'Transferencia intragrupo (no comercial)',
  INTERNAL_TRANSFER: 'Traspaso entre cuentas propias de la misma sociedad',
  CUSTOMER_ADVANCE: 'Anticipo de cliente sin factura (por ejemplo, pago de proforma)',
  CUSTOMER_REFUND: 'Devolución de dinero a cliente (saldo a favor)',
  SUPPLIER_REFUND: 'Reembolso de proveedor sin abono asociado (por ejemplo, pago duplicado nuestro)',
  CARD_EXPENSES: 'Liquidación de tarjetas de empresa',
  INSURANCE: 'Primas de seguros',
  BANK_REVERSAL: 'Apunte erróneo del banco y su anulación',
  UNIDENTIFIED: 'Cobro no identificado (no existe partida)',
}

const STATEMENT_FORMAT_LABEL: Record<string, string> = { n43: 'Norma 43', mt940: 'MT940', camt053: 'camt.053' }

export const statementFormatLabel = (format: string) => STATEMENT_FORMAT_LABEL[format] ?? format

/** The scorer's kinds of movement. */
const SEGMENT_LABEL: Record<string, string> = {
  ap_confirming: 'Pago por confirming',
  ap_credit_note_netted: 'Pago con abono compensado',
  ap_direct_debit: 'Proveedor por adeudo',
  ap_duplicate_payment: 'Pago duplicado a proveedor',
  ap_duplicate_refund: 'Reembolso de pago duplicado',
  ap_factored: 'Factura de proveedor cedida',
  ap_fx: 'Pago en otra divisa',
  ap_paid_by_holding: 'Pago por la matriz',
  ap_partial: 'Pago parcial a proveedor',
  ap_payment_multi: 'Pago de varias facturas',
  ap_payment_single: 'Pago de una factura',
  ap_returned_transfer: 'Transferencia devuelta',
  ap_supplier_refund: 'Reembolso de proveedor',
  ar_1to1: 'Cobro de una factura',
  ar_1to1_remittance: 'Cobro de una factura con aviso',
  ar_1toN_credit_note: 'Cobro de varias con abono',
  ar_1toN_remittance: 'Cobro de varias con aviso',
  ar_1toN_text: 'Cobro de varias citadas en el texto',
  ar_advance_deduction: 'Cobro con anticipo deducido',
  ar_card_chargeback: 'Contracargo de tarjeta',
  ar_card_settlement: 'Liquidación de tarjetas',
  ar_cheque_deposit: 'Ingreso de cheques',
  ar_cheque_returned: 'Cheque devuelto',
  ar_credit_note_paid_out: 'Abono pagado al cliente',
  ar_dd_batch: 'Remesa de recibos',
  ar_dd_represented_transfer: 'Recibo pagado de nuevo por transferencia',
  ar_dd_returned: 'Recibo devuelto',
  ar_discount_late: 'Descuento fuera de plazo',
  ar_dispute_settlement: 'Liquidación de una disputa',
  ar_duplicate_payment: 'Cobro duplicado',
  ar_fx: 'Cobro en otra divisa',
  ar_instalment: 'Cobro a plazos',
  ar_n_to_m: 'Varios cobros, varias facturas',
  ar_new_iban: 'Cobro desde un IBAN nuevo',
  ar_overpayment: 'Sobrepago',
  ar_partial: 'Cobro parcial',
  ar_ref_noise: 'Cobro con referencia ruidosa',
  ar_replaced_invoice: 'Factura anulada y sustituida',
  ar_retention: 'Cobro con retención de garantía',
  ar_retention_release: 'Liberación de la retención',
  ar_same_amount_fifo: 'Mismo importe, la más antigua',
  ar_same_amount_month: 'Mismo importe, según el mes',
  ar_short_bank_charges: 'Comisión descontada por el banco',
  ar_short_discount: 'Pronto pago',
  ar_short_dispute: 'Disputa',
  ar_short_withholding: 'Retención de impuestos',
  ar_third_party_agency: 'Paga una agencia',
  ar_third_party_confirming: 'Paga un confirming',
  ar_third_party_parent: 'Paga la matriz',
  customer_advance: 'Anticipo de cliente',
  customer_refund: 'Devolución a cliente',
  nonitem_bank_fees: 'Comisiones bancarias',
  nonitem_bank_fees_intl: 'Comisiones internacionales',
  nonitem_bank_reversal: 'Apunte erróneo del banco',
  nonitem_card_expenses: 'Tarjetas de empresa',
  nonitem_cash_pool: 'Cash pooling',
  nonitem_fx_deal: 'Compraventa de divisa',
  nonitem_insurance: 'Seguros',
  nonitem_intercompany: 'Intragrupo',
  nonitem_interest_expense: 'Intereses de deudas',
  nonitem_interest_income: 'Intereses a favor',
  nonitem_internal_transfer: 'Traspaso entre cuentas',
  nonitem_leasing: 'Leasing',
  nonitem_loan_drawdown: 'Disposición de préstamo',
  nonitem_loan_repayment: 'Cuota de préstamo',
  nonitem_payroll: 'Nóminas',
  nonitem_social_security: 'Seguridad social',
  nonitem_tax_payment: 'Impuestos',
  nonitem_tax_refund: 'Devolución de impuestos',
  unidentified: 'Cobro sin identificar',
  unidentified_lookalike: 'Sin identificar con importe parecido',
}

export const segmentLabel = (segment: string) => SEGMENT_LABEL[segment] ?? segment

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

export const partyHowLabel = (how: string) => PARTY_HOW_LABEL[how] ?? ruleDescription(how) ?? how
