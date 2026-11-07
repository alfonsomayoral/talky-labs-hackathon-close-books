# Tres reglas de evidencia tomadas de Valtermia

Comparación contra `main` `3b5328e`, sobre el holdout existente de enero a junio de 2025: 199.987 movimientos.
Las ideas proceden de `lorenzo-redolfi/valtermia-rec` `c07d5a7`; se adaptan al motor y a sus controles de ambigüedad.

## Comportamiento

- **Referencia ruidosa, solo cobros de clientes:** una cita que no explica el importe puede ceder ante una única
  factura abierta del mismo tercero seguro que cuadra al céntimo. Se conservan los pagos parciales explícitos,
  planes PDF, descuentos, retenciones, comisiones y sobrepagos explicables. No se amplía la búsqueda de subconjuntos.
- **Plazo explícito:** `INSTALMENT 2/6`, `PLAZO 2 DE 6` y equivalentes pueden explicar una cuota sin plan PDF.
  Se exige un único candidato, tercero seguro, fracción válida y saldo suficiente. El redondeo admite únicamente
  los céntimos inferior y superior del reparto en cuotas iguales. Un plan PDF contradictorio impide esta inferencia.
- **Abono pagado por transferencia:** un cargo puede liquidar un `ARC` del cliente identificado, por su saldo exacto,
  si cita el documento completo o su PDF dice que se pagará por transferencia. Los abonos para compensar,
  reservados, futuros, cerrados o ambiguos se excluyen. La fila lleva importe positivo y reduce el saldo del abono.

No se añaden nombres, IDs, importes, fechas ni porcentajes aprendidos como constantes del motor.
Las decisiones nuevas conservan su evidencia y las excepciones siguen pasando por `resolve` y `policy`.

## Resultados con el evaluador oficial

| Medida | Base | Variante |
| --- | ---: | ---: |
| Score | 92,59 | 92,61 |
| Precisión de pares | 0,996585 | 0,996629 |
| Recall de pares | 0,894023 | 0,894113 |
| Exactitud por movimiento | 0,944571 | 0,944941 |
| Macro-F1 de excepciones | 0,856104 | 0,856592 |
| `ar_credit_note_paid_out` (43) | 0,000000 | 0,930233 |
| `ar_ref_noise` (42.462) | 0,918727 | 0,919481 |
| `unidentified` / `unidentified_lookalike` | 1,000000 / 1,000000 | 1,000000 / 1,000000 |
| Movimientos cubiertos | 199.987 | 199.987 |
| Tiempo total (una ejecución por variante) | 370 s | 594 s |
| Pico RSS informado por el pipeline | 1.946 MB | 2.072 MB |

La mejora es **0,02 puntos**, con 74 movimientos correctos adicionales en total. Existe una regresión de un
movimiento en `ar_same_amount_fifo` (0,944562 → 0,944399); no se afirma que todos los segmentos mejoren.
La precisión de `DUPLICATE_PAYMENT` pasa de 0,950437 a 0,960236 y la de `OVERPAYMENT` se mantiene en 0,975904.
Ninguna precisión de excepción baja más de 0,002.

| Mes | Base | Variante |
| --- | ---: | ---: |
| 2025-01 | 93,65 | 93,67 |
| 2025-02 | 93,61 | 93,64 |
| 2025-03 | 93,72 | 93,73 |
| 2025-04 | 92,96 | 92,98 |
| 2025-05 | 92,27 | 92,30 |
| 2025-06 | 90,11 | 90,14 |

Los meses se puntúan con el evaluador oficial sobre las predicciones de la misma ejecución cronológica continua;
no son seis particiones independientes con estados reinicializados.

Auditoría de las decisiones directas de las reglas nuevas, sin atribuirles los efectos posteriores sobre saldos:

| Regla | Activaciones | Correctas antes | Correctas después |
| --- | ---: | ---: | ---: |
| `PARTY-REF-NOISE` | 27 | 2 | 26 |
| `CREDIT-PAYOUT` | 40 | 0 | 40 |
| `PARTY-INSTALMENT` | 0 | — | — |

La restricción final a cobros de clientes no excluye ninguna activación observada: ninguna recuperación de
referencia se produjo sobre proveedores. El respaldo de plazos está comprobado con pruebas sintéticas; este
holdout no demuestra una mejora suya. Los 27 casos de referencia se justifican por POLICIES §5.5 y los abonos por
POLICIES §5.9, sin calibrar una regla para alcanzar un número mínimo de activaciones.

## Comprobaciones y límites

- `just be-check`: correcto. Suite pytest sin datasets externos: **391 passed, 28 skipped**. Las pruebas nuevas
  incluyen reservas, ambigüedad, documentos futuros, divisa, saldo insuficiente, PDF contradictorio y resolución
  del importe, excepción y saldo final. Los casos positivos fallaron antes de implementar las reglas.
- Se reaprendió la tabla de categorías únicamente con los **1.289.944 movimientos anteriores a 2025-01-01**.
  Comparar ambas tablas sobre todos los movimientos del holdout da **cero cambios de categoría y cero cambios
  de fallback**. Nueve propuestas pasan de `CAT-CODE` a `CAT-TEXT` con idéntica categoría. Es una comprobación
  de equivalencia de decisiones, no otra ejecución completa del motor con la tabla nueva.
- Los artefactos locales están en `runs/valtermia-review/{baseline,candidate}/`, con `submission.csv.gz`,
  `explanations.jsonl.gz` y `run.json`. Se comparan con `closebooks score <candidate> --compare <baseline>`.
- No se ejecutó holdout-drift, ni un control temporal nuevo, ni una prueba completa sin PDFs. Este holdout ya se
  había utilizado para desarrollar el motor: las mejoras mensuales no prueban ausencia de sobreajuste.
- El tiempo pasó de 370 a 594 segundos. No se ha aislado la causa ni repetido una medición controlada de
  rendimiento; la PR permanece en borrador hasta revisar este coste y validar drift. No hubo envíos LIVE/FINAL.
