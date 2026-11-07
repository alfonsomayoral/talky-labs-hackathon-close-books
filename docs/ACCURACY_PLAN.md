# ACCURACY_PLAN.md — subir la puntuación sin sobreajustar (tarde del 7 nov 2026)

Plan para la sesión **Exactitud Close the Books**. Parte de lo medido, no de lo esperado. Lo marcado **[Inferencia]** es estimación.

## 1. Dónde estamos (medido)

| Medida | Valor |
| --- | --- |
| **LIVE oficial** (`runs/live-final-a`, main 4e5d51b, enviado 09:43) | **90,69** · F1 pares 0,933 (precisión 0,996, recall 0,877) · exactitud 0,934 · macro-F1 0,801 · 0 movimientos faltantes |
| Holdout temporal (últimos 6 meses de TRAIN, estado inicial calculado) | 91,37 · drift simulado 90,06 |
| Desviación holdout → LIVE | −0,7: el sistema no sobreajusta más de lo que medimos |
| Tiempo y memoria (holdout) | 136 s, 7,3 GB; con los prototipos de `docs/PERF.md`, 105 s y 5,1 GB |

Lo que ya está al 98–100 % y **no se toca**: todo lo resuelto por fichero de detalle (remesas de pago, recibos, tarjetas, cheques, devoluciones), avisos de remesa parseados, categorías, `ar_1to1`, `ar_same_amount_month`.

## 2. Dónde se pierden los puntos en LIVE (movimientos fallados ≈ n × (1 − exactitud))

| Segmento | Exactitud | n | Fallados | Qué es | Causa probable [Inferencia] |
| --- | --- | --- | --- | --- | --- |
| `ar_ref_noise` | 0,896 | 42.000 | ~4.400 | cobro con referencia ruidosa, 2,2 facturas de media | tercero no resuelto (nombre cortado o renombrado) o varias facturas abiertas sin señal; subconjuntos con > 16 candidatas |
| `ar_1toN_credit_note` | 0,605 | 3.300 | ~1.300 | facturas menos abono, abono sin citar | `REF-COMPLETED`/`_notes_for` solo cubre un abono exacto; varios abonos o abono + descuento no |
| `ar_n_to_m` | 0,324 | 1.800 | ~1.200 | un cobro paga parte de varias facturas | `_oldest_first` reparte por antigüedad; el golden reparte de otra forma (ver §4.3) |
| `ar_partial` | 0,762 | 3.900 | ~900 | pago parcial | elegir la factura correcta entre varias cuando la caja no cuadra con ninguna |
| `ar_1toN_text` | 0,887 | 6.500 | ~700 | varios números en el texto | números cortados en el límite de 38 caracteres; sufijos cortos |
| `ar_short_discount` | 0,900 | 5.500 | ~550 | descuento por pronto pago | descuento sobre varias facturas; fecha de gracia; términos del maestro frente a la factura |
| `ar_same_amount_fifo` | 0,935 | 6.400 | ~400 | mismo importe, varias facturas | FIFO por fecha de emisión frente a otra regla de desempate |
| `ar_instalment` · `ar_retention` · `ar_advance_deduction` | 0,92 · 0,80 · 0,71 | 4.700 · 1.000 · 260 | ~700 | lo que dice el PDF | cláusulas no extraídas (texto en otro idioma o formato) |
| `ar_duplicate_payment` · `ap_duplicate_payment` | 0,42 · 0,84 | 590 · 70 | ~350 | pago repetido | detección solo si la partida se cerró con cita; **y la clase DUPLICATE_PAYMENT vale 2 puntos** |
| `ar_overpayment` | 0,419 | 340 | ~200 | sobrepago | ratios 2 %/10 % aprendidos del golden; **clase de 2 puntos** |
| `ar_discount_late` | 0,651 | 830 | ~290 | descuento fuera de plazo (PARTIAL) | fecha límite y gracia |
| `ar_short_dispute` | 0,750 | 1.100 | ~275 | disputa | 15 % sin aviso; avisos no parseados |
| `ar_dd_represented_transfer` | 0,725 | 980 | ~270 | recibo devuelto que se paga por transferencia | referencia al recibo/mandato en el texto |
| `ar_fx` | 0,736 | 760 | ~200 | factura en divisa cobrada en otra | `orig_amount` ausente: buscar por contravalor con `fx_rates` y tolerancia 3 % |
| `ar_third_party_agency` · `_parent` · `_confirming` | 0,44 · 0,68 · 0,84 | 350 · 190 · 690 | ~370 | paga un tercero | ordenante no es cliente: «EXPTE», «ORD.», matriz por `parent_customer_id` |
| `ar_credit_note_paid_out` | 0 | 43 | 43 | abono pagado por transferencia | nuestro cargo contra un `ARC` (rappel pagado): no hay regla |

Macro-F1 (0,801): las clases que más pierden son `DUPLICATE_PAYMENT`, `OVERPAYMENT`, `PARTIAL` y `UNIDENTIFIED` (falsos positivos por cobros sin casar). Cada clase vale 2 puntos.

## 3. Lo que es sobreajuste y hay que cambiar (riesgo para FINAL)

FINAL trae a propósito: una sociedad nueva con banco, divisa (ZAR) y numeración (`KWI…`) nuevos y maestros aparte (`final/masters_final/`), IT01 con cuenta nueva desde 2026-02-01, clientes renombrados, pagos más lentos. Lo que hoy depende de TRAIN:

| Dependencia | Fichero | Cambio |
| --- | --- | --- |
| Tabla de códigos de categoría aprendida con todo TRAIN | `categories.py`, `backend/data/category_codes.csv` | Se mantiene como **una** señal; añadir señales estructurales que no dependen del banco: pareja opuesta el mismo día entre cuentas propias (traspaso / cash pool), importe idéntico mensual al mismo tercero (leasing, nómina, seguro), abono y cargo iguales en días (anulación). Medir que un banco nunca visto (holdout sin MONC en la tabla) no cae al respaldo |
| Vocabulario en regex por idioma | `TEXT_RULES`, `DISCOUNT_WORDS`, `WITHHOLDING_WORDS`, `CROSS_BORDER_MARKS` | Ampliar a los idiomas y países del maestro de la fase (inglés sudafricano, portugués, polaco, chino romanizado) y, sobre todo, apoyarse en estructura (código ISO camt, dirección, periodicidad) antes que en palabras |
| Formas jurídicas y prefijo fijo de 8 caracteres | `parties.py` | Formas jurídicas derivadas del maestro de la fase (sufijos más frecuentes por país) + emparejado por tokens del nombre (bolsa de palabras con IDF calculada sobre el maestro) con el mismo criterio de «un único candidato claro» |
| Gramática de números impresos | `advices.py` `_number_keys`, `party_amount.py` `MIN_SUFFIX`/`MIN_CUT` | Inferir por sociedad, de sus propias facturas de la fase, el patrón (prefijo, año, separadores, longitud de secuencia) y generar las claves de búsqueda a partir de él; sin eso `KWI…` no se encuentra |
| Ventanas y constantes de días | `advices.py` `WINDOW`, `party_amount.py` 400 días, demoras de recibos | Calcularlas por fase a partir de lo ya casado por documento (mediana y p95 de días emisión → cobro por sociedad); ventanas más anchas con pagos más lentos |
| Umbrales de sobrepago y duplicado | `policy.py` | No se endurecen más con TRAIN: regla estructural (sobrepago solo con una única factura abierta del tercero y texto que la cita; duplicado solo con partida cerrada por cita, mismo tercero, mismo importe, > 1 día después). Si la precisión en holdout no llega a 0,95, la excepción se apaga en FINAL |
| Parsers de aviso por cabecera conocida | `advices.py` `_columns` | Detección de tabla por contenido: la columna cuyos valores casan con números de la sociedad y la columna de importes que suma el total; los campos de deducción y motivo por posición relativa. Lo que no se detecte va al modelo residual (PR 68, apagado) si hay sesión, y si no, pregunta |
| Tolerancias de disputa sin motivo | `policy.py` `_deducted` | Solo con deducción explícita en el aviso; sin motivo y fuera de descuento/retención, `PARTIAL` |

## 4. Plan de trabajo (por puntos esperados por hora; cada bloque con su puerta)

Puerta de entrada de toda PR: holdout **y** holdout-drift sin ningún segmento que baje más de 0,002, precisión de pares ≥ 0,995, ninguna clase de excepción con precisión < 0,95 (si no llega, se apaga), `unidentified` y `unidentified_lookalike` en 1,000, CSV determinista, RSS ≤ 7,5 GB, tiempo ≤ 150 s en holdout. Medir con `just be-score --compare` y `just be-diff`.

| # | Bloque | Objetivo medible | Esfuerzo [Inferencia] |
| --- | --- | --- | --- |
| 1 | **Test de generalización** antes de tocar reglas: holdout con una sociedad excluida de todo lo aprendido (índices de nombres, tabla de códigos, gramática de números construidos sin ella) y con un banco cuyos códigos no estén en la tabla; anotar la caída por segmento. Es la línea base de sobreajuste | tabla en `docs/ACCURACY_PLAN.md` §6 | 1 h |
| 2 | **Abonos netos y N:M** (`ar_1toN_credit_note`, `ar_n_to_m`, `ar_partial`): con el tercero resuelto, subconjunto de facturas menos cualquier subconjunto de abonos del tercero (ambos pequeños); reparto de parciales: comprobar en el golden de TRAIN cómo reparte un cobro que no cubre varias facturas (¿más antigua primero? ¿proporcional? ¿la citada?) y codificar **esa** regla, no `_oldest_first` por defecto | `ar_1toN_credit_note` ≥ 0,85, `ar_n_to_m` ≥ 0,7, `ar_partial` ≥ 0,85 en holdout | 2–3 h |
| 3 | **Tercero robusto** (`ar_ref_noise`, terceros): tokens del nombre con IDF del maestro de la fase, formas jurídicas derivadas, renombrados por `customer_name` de las facturas de la fase, matriz/grupo por `parent_customer_id`/`group_id`, ordenante «ORD.»/«EXPTE»/«CONFIRMING» → cliente citado; abstención si dos terceros claros | `ar_ref_noise` ≥ 0,93; terceros ≥ 0,8 | 2–3 h |
| 4 | **Gramática de números por sociedad** y ventanas por fase (sin constantes): claves de búsqueda generadas del patrón de cada sociedad; ventanas de aviso y de partidas previas por percentiles medidos | `ar_1toN_text` ≥ 0,93; holdout-drift ≥ holdout − 0,5 | 1–2 h |
| 5 | **Duplicado y sobrepago estructurales** (clases de 2 puntos) | precisión ≥ 0,95 en ambas o apagadas; `ar_duplicate_payment` ≥ 0,7 | 1 h |
| 6 | **PDF y descuentos**: cláusulas en los seis idiomas con pruebas sobre PDFs reales de cada sociedad; descuento sobre varias facturas y gracia; `ar_discount_late` | `ar_instalment` ≥ 0,95, `ar_short_discount` ≥ 0,95 | 1–2 h |
| 7 | **Reglas que faltan**: `ar_credit_note_paid_out` (nuestro cargo contra un `ARC` con rappel «pagado por transferencia» en el PDF), `ar_dd_represented_transfer` (cita del recibo o mandato devuelto), `ar_fx` sin `orig_amount` (contravalor con `fx_rates` ± 3 %) | cada uno ≥ 0,8 | 1–2 h |
| 8 | **Categorías estructurales** y vocabulario por maestro (§3) | holdout con banco excluido ≥ 0,9 en `nonitem_*` | 1 h |
| 9 | **Ensayo FINAL** con el holdout-drift y con el mutador de layout de aviso inventado: una ejecución completa cronometrada, `validate`, distribución por regla comparada con LIVE | run + validate < 5 min, RSS ≤ 7,5 GB | 30 min |

Orden recomendado: 1 → 2 → 3 → 5 → 4 → 6 → 7 → 8 → 9. Congelación de reglas a las **17:00**. FINAL se publica a las 18:00 y el envío único cierra a las 19:30.

## 5. Reglas del juego

- Una PR por bloque, contra `main`, con la tabla antes/después por segmento en holdout y holdout-drift, matriz de excepciones, tiempo y RSS. La orquestadora fusiona; nadie fusiona su propia PR.
- Ningún valor aprendido de TRAIN entra como constante nueva; si una regla necesita un parámetro, se calcula de los datos de la fase y se documenta en el README del backend.
- `policy.py` y `resolve.py` tienen un único dueño (esta sesión); las reglas nuevas van en `rules/`.
- Una medición pesada a la vez en la máquina (hay otras sesiones: frontend y rendimiento); pedir turno a la orquestadora para holdout; nada de TRAIN completo (`docs/PERF.md`: la escritura de explicaciones pediría ~21 GB).
- Nunca se envía nada a la clasificación; nunca se escribe en `db/` salvo `db/holdout*/`; `runs/` con nombres propios (`runs/acc-*`).
- Cada afirmación en el ESTADO con su medida; lo no medido se dice.

## 6. Línea base de generalización (bloque 1, medido el 7 nov a las 11:43)

Holdout con el código de `main`. Cada columna cambia una sola cosa. Pico de 6,96 a 7,49 GB por ejecución, una cada vez.

| Prueba | Holdout | Tabla sin fuga (`--before 2025-01-01`) | Sin bancos MONC y MEZQ en la tabla | Con layout de aviso inventado | Drift reconstruido |
| --- | --- | --- | --- | --- | --- |
| Score | 91,37 | 91,37 | 91,37 | **83,04** | 91,08 |
| Exactitud por movimiento | 0,9370 | 0,9370 | 0,9369 | 0,9251 | 0,9335 |
| Macro-F1 de excepciones | 0,820 | 0,820 | 0,820 | **0,652** | 0,815 |
| `ar_ref_noise` | 0,902 | 0,902 | 0,902 | 0,894 | 0,900 |
| `nonitem_*` (13.766) | 1,000 | 1,000 | 1,000 | 1,000 | 1,000 |
| `ar_1toN_remittance` | 0,988 | 0,988 | 0,988 | **0,427** | 0,973 |

**Sociedad y banco nuevos:** se sustituyó «sociedad excluida» porque nombres y números ya se indexan por fase: lo único aprendido de TRAIN es la tabla de códigos.

| Medida | Valor |
| --- | --- |
| MX01 (único banco, MEZQ), con y sin su banco en la tabla | 0,948 en ambas |
| MONC, con y sin su banco en la tabla | 0,8726 → 0,8712 |
| ZA01 en drift, frente a MA01 en holdout | 0,9177 frente a 0,9626 |

**Qué se lee**

- **La tabla de códigos no es un riesgo.** La fuga no mueve nada y quitar dos bancos solo baja `customer_refund` (1,000 → 0,958, n = 354). `nonitem_*` se mantiene en 1,000 por las reglas de texto.
- **El layout inventado es el mayor riesgo medido: −8,33 puntos.** Reescribe las cabeceras de los 2.815 avisos csv y xlsx de 6.762, así que es el peor caso, no una predicción. `_columns` los rechaza y se pierden `ar_1toN_remittance`, `ar_short_dispute` (0,801 → 0,319) y `ar_dispute_settlement` (0,860 → 0,523).
- **ZA01 en drift es pesimista.** Los avisos y PDF conservan la numeración FA/AV y sus importes sin doblar, y las partidas previas de TRAIN siguen como MA01. Parte de la diferencia viene del mutador, sin separar cuánta.
- **El 90,06 anterior era del mutador viejo.** El drift reconstruido da 91,08, y esa es la base de la puerta desde ahora.
