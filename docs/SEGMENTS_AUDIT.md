# SEGMENTS_AUDIT.md — lo que dicen los ejemplos oficiales y lo que hace el motor

Auditoría del 7 nov 2026 (brief: `docs/briefs/segments_audit.md`). Fuente de los ejemplos: https://hackathon.usetalky.com/ejemplos. Salvo que se diga otra cosa, las cifras son de holdout. **Dato** viene del golden o de una ejecución; **replay** es una simulación sin efecto cascada; **[Inferencia]** es deducción no medida.

Umbral de entrada, fijado antes de medir: una regla entra si explica ≥ 0,98 de las líneas que activa, sobre todos los cobros, con 0 falsos en `unidentified` y `unidentified_lookalike`.

## 1. Conclusión

Los 7 ejemplos literales de los segmentos prioritarios ya pasaban: el motor no caía en ninguna trampa que nombran. Los puntos no estaban en la trampa, sino en cuatro sitios que los ejemplos solo dejan ver indirectamente:

| Hallazgo | Tipo | Efecto medido |
| --- | --- | --- |
| El cobro de una retención es `total − round_half_up(total × pct / 100)`, no el importe impreso (`floor`) | Ley del dato: 924/924 en holdout, 913/913 en drift | `ar_retention` 0,8319 → 0,9828 (PR 104) |
| `_common_prefix` contaba el espacio tras la palabra y un nombre más largo ganaba al entero | Bug | 93,04 → 93,26, ningún segmento baja (PR 105) |
| «Mar» de «Riegos Mar S.L.» se leía como marzo | Bug | fifo +0,0039, month +0,0061 (PR 108) |
| Sin buscar varias facturas netas de la tasa fiscal | Regla que faltaba | `ar_short_withholding` 0,9158 → 0,9458 (PR 113) |
| Un tercero sin maestro que cita o nombra la única factura abierta | Regla que faltaba | `ar_third_party_agency` 0,4747 → 0,7247, confirming 0,8527 → 0,9893 (PR 112) |
| Se perdía la regularización de una disputa | Regla que faltaba | `ar_dispute_settlement` 0,8604 → 0,9701 (PR 114) |

LIVE oficial con las PR 104 y 105: 92,32 → 92,59, sin ningún segmento a la baja. Las siguientes no están medidas en LIVE aquí.

## 2. Segmento × causa × señal del ejemplo × líneas

| Segmento | Causa | Señal del ejemplo | Líneas | Decisión |
| --- | --- | --- | --- | --- |
| `ar_retention` | Cobro 1 céntimo bajo el impreso | Sí, cláusula del PDF | 133 | Regla, PR 104 |
| `ar_retention` | Retención confundida con `SHORT_WITHHOLDING` por la tasa del país | Sí, es la trampa | 11 | Regla, PR 104 |
| `ar_retention` | Tercero no identificado | Sí, pero sin tercero no se usa | 12 | Fuera |
| `ar_advance_deduction` | Sin cobro igual al neto en el extracto, o anterior a la factura | Cláusula extraída 356/356 | 7 | Cerrado sin regla |
| `ar_third_party_agency` | Cola de factura o nombre cortado, sin tercero | Sí | 89 | Regla, PR 112 |
| `ar_third_party_agency` | Cita y nombre, pero ≥ 4 facturas o cobro ≠ saldo | Parcial | 67 | Fuera |
| `ar_third_party_agency` | A6, cita + 1 a 3 partidas | Sí | 8 | Fuera, muestra pequeña |
| `ar_third_party_agency` | Solo nombre, solo cita, o sin señal | Parcial o no | 23 | Fuera |
| `ar_overpayment` | Sin citar la factura; el importe no cuadra | No | 189 | Fuera |
| `ar_overpayment` | Exceso citado > 2 % sin excepción | Sí | 34 | Fuera, §3 |
| `ar_overpayment` | Sin casar, con cita débil o fuerte | Parcial | 15 | Fuera |
| `ar_fx` | Varias facturas sin casar | Sí (`orig_amount`), no es divisa | 90 | Techo de N a M |
| `ar_fx` | REF-TEXT cita parte de la lista | Sí | 64 | Techo de N a M |
| `ar_short_dispute` | Sin aviso de igual sociedad y total | No | 209 | Techo, §3 |
| `ar_dispute_settlement` | Pago previo perdido | Sin ejemplo propio | 91 | Regla, PR 114 |
| `ar_short_withholding` | Subconjunto neto de la tasa | Sí | 39 | Regla, PR 113 |
| `ar_short_withholding` | Límite de búsqueda o `MAX_CHANCE` | Sí | 71 | Techo de N a M |
| `ar_short_withholding` | Tercero no encontrado | No | 13 | Fuera |
| `ar_same_amount_*` | Homónimo más largo gana al nombre entero | Sí | 153 | Bug, PR 105 |
| `ar_same_amount_*` | Intercambio del mismo día, tercero e importe | No | 176 | Techo, §3 |
| `ar_same_amount_*` | Mes leído del nombre | No | 40 | Bug, PR 108 |

Las líneas de `ar_same_amount_*` se solapan por cascada; `ar_retention`, `ar_fx` y `ar_short_withholding` usan bases distintas según la fecha de la medida.

`ar_instalment`: los 108 fallos con fila del golden en FALLBACK tenían 34 líneas del bug de homónimo, 11 con el ordenante conocido de otro cliente y 28 sin número citado. `customer_advance` y `ap_confirming` no se han auditado en esta sesión.

## 3. Lo medido y descartado

| Hipótesis | Medida | Por qué no entra |
| --- | --- | --- |
| Agencia: `_in_text` lee `remittance_info` en todas las líneas (A1) | Replay: activa 56, aciertos 49, falsos 7 | 0,875 < 0,98 |
| Sobrepago: factura citada + cash > total + el exceso no cuadra con otra partida | Replay: activa 582, aciertos 184, falsos 398; solo filas nuevas 243 / 32 | 0,316. Precisión de clase 0,976 → 0,474. En 194 de 211 falsos el golden paga más facturas: son citas incompletas |
| `ar_fx` sin `orig_amount`: tercero + única partida en divisa con contravalor ±0,5 % | Replay: activa 18, aciertos 0 | Esa masa no existe: 725/725 de `ar_fx` traen `orig_amount`, y 0 de las 1.448 líneas EN DIV/XBCT sin él son facturas en divisa |
| Disputa: sociedad + total + ventana, sin referencia | 3 activadas, 2 con el mismo número de filas | Muestra mínima, por debajo del umbral |
| FIFO: una cita o un aviso gana a la más antigua | 1 REF-TEXT de 480 fallos | Falsa |
| FIFO: desempate en el mismo día | Id menor 64, mayor 71; fecha valor 22 frente a 14 | Sin señal. El propio ejemplo oficial es un intercambio de estos |

Techos, sin regla posible con los datos que hay:

- **`ar_short_dispute` sin aviso (209 cobros, 17.750 filas):** el texto cita 885 filas y 18 de las 528 con disputa. POLICIES prohíbe marcar disputa sin deducción explícita.
- **Límites de búsqueda de varias facturas (71 líneas en retención fiscal):** problema compartido con N a M.

## 4. Lo que los ejemplos no dicen

- **`ar_short_withholding`:** el texto de la trampa («sólo va en la partida que sufre la retención») contradice las filas del propio ejemplo y el golden, que marcan todas las facturas: 0 sin excepción en 1.401 movimientos, abonos vacíos, y 74 filas de BR01 con `SHORT_DISPUTE`. Manda el golden.
- **Parser:** cláusulas de retención, anticipo, cuotas y sustitución extraídas al 100 % en holdout y LIVE (solo en `es` y `en`, en todas las fases). 0 avisos rechazados en todos los formatos. **Riesgo FINAL:** una sociedad nueva con frase en otro idioma no se extraería; y `DISCOUNT_WORDS` y `WITHHOLDING_WORDS` son listas fijas.
- **`ar_advance_deduction` en LIVE:** sin hueco de cláusula. De 91 partidas sin fila, 77 no tienen cobro igual al neto; unas 5 serían recuperables [Inferencia].

## 5. Estado de las reglas

| Regla | Rama / PR | Holdout | Drift |
| --- | --- | --- | --- |
| Retención | PR 104 | 92,99 → 93,04 | Conjunta, abajo |
| Tercero (`_common_prefix`) | PR 105 | 93,04 → 93,26 | Conjunta, abajo |
| Evidencia de `PARTY-PLAN` | PR 107 | CSV idéntico | No aplica |
| Mes en el nombre | PR 108 | 93,04 → 93,05, 50 líneas | Conjunta, abajo |
| Agencia | PR 112 | 93,52 → 93,58, 196/196 filas de la regla | 93,27 → 93,33 |
| Retención fiscal | PR 113 | 93,52 → 93,56, 371/371 líneas | 93,27 → 93,31, 365/366 |
| Regularización | PR 114 | 93,60 → 93,63, 1.057/1.057 en la medida previa | 93,27 → 93,30 |
| Enlace de aviso por referencia cortada | `KPI-12_advice_cut` | 93,60 → 93,62, 4 líneas de mal a bien | En medición |

Drift conjunto de las PR 104, 105, 107 y 108, sobre main bb942ee: 92,75 → 93,02, ningún segmento baja. Las medidas de las PR 112 y 113 son anteriores al rebase sobre las PR 110 y 113; la 113 se repitió tras rebasar (371/371). No se ha corrido en cada PR ni la suite completa ni la comprobación de CSV determinista.

`unidentified_lookalike` queda en 0,9993 desde la PR 109 (PARTY-FRACTION, de otra sesión): una línea, aceptada como excepción de puerta por la orquestadora. Ninguna regla de esta auditoría añade filas ahí.

`PARTY-AGENCY` activa 102 líneas en `ar_third_party_confirming` y ninguna en agencia, en contra de la simulación; aciertan todas. La causa de la diferencia no se ha investigado.
