# CONTRACT.md

Lo que el backend entrega al frontend: el **`Run`**, las decisiones del agente sobre un `Dataset`. Es el único acoplamiento entre los dos. El tipo TypeScript está en [`app/src/domain/run.ts`](app/src/domain/run.ts); el backend lo replica.

> **Estado:** v0, provisional. Se ajusta el día del evento al formato de entrega oficial. Ampliarlo (campos opcionales nuevos) no rompe nada; cambiar o quitar un campo se hace en la misma PR en backend y frontend.

## Convenciones

- JSON, claves en `camelCase`.
- Importes en **céntimos enteros** (`amountCents`) con su `currency` (ISO 4217). Nunca se suman monedas distintas.
- Fechas en ISO 8601: `YYYY-MM-DD` para fechas contables, con hora y zona para marcas de tiempo.
- Un objeto del `Dataset` se referencia con `ObjectRef`: `{ "kind": "invoice", "id": "F-2026-0012" }`. Los `kind` válidos son `entity`, `vendor`, `contract`, `purchaseOrder`, `invoice`, `bankTransaction`, `ledgerEntry` y `erpEvent`.

## `Run`

```json
{
  "id": "run-2026-09-001",
  "createdAt": "2026-11-07T10:30:00+01:00",
  "period": "2026-09",
  "agent": { "version": "0.1.0", "models": ["claude-opus-5-5"], "costUsd": 0.42, "durationMs": 133000 },
  "metrics": { },
  "matches": [ ],
  "alerts": [ ]
}
```

### `metrics`

Una por criterio del jurado. Un valor `null` significa «no calculado» y la interfaz muestra «—».

| Campo | Tipo | Significado |
| --- | --- | --- |
| `accuracy` | `number \| null` | Precisión contable, 0..1. Solo si hay referencia con la que comparar |
| `reconciliation` | `{ matched, suggested, unmatched }` | Recuento de transacciones bancarias en cada cubo |
| `fraud` | `{ detected, byType: Record<AlertType, number> }` | Alertas de fraude detectadas |
| `autonomy` | `{ auto, review }` | Partidas resueltas solas frente a enviadas a revisión humana |
| `auditability` | `{ withEvidence, total }` | Decisiones con regla y evidencia frente al total |

### `matches[]`: conciliación bancaria

Una entrada por transacción bancaria del periodo.

| Campo | Tipo | Significado |
| --- | --- | --- |
| `bankTransactionId` | `string` | Transacción del extracto |
| `status` | `'matched' \| 'suggested' \| 'unmatched'` | Casada, propuesta para revisión, o sin casar |
| `targets` | `ObjectRef[]` | Apuntes del libro mayor o facturas con los que casa (1:1, 1:N) |
| `confidence` | `number \| null` | 0..1 |
| `rule` | `string` | Regla que la produjo, p. ej. `BANK-EXACT-AMOUNT-DATE` |
| `differenceCents` | `number` | Residuo entre el banco y los objetivos; 0 si cuadra |

### `alerts[]`: lo que necesita a una persona

| Campo | Tipo | Significado |
| --- | --- | --- |
| `id` | `string` | Id estable |
| `type` | `'duplicate' \| 'tax_error' \| 'bank_change' \| 'unmatched' \| 'po_mismatch' \| 'other'` | Tipo |
| `severity` | `'high' \| 'medium' \| 'low'` | `high` retiene el pago o el asiento |
| `entityId` | `string` | Sociedad afectada |
| `subject` | `ObjectRef` | Objeto principal (la factura duplicada, el proveedor con IBAN cambiado…) |
| `amountCents` · `currency` | `number` · `string` | Importe en juego |
| `title` | `string` | Una línea, en español: «IBAN distinto al del maestro» |
| `reason` | `string` | Por qué, con las cifras |
| `rule` | `string` | Regla que la levantó |
| `evidence` | `ObjectRef[]` | Objetos que lo prueban (la factura original, el evento del ERP…) |
| `action` | `string` | Qué tiene que hacer la persona: «Verificar el IBAN con el proveedor por teléfono» |
