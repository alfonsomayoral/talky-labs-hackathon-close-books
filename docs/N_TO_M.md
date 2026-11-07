# N_TO_M.md — qué es `ar_n_to_m` y qué se puede casar sin forzar (7 nov 2026)

Resultado de la sesión N a M (`docs/briefs/n_to_m.md`). Las cifras son del holdout salvo donde se indica; las de drift salen iguales o casi, así que drift **no es prueba independiente** en esta estructura. Lo marcado **[Inferencia]** es estimación. Base: `runs/acc-group-holdout`. Con las reglas: `runs/acc-integ-holdout` y `-drift` (PR 99).

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

## 8. Parejas de cobros en `ar_partial`: `PAIRED-PARTIAL`, sin PR

Rama `KPI-11_paired-partial`, sin fusionar. Dos cobros de un solo cliente suman al céntimo el saldo de la única factura que encaja. Sin constantes.

| Medida | Holdout | Drift |
| --- | --- | --- |
| Sobre main antes de `PARTY-FRACTION` (replay) | 378 de 378, `ar_partial` 0,752 → 0,855 | 382 de 384 |
| **Marginal sobre main con `PARTY-FRACTION`** (replay sobre `seg-main-45236d1-holdout`) | **30 movimientos**, 30 mal→bien, `ar_partial` 0,967 → 0,975 | — |

- **Por qué no entra:** 30 líneas no llegan al mínimo de 50 acordado; `PARTY-FRACTION` (PR 109) se llevó esa masa.
- **Fuera de muestra, TRAIN 2024-H1:** 2.104 de 2.178 = 0,966, 0 falsos en `unidentified` y `unidentified_lookalike`. Con guardas (abstención si hay plan de cuotas en el PDF o si el cobro cita otra factura): 1.616 de 1.620 = 0,9975, pero las guardas salieron de los falsos de esa misma ventana. Estado de una ejecución antigua, sin `REF-*` ni `PARTY-*`: es una prueba de estrés, no la población real.
- **Homónimos, para después del evento:** aceptar los 2–5 clientes con el mismo nombre en vez de uno solo recuperaría 687 fallos en vez de 377 (163 parejas más), con 1–2 parejas falsas en `ar_instalment`. Filtro post-hoc: fuera.
- **Sin señal:** 163 `PARTIAL` cuyo segundo cobro cae fuera de la fase. Solo los explican las fracciones del golden.

## 9. Conjuntos dispersos de `ar_ref_noise`: sin señal

Holdout: 2.826 líneas en fallback, 2.435 con 2 o más facturas (2.297 sin cita), de tamaño 4·6·10 (cuartiles) y máximo 43, entre 32·47·70 abiertas del cliente. Todas pagan facturas enteras. Los cobros son periódicos, pero los conjuntos no son ciclos: 1.863 de 2.236 solapan vencimientos con el cobro anterior.

| Hipótesis (aciertos/disparos en líneas en fallback) | Holdout | Drift | Falsos `unidentified`/`lookalike` |
| --- | --- | --- | --- |
| Mes de emisión, subconjunto único | 164/196 | 185/219 | 1 |
| Serie, subconjunto único | 178/203 | 168/191 | 2 |
| Más antiguo que cuadra | 389/2.423 | 352/2.509 | 11 |
| Vencidas con cotas del repo (post-hoc) | 182/190 = 0,958 | 164/169 | 0 |
| Residuales vencidas en cascada (post-hoc) | 286/293 = 0,976 | 309/314 = 0,984 | 0 |

Las hipótesis que superan 0,98 suman 44 líneas, y casi todas ya están resueltas. La más cercana no llega en holdout, se eligió tras ver el golden y sin cascada da 0,833. **No entra ninguna regla y el umbral no se relaja.**

## 10. Parejas de `ar_n_to_m` solo por importes: no pasan

958 líneas de pareja sin doble cita, 806 de ellas fallan. Replay sobre el estado de la ejecución, solo líneas sin resolver hoy, holdout.

| Variante | Parejas | Objetivo bien / falsas | Falsas totales | Precisión |
| --- | --- | --- | --- | --- |
| V1, con fracciones 0,4/0,5/0,6 y 10–42 días (del golden) | 214 | 266 / 4 | 40 | 0,907 |
| V2, partición exacta sin constantes | 247 | 0 / 0 | 4 | 0,992 |

V2 solo acierta pares de una sola factura, sobre todo `ar_partial`, y no resuelve N a M. Sin fracción, la suma no dice qué factura se parte: 733 abstenciones por varias particiones. V1 no llega al umbral y sus constantes están retiradas.

## 11. Líneas sueltas sin tercero resuelto: `PARTY-AMOUNT-LATE` (PR 120)

Cobros en fallback donde el texto nombra al pagador de forma parcial y el importe es el saldo exacto de una única factura abierta. Con la PR 105 de `parties`, de las 391 líneas sueltas de `ar_ref_noise` siguen en fallback 113.

| Variante (replay sobre todos los cobros en fallback) | Holdout | Drift | LIVE (recuento) | Falsos `unidentified`/`lookalike` |
| --- | --- | --- | --- | --- |
| Un solo tercero, por prefijo | 61/61 | 61/61 | 64 | 0 |
| Unión con varios candidatos (post-hoc) | 162/162 | 167/167 | 166 | 0 |
| Sin tercero, factura única de sociedad y divisa | 356/982 | 359/999 | 940 | 477 · 488 |

Ejecución real de la unión, sobre main a5c8ca8: 161 de 163 = 0,988 en holdout y 170 de 172 = 0,988 en drift, 0 falsos en `unidentified` y `unidentified_lookalike`. Los 2 fallos son `ar_same_amount_fifo` con mismo importe y mismo saldo.

- **Primera medida real: 0,895 en drift.** Cerraba por saldo final un cobro anterior a otro que ya había dejado `PARTIAL` la factura. El orden por fecha lo corrigió: el anterior es el parcial y el último cierra.
- **Justificación:** ejemplo oficial de referencia ruidosa (hackathon.usetalky.com/ejemplos). POLICIES §3 advierte de no identificados con el importe exacto de otra factura; por eso se exige tercero, partida única y revisión por una persona.
- **Límite:** corre tras la cascada y no libera cobros posteriores que dependan de ese saldo.

## 12. Otras cifras de la tarde

- **`PARTY-FRACTION` (PR 109, de otra sesión), holdout sobre 45236d1:** 456 de 466 = 0,9785. De los 10 fallos, 8 tienen factura e importe bien y excepción mal, y 2 casan un cobro sin partida (1 `unidentified_lookalike`, 1 `customer_advance`). Múltiplos del 5 % sin documento que los nombre: es la excepción conocida a la puerta.
- **Coste de `REF-SPLIT`:** 29,7 s en holdout, pico 4,1 GB, casi todo en un segundo `PartyAmount` y `parties._in_text`. El reorden de la rama `KPI-11_n_to_m-speed` no ahorró nada medible y no se fusionó.

## 13. Para después del evento

| Qué | Por qué | Cifra de partida |
| --- | --- | --- |
| Reutilizar el motor de `PartyAmount` en `REF-SPLIT` y etapas tras `resolve` | Lo que de verdad cuesta | ~30 s por fase |
| Medir `PAIRED-PARTIAL` en una fase de 2024 con código actual | El 0,966 de TRAIN usa estado antiguo | Marginal hoy: 30 líneas |
| Parejas de homónimos | Más cobertura, filtro post-hoc | 163 parejas más, 1–2 falsas |
| Revisar `PARTY-FRACTION` en una fase ajena | Sin documento, lookalike < 1,000 | 0,9785 en holdout |
| Reconciliar los dos censos de citas y los 150 movimientos con avisos sin enlazar | Abierto en §7 | 150 movimientos |
| Fuente nueva para parejas sin cita y dispersos | Sin señal en los datos | 806 + 2.435 líneas |
| Cobros sueltos de `ar_n_to_m` y `PARTIAL` con segundo cobro fuera de fase | Sin explicar | 120 · 163 líneas |
