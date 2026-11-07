# N_TO_M.md — qué es `ar_n_to_m` y qué se puede casar sin forzar (7 nov 2026)

Resultado de la sesión N a M (`docs/briefs/n_to_m.md`). Las cifras son del holdout; las de drift salen iguales o casi, así que drift **no es prueba independiente** en esta estructura. Lo marcado **[Inferencia]** es estimación. Base: `runs/acc-group-holdout`. Con las reglas: `runs/acc-integ-holdout` y `-drift` (PR 99).

## 1. Resultado

| Medida | Base | Con PR 99 |
| --- | --- | --- |
| `ar_n_to_m` | 652 de 1.857 (0,351) | 752 de 1.857 (0,405) |
| `unidentified` · `unidentified_lookalike` | 3.221 · 1.364 (1,000) | 3.221 · 1.364 (1,000) |

En LIVE, según el resultado oficial que pasó la orquestadora: `ar_n_to_m` 0,325 → 0,388 (+113 movimientos), con nota total de 92,32.

De las 100 líneas, 71 son de `REF-SPLIT` y 20 del orden impreso del aviso. Las otras 9 no están atribuidas: pueden ser cascada de saldos o reglas de Exactitud de la misma PR [Inferencia].

**La expectativa del brief (0,6–0,7 por enlace de documentos) no se cumple:** el segmento casi no tiene documentos. El resto de los fallos se queda en fallback, porque no hay señal que supere el umbral.

## 2. Qué es de verdad el segmento

No es un cobro repartido entre facturas, sino **dos cobros unidos por una factura partida**.

| Hecho (golden de holdout) | Valor |
| --- | --- |
| Movimientos · filas | 1.857 · 6.920, todas `ARI`, ninguna `ARC`; la suma de filas es el cobro en todos |
| Parejas · sueltos | 766 parejas (1.532 líneas) · 325 movimientos |
| En cada pareja | mismo cliente, 1 factura común que cierra con los dos importes, `PARTIAL` en el primer cobro |
| Distancia entre los dos cobros | 10–42 días, mediana 24 |
| Orden por emisión o vencimiento explica la factura partida | 83 de 766 |
| `PARTIAL` a 0,4 · 0,5 · 0,6 exactos del total | 336 · 306 · 283 de 925 |

Por eso ninguna hipótesis de antigüedad funciona: el orden no decide qué factura queda partida.

## 3. Subtipos e hipótesis

Umbral fijado antes de medir: una hipótesis entra si acierta ≥ 0,98 de sus líneas en holdout con 0 falsos sobre `unidentified` y `unidentified_lookalike`. **Ningún subtipo por evidencia lo alcanza.** El acierto es el de la mejor hipótesis tras aplicarla.

| Subtipo (excluyentes) | Líneas | Fallaban | Mejor hipótesis | Acierto | Entra |
| --- | --- | --- | --- | --- | --- |
| Aviso enlazable, total igual | 175 | 20 | El documento | 0,994 en facturas; 0,674 por fila antes del orden impreso | Sí, orden impreso (§4) |
| Fichero de detalle | 0 | 0 | — | — | Sin líneas |
| PDF con cláusula abierta | 302 | 211 | H7a; la cuota dispara 0 | 0,457 | No |
| Abono abierto del cliente | 1.117 | 789 | H7a; netar primero 0 de 281 | 0,535 | No |
| Texto declara parcial con cita | 1 | 0 | — | — | Sin masa |
| Cita sin palabra de parcial | 143 | 81 | H7a | 0,622 | No |
| Solo importes y fechas | 117 | 102 | H7a | 0,641 | No |
| Sin tercero | 2 | 2 | — | — | No |

Los predicados de PDF y abono son amplios: basta con que el cliente tenga una partida abierta con cláusula o un abono abierto. El golden no neta ningún abono en este segmento.

Hipótesis medidas (aciertos sobre disparos dentro del segmento):

| Hipótesis | Aciertos | Por qué no entra |
| --- | --- | --- |
| Más antigua primero · por vencimiento | 46 de 674 · 46 de 674 | Sin señal |
| Importe más cercano | 26 de 693 | Sin señal |
| Todas menos la mayor | 0 de 42 | Sin señal |
| Abono primero | 0 de 329 | El golden no neta abonos aquí |
| Consecutivas con fracción | 79 de 102 | Post-hoc y por debajo del umbral |
| **H7a**: subconjunto único, o uno más una factura a 0,4/0,5/0,6 | 404 de 511 | Post-hoc. Fuera del segmento 252 falsos y 4 sobre `unidentified`/`lookalike` |

**Las fracciones 0,4/0,5/0,6 no se usan.** Son un patrón del golden, sin documento ni política que lo diga, y codificarlo sería acertar en TRAIN porque sí. Además falla el umbral.

## 4. Lo que entró (PR 99)

Medido contra el golden en `runs/acc-integ-holdout`. Drift da las mismas cifras. Acierto = movimiento entero igual al golden.

| Regla | Movimientos | Aciertan | mal→bien | bien→mal | mal→mal |
| --- | --- | --- | --- | --- | --- |
| `REF-SPLIT` | 180 | 180 | 72 | 0 | 0 |
| Orden impreso del aviso (los que cambian) | 25 | 20 | 20 | 0 | 5 |

- **`REF-SPLIT` (`rules/split_invoice.py`).** Dos cobros del mismo cliente y divisa citan la misma factura, y solo una, y juntos suman al céntimo todo lo que citan los dos. El primero cierra sus exclusivas y deja el resto en la común, con `PARTIAL`; el segundo la cierra. La evidencia son las dos citas y el cuadre; POLICIES §2 y §3 solo dan las etiquetas, no el emparejamiento. Por segmento: `ar_n_to_m` 179 de 179, `ar_replaced_invoice` 1 de 1, sin disparos en `ar_partial`, `ar_instalment`, `ar_same_amount_*`, `unidentified` ni `unidentified_lookalike`.
- **Orden impreso.** Cuando un aviso enlazado no cierra, el dinero llena sus líneas en el orden impreso y la última queda `PARTIAL`. Es una lectura de POLICIES §5.4, que solo dice que el aviso lista lo pagado: el orden no está escrito. Medido en TRAIN fuera del holdout: 391 de 391 en `ar_n_to_m`. Los 5 mal→mal son `ar_discount_late`, ya mal antes.

**Por qué se exige una factura exclusiva.** Con una sola factura no hay nada que repartir y `REF-TEXT` ya la deja bien. Sin esa condición, el predicado tendría 35 falsos en `ar_instalment`. La condición se decidió antes de medirlos.

**Prueba en LIVE, sin golden (`runs/live-amount-c`):** 178 parejas cumplen el predicado con exclusiva, frente a 176 esperadas por proporción. El pipeline ya resolvía 113 y cambian 65, frente a 69 esperadas. Es consistente, pero no mide acierto.

**Límite conocido:** el pase corre antes del recorrido por fecha y lee saldos de apertura, así que no ve un tercer cobro anterior que ya pagó parte de esas facturas. Sin medir.

## 5. Lo que queda en fallback

Citas según `_cited`, fuerte y débil.

| Factura común citada por | Parejas | Líneas | Fallaban | Exclusivas citadas | Disparan |
| --- | --- | --- | --- | --- | --- |
| Ambos cobros | 287 | 574 | 279 | 1.244 de 1.336 | 182 |
| Solo el primero | 76 | 152 | 99 | 272 de 350 | 0 |
| Solo el segundo | 125 | 250 | 202 | 258 de 791 | 0 |
| Ninguno | 278 | 556 | 505 | 62 de 1.573 | 0 |

- **Una sola cita o ninguna: 479 parejas y 806 líneas que fallaban.** Sin dos citas no se observa cuál es la factura común. Sin cita, 247 de 278 parejas tampoco citan ninguna de sus facturas. Hay más combinaciones que evidencia: si se fuerzan, los falsos caen sobre `unidentified` y `ar_partial`.
- **Doble cita que no dispara: 105 parejas.** Alguna factura citada es ajena al golden o falta una cita. El predicado se abstiene, como debe.
- **Cobros sueltos: 325 movimientos, 120 fallaban.** Sin explicar.

**Lo que haría falta para ir más allá:** una fuente nueva, no otra heurística, por ejemplo el extracto de cuenta del cliente o una respuesta de la organización sobre cómo se reparte. Jev no ayuda: es aritmética sin texto que leer.

## 6. Enlace de avisos: descartado con números

En los fallos de `ar_n_to_m` + `ar_partial` + `ar_1toN_credit_note`, 3.072 de 3.170 (holdout) y 3.088 de 3.186 (drift) no tienen ningún aviso de su sociedad que cite una partida del golden.

| Causa | Líneas | Recuperables |
| --- | --- | --- |
| Ningún aviso de la sociedad cita alguna partida | 3.072 | 0 |
| Aviso enlazado, reparto equivocado | 21 | 20 (orden impreso, §4) |
| Aviso de otro movimiento: cita 1 de 2 partidas y su total es otro cobro | 77 | 0 |
| Ventana de fechas · pagador · total distinto · número sin prefijo · formato (6.762 avisos, 0 fallidos) · fichero de detalle | 0 | 0 |

## 7. Sin resolver

- **Recuentos de citas.** El análisis de la factura común dio dos censos: 209/94/123/340 con cola fuerte de 5 dígitos, y 287/76/125/278 con `_cited` fuerte y débil. La diferencia de criterio probablemente explica el salto [Inferencia]; no se han cruzado. Lo mismo con 741 y 761 parejas cuya suma cuadra.
- **Avisos.** En un cruce sin filtro de pagador ni fecha, los números salen literales en avisos en 325 movimientos, frente a 175 enlazados. De esos 150, el análisis de enlace acota 77 a avisos de otro cobro. Es probable que el resto sean colisiones [Inferencia]; no se han revisado uno a uno.
- **Coste del pase.** La etapa `rules` pasó de 8,5 a 34,2 s en la ejecución integrada (148 s en total, tope 150 s). Falta separar qué parte es de `REF-SPLIT`.
