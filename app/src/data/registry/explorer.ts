// The package's data types in the Explorer: a new type is a spec here, not a new page (CLAUDE.md §6).
export interface ExplorerSpec {
  id: 'items' | 'parties' | 'documents' | 'detailFiles'
  label: string
  /** API resource under /api/data/{phase}/. */
  resource: 'items' | 'parties' | 'documents' | 'detail-files'
  searchPlaceholder: string
  /** Facet in the `type`-like param of the resource, with its values. */
  facet: { param: string; label: string; options: { value: string; label: string }[] }
}

export const EXPLORER_SPECS: ExplorerSpec[] = [
  {
    id: 'items',
    label: 'Partidas',
    resource: 'items',
    searchPlaceholder: 'Busca por número, id o tercero…',
    facet: {
      param: 'type',
      label: 'Tipo',
      options: [
        { value: 'ARI', label: 'Factura emitida' },
        { value: 'ARC', label: 'Abono emitido' },
        { value: 'API', label: 'Factura de proveedor' },
        { value: 'APC', label: 'Abono de proveedor' },
      ],
    },
  },
  {
    id: 'parties',
    label: 'Terceros',
    resource: 'parties',
    searchPlaceholder: 'Busca por nombre, id o NIF…',
    facet: {
      param: 'kind',
      label: 'Clase',
      options: [
        { value: 'customer', label: 'Cliente' },
        { value: 'supplier', label: 'Proveedor' },
      ],
    },
  },
  {
    id: 'documents',
    label: 'Documentos',
    resource: 'documents',
    searchPlaceholder: 'Busca por fichero o tercero…',
    facet: {
      param: 'kind',
      label: 'Clase',
      options: [
        { value: 'remittanceAdvice', label: 'Aviso de remesa' },
        { value: 'invoicePdf', label: 'Factura' },
        { value: 'creditNotePdf', label: 'Abono' },
        { value: 'proformaPdf', label: 'Proforma' },
        { value: 'bankAccountNotice', label: 'Carta de IBAN' },
      ],
    },
  },
  {
    id: 'detailFiles',
    label: 'Ficheros de detalle',
    resource: 'detail-files',
    searchPlaceholder: 'Busca por fichero…',
    facet: {
      param: 'kind',
      label: 'Clase',
      options: [
        { value: 'directDebitBatch', label: 'Remesa de recibos' },
        { value: 'cardSettlement', label: 'Liquidación de tarjeta' },
        { value: 'chequeDeposit', label: 'Ingreso de cheques' },
        { value: 'paymentRun', label: 'Remesa de pagos' },
      ],
    },
  },
]
