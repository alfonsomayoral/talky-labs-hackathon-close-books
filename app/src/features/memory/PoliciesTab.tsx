import { Card, Mono } from '@/components'
import styles from './PoliciesTab.module.css'

const SOURCE = 'db/bankrec-docs-and-masters/POLICIES.md'

interface Row {
  name: string
  /** Codes of the closed lists (exceptions, categories) are set in mono. */
  mono?: boolean
  what: string
}

const code = (name: string, what: string): Row => ({ name, mono: true, what })

// A hand-made summary of POLICIES.md §2 to §4, not a copy: the file is the reference and wins.
const AMOUNTS: Row[] = [
  { name: 'Pago normal', what: 'Se liquida el importe abierto de la partida, siempre en positivo, también en los abonos.' },
  { name: 'Abono compensado', what: 'En un cobro o pago neto, el abono es una fila con su importe completo y sin excepción.' },
  { name: 'Diferencia explicada', what: 'La partida se liquida entera aunque haya llegado menos dinero: el importe es el abierto completo.' },
  { name: 'Parcial o disputa', what: 'El importe es lo realmente aplicado; el resto sigue abierto.' },
  { name: 'Duplicado o devuelto', what: 'Duplicado: lo pagado otra vez. Devuelto: lo que se vuelve a abrir.' },
]

const EXCEPTIONS: Row[] = [
  code(
    'PARTIAL',
    'Tras la línea la partida sigue con saldo y no aplica otro motivo: pagos a cuenta, plazos salvo el último, retenciones, anticipos.',
  ),
  code('SHORT_DISCOUNT', 'Pronto pago dentro de plazo (más 3 días de cortesía); la partida se liquida entera.'),
  code('SHORT_BANK_CHARGES', 'Transferencia de fuera de SEPA con comisión de un intermediario, hasta 60 EUR y el 2 %.'),
  code('SHORT_WITHHOLDING', 'El cliente retiene impuestos en origen (México, Brasil, Marruecos).'),
  code('SHORT_DISPUTE', 'El cliente descuenta algo con un motivo, normalmente solo visible en su aviso de remesa.'),
  code('OVERPAYMENT', 'Paga más que el abierto de una sola factura; el exceso queda en la cuenta del cliente.'),
  code('DUPLICATE_PAYMENT', 'La partida ya estaba liquidada y se paga otra vez (un cliente, o nosotros a un proveedor).'),
  code('RETURNED', 'Vuelve un adeudo, un cheque, un contracargo o una transferencia nuestra, y reabre la partida.'),
  code('UNIDENTIFIED', 'Un cobro sin ninguna partida abierta. No se fuerza una casación aunque un importe coincida.'),
  code('FX_DIFFERENCE', 'La línea está en otra divisa que la factura; el banco convierte a su cambio y la factura se liquida entera.'),
]

const CATEGORIES: Row[] = [
  code('BANK_FEES', 'Comisiones de mantenimiento, por transferencia, internacionales, de remesas SEPA, de devolución y de TPV.'),
  code('CASH_POOL', 'Barridos a cero entre las cuentas participantes y la cabecera, las dos patas.'),
  code('INTERNAL_TRANSFER', 'Traspasos entre cuentas de la misma sociedad.'),
  code('INTERCOMPANY', 'Financiación entre sociedades del grupo.'),
  code('FX_DEAL', 'Operaciones de cambio de divisa, las dos patas.'),
  code('BANK_REVERSAL', 'Error del banco y su anulación: las dos líneas.'),
  code('CUSTOMER_ADVANCE', 'Pago de una proforma, cuando la factura todavía no existe.'),
  code('CUSTOMER_REFUND', 'Devolución a un cliente de un pago duplicado.'),
  code(
    'SUPPLIER_REFUND',
    'Devolución de un proveedor de un pago que hicimos dos veces. Si devuelve un abono suyo, no es categoría: liquida el abono.',
  ),
  {
    name: 'Otras',
    what: 'Nóminas, seguridad social, impuestos, préstamos, leasing, seguros, tarjeta corporativa e intereses: están en categories.csv.',
  },
]

function PolicyTable({ title, description, head, rows }: { title: string; description: string; head: string; rows: Row[] }) {
  return (
    <Card title={title} description={description} padding="none">
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col" className={styles.name}>
              {head}
            </th>
            <th scope="col">Qué dice</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.name}>
              <td className={styles.name}>{r.mono ? <Mono>{r.name}</Mono> : r.name}</td>
              <td>{r.what}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}

export function PoliciesTab() {
  return (
    <div className={styles.wrap}>
      <p className={styles.source}>
        Resumen de las políticas con las que se etiquetan las respuestas oficiales, hecho a mano. El texto completo, y el que manda, está en <Mono>{SOURCE}</Mono>; el
        paquete oficial no se versiona ni lo sirve la API. Una regla de memoria nunca cambia estas políticas: solo ayuda a aplicarlas.
      </p>
      <PolicyTable title="Importe de cada fila" description="Cuánto se liquida de cada partida (§2)." head="Caso" rows={AMOUNTS} />
      <PolicyTable
        title="Excepciones de cobro y de pago"
        description="Por qué el dinero no coincide con los documentos (§3)."
        head="Excepción"
        rows={EXCEPTIONS}
      />
      <PolicyTable
        title="Líneas sin partida"
        description="Categorías de lo que no liquida ninguna factura ni abono (§4)."
        head="Categoría"
        rows={CATEGORIES}
      />
    </div>
  )
}
