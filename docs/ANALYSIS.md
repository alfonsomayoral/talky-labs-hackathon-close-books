# ANALYSIS.md — Close the Books, análisis previo al hackathon

Análisis del problema, los datos y el repo, hecho el 6 nov 2026 (víspera del evento). Sirve para decidir qué construir el día 7. No describe ninguna implementación: eso vendrá después.

> **Fuentes y jerarquía.** `POLICIES.md` manda sobre el etiquetado; el paquete oficial (`db/bankrec-docs-and-masters/`) manda sobre la web ([hackathon.usetalky.com](https://hackathon.usetalky.com/) y sus secciones, leídas el 6 nov); la web y el paquete mandan sobre nuestros docs. Cada afirmación lleva su origen:
>
> - **[Paquete]** / **[Web]** / **[POLICIES §n]**: lo dice la fuente.
> - **[Medido]**: lo hemos medido sobre `db/train/` (TRAIN completo) y `db/live/` con los scripts de [`scripts/analysis/`](../scripts/analysis/README.md). Las tablas completas están en `runs/analysis/*.md` (ignorado por git; se regeneran con los scripts).
> - **[Inferencia]**: lo deducimos nosotros. No lo dice ninguna fuente ni lo hemos medido.
>
> **Reproducir:** `uv run scripts/analysis/01_volumes.py` … `05_baseline.py`. El baseline oficial se genera con `python3 -I db/bankrec-docs-and-masters/starter/starter.py --data db/bankrec-docs-and-masters --phase train --out runs/baseline/starter_train.csv.gz` (hay enlaces simbólicos `train/` y `live/` dentro de `db/bankrec-docs-and-masters/` para que el starter y `score_train.py` encuentren las fases).

## Índice

1. [El problema en una página](#1-el-problema-en-una-página)
2. [Revisión de nuestros docs](#2-revisión-de-nuestros-docs)
3. [Medición de los datos](#3-medición-de-los-datos)
4. [Baseline y techo de puntos por segmento](#4-baseline-y-techo-de-puntos-por-segmento)
5. [Mapa de oportunidades](#5-mapa-de-oportunidades)
6. [Diseños de pipeline candidatos](#6-diseños-de-pipeline-candidatos)
7. [Plan del día](#7-plan-del-día)
8. [Preguntas para la organización](#8-preguntas-para-la-organización)
9. [Decisiones que necesito de ti](#9-decisiones-que-necesito-de-ti)
10. [Anexos](#10-anexos)

---

## 1. El problema en una página

**Qué entra.** Por fase, los movimientos bancarios normalizados de un grupo de 17 sociedades (`bank_transactions.csv.gz`, con los extractos en bruto al lado en Norma 43, MT940 y camt.053), las partidas (facturas emitidas `ARI`, abonos emitidos `ARC`, facturas de proveedor `API`, abonos de proveedor `APC`), las partidas abiertas al inicio de la fase (solo LIVE y FINAL), los ficheros de detalle (remesas de recibos, liquidaciones de tarjeta, ingresos de cheques, remesas de pago) y los documentos sucios (avisos de remesa en csv/txt/xlsx/pdf y PDFs de facturas, abonos, proformas y cartas). Más los maestros (sociedades, cuentas, clientes, proveedores, categorías, condiciones de pago y tipos de cambio del BCE). **[Paquete: DATA_DICTIONARY]**

**Qué sale.** Un CSV por fase con `bank_txn_id,item_id,amount,category,exception`: una fila por partida que liquida el movimiento (importe en la divisa de la partida, positivo, con dos decimales) o una sola fila con `category` si no liquida ninguna; en cada fila, una `exception` de la lista cerrada o vacía. ≤ 60 MB sin comprimir, ≤ 3 M filas. **[Paquete: FORMAT]**

**Cómo se puntúa** (`bankrec_score.py`, el mismo código del servidor) **[Paquete: FORMAT, starter/bankrec_score.py]**:

> **Score = 100 × (0,5 · F1 de pares + 0,3 · exactitud por movimiento + 0,2 · macro-F1 de excepciones)**

| Métrica | Peso | Unidad | Qué cuenta |
| --- | --- | --- | --- |
| F1 de pares | 50 | el par `(movimiento, partida)` | Acierto si el par está en el golden y `\|importe − golden\| ≤ max(0,01; 0,5 %)`. Precisión = aciertos / pares enviados; recall = aciertos / pares del golden. **La excepción no influye** |
| Exactitud por movimiento | 30 | el movimiento | Correcto si su conjunto de (partida, importe ± tolerancia, excepción) es exactamente el del golden, o, sin partida, si coinciden categoría y excepción. Un movimiento que falta es incorrecto |
| Macro-F1 de excepciones | 20 | la clase | F1 de cada una de las 10 clases presentes en el golden, por fila, y media sin ponderar: **cada clase vale 2 puntos**, tenga 1.130 filas (`SHORT_BANK_CHARGES`) o 113.508 (`FX_DIFFERENCE`) |

**Qué cuesta cada error**, leído del código del evaluador **[Paquete]** y cuantificado con el golden de TRAIN (1.489.931 movimientos, 5.260.781 pares) **[Medido]**:

| Error | F1 de pares | Exactitud | Macro-F1 | Coste orientativo en TRAIN |
| --- | --- | --- | --- | --- |
| Movimiento sin fila | sus pares del golden son falsos negativos | el movimiento es incorrecto | si tenía excepción, falso negativo de esa clase | ≥ 30/1.489.931 = 0,00002 puntos cada uno; es el único error que no tiene ningún acierto posible |
| Una fila de más (par que no está en el golden) | baja la precisión | el movimiento pasa a incorrecto aunque el resto esté bien | si lleva excepción, falso positivo de la clase | un par de más cuesta lo mismo que un par de menos en el F1, y además rompe el movimiento |
| Importe fuera de tolerancia | el par no es acierto (cuenta como enviado y como no encontrado) | incorrecto | la excepción **sí** cuenta como acierto de clase si el par existe en el golden (el evaluador compara la excepción aunque el importe falle) | como una fila de más y una de menos a la vez |
| Excepción equivocada en un par correcto | ninguno | incorrecto | falso positivo de la clase puesta y falso negativo de la clase real: **se paga dos veces** | en una clase de 1.130 filas, cada fila vale 2/1.130 = 0,0018 puntos; en `FX_DIFFERENCE`, 0,00002 |
| Categoría equivocada en una fila sin partida | ninguno | incorrecto | solo si es `UNIDENTIFIED` (su excepción) | 0,00002 puntos de exactitud |
| Forzar un cobro `UNIDENTIFIED` contra una factura | un par de más | incorrecto | falso negativo de `UNIDENTIFIED` | el peor error: toca las tres métricas |

**Fases y envíos** **[Web: reglas, FAQ; Paquete: README]**: TRAIN (2021-07 → 2025-06, 1,49 M movimientos, con golden) se puntúa en local; LIVE (2025-07 → 2025-12, 203 k) se envía a la clasificación pública (un envío cada 3 min, 20 al día por fase, pedir la URL de subida ya gasta un hueco, un fichero inválido también); FINAL (2026-01 → 2026-06, 220 k) se publica a las 18:00, los envíos cierran a las 19:30 y **solo cuenta el primer fichero válido**. Un fichero rechazado por la validación no gasta el envío FINAL. Empates: el envío más temprano. Referencias de la web: naive ≈ 19, heurística ≈ 61, perfecto 100. **Entrega del proyecto antes de las 19:45:** vídeo (≤ 5 min, 720p), repo visible para el jurado y descripción (ideas clave, stack y modelos, siguientes pasos, miembros). «Además del CSV, el jurado valora vuestro enfoque.» **[Web: proyecto]**

**Hallazgo nuevo (importante para el día):** el evaluador oficial rechaza ficheros de más de 60 MB sin comprimir. El golden de TRAIN pesa **325 MB** sin comprimir (5,4 M filas) **[Medido]**, así que **una buena entrega de TRAIN no se puede puntuar con `score_train.py` tal cual**: solo pasa mientras el fichero es pequeño (el del starter, con una fila por movimiento, pesa 50 MB). Hay que puntuar TRAIN relajando `MAX_UNCOMPRESSED` en local (es la única diferencia; la métrica es idéntica, y `05_baseline.py` lo hace así y lo comprueba) o por trozos. Para LIVE/FINAL no hay problema: ~750 k filas rondan los 35 MB **[Inferencia a partir de 45 bytes por fila]**, pero conviene escribir sin comillas ni ceros de más y medir el tamaño antes de subir.

---

## 2. Revisión de nuestros docs

Contrastados `PROBLEM.md`, `ARCHITECTURE.md`, `CONTRACT.md` y `CLAUDE.md` (rama `KPI-4_problem-from-official-package`) con el paquete y la web. En general están bien y las cifras de `PROBLEM.md` §9 coinciden con las nuestras. Lo que hay que corregir o completar:

| Doc | Qué dice | Qué pasa | Qué hacer |
| --- | --- | --- | --- |
| PROBLEM §4, §7.4, ARCHITECTURE §1.3 | «Cada cambio se puntúa sobre `sample/` y TRAIN con `bankrec_score.py`» | **Error por omisión:** el evaluador rechaza > 60 MB; el golden de TRAIN pesa 325 MB (§1) | Documentar el límite y cómo se puntúa TRAIN en local (límite relajado o por trozos) |
| PROBLEM §5.5 | 50.891 avisos de remesa, 131.638 PDFs, 6.890 y 16.689 en LIVE | Cuentan la cabecera del `index.csv`: son 50.890, 131.637, 6.889 y 16.688 **[Medido]** | Corregir (menor) |
| PROBLEM §5.2, DATA_DICTIONARY | «TRAIN also includes invoices issued before 2021-07 that were still open» | **No cuadra con los datos:** 212.018 partidas emitidas en 2021-03…06 nunca se liquidan en el golden y tampoco están en `open_items_at_start` de LIVE (144.331 `ARI`, 59.660 `API`, 3.355 `ARC`, 2.306 `APC`). **[Inferencia]** Se pagaron antes del 2021-07-01 (o están dadas de baja): TRAIN **no trae su saldo inicial**. Además 967 partidas abiertas al inicio de LIVE tienen `open_amount` menor que el total sin ninguna asignación en el golden: cobros parciales anteriores a TRAIN | Para TRAIN, tratar las partidas anteriores a 2021-07 sin asignación como «estado inicial desconocido» (solo cuentan como candidatas si algo las cita). Preguntar a la organización (§8) |
| PROBLEM §5.4 / §12 | 47 cuentas en el maestro, 48 con movimientos en TRAIN y 49 en LIVE | La que falta en el maestro es **`IT01-VALD-EUR-2`** (11.890 movimientos en TRAIN, 1.689 en LIVE) y en LIVE además `ZA01-UMVC-ZAR` **[Medido]** | Nombrarla; el backend no puede depender de que toda cuenta esté en `bank_accounts.csv` |
| PROBLEM §4.1 | «Un gran cliente cambia el formato de sus avisos en septiembre de 2025» | Hemos identificado el cambio **[Medido]**: varios pagadores pasan de csv a un **xlsx nuevo** con columnas `Voucher, Invoice, PO, Inv. date, Amount, Deduction, Net paid`, donde `Invoice` es nuestro número **sin prefijo ni ceros** (`213397` por `FA250213397`) y `Voucher` es su comprobante (`VCHR…`). Catorce pagadores con ≥ 10 avisos cambian de formato; el que más, Landscapes Santa Lucia Springs LLC (US01) | Añadir el ejemplo al PROBLEM; el parser de avisos tiene que resolver números sin prefijo |
| PROBLEM §9.3 | Categorías «BANK_FEES (70 k)…» | Correcto. Falta decir que `nonitem_bank_fees_intl` (23.168) es la comisión aparte de una transferencia internacional (`POLICIES §4`) y que `ap_duplicate_refund` (483) es `SUPPLIER_REFUND` | Completar |
| PROBLEM §2 / web spainhackathons | — | La página de [spainhackathons](https://spainhackathons.com/events/claude-code-hackathon-close-the-books) describe **el reto antiguo** (libro mayor, pedidos, fraude): de ahí salió nuestra v0. Es la única fuente que lo dice; no vale para nada más | Nota a pie en PROBLEM |
| PROBLEM §7.3 | «La excepción no cuenta en el F1» | Correcto, y un matiz **[Paquete: código]**: en la macro-F1 una excepción cuenta como acierto si el par existe en el golden **aunque el importe esté fuera de tolerancia** | Añadir el matiz (afecta a cómo priorizar: la clase se gana antes que el importe) |
| ARCHITECTURE §7.1 `documents`, §9.1 | «Caché en `runs/cache/` por hash del fichero» | `runs/` está en `.gitignore`: la caché no viaja entre portátiles ni sobrevive a un clon. En FINAL los documentos son nuevos (≈ 17 k PDFs y ≈ 7 k avisos **[Inferencia por LIVE]**), así que la caché no ahorra nada ese día: lo que importa es que **los parsers deterministas cubran casi todo** y el modelo sea residual | Decidir dónde vive la caché (§9) y medir en LIVE qué porcentaje de documentos necesita modelo |
| ARCHITECTURE §7.3 | «El saldo abierto se lleva en orden de fecha. Parte de `open_items_at_start` más las partidas emitidas en la fase» | Vale para LIVE y FINAL. En TRAIN no hay `open_items_at_start` y hay 212 k partidas con estado inicial desconocido (arriba) | Decir cómo se trata TRAIN |
| ARCHITECTURE §9.2 | «el starter procesa TRAIN en minutos» | 54 s en este portátil (M-series, 18 núcleos) **[Medido]**; LIVE, 29 s; `score_train.py` sobre TRAIN, 17 s | Precisar |
| CONTRACT | `rule`, `sources`, `confidence` | Bien. Falta un campo para el **tercero resuelto** (`partyId`) y la **referencia extraída** del texto: son lo que la interfaz tiene que enseñar al revisor y lo que permite auditar un `FALLBACK` | Añadir `partyId` y `evidence.reference` (opcional) |
| CLAUDE §5 | «~200 k movimientos y ~1 M de partidas por fase (5,6 M en TRAIN)» | Correcto: LIVE trae 487 k + 199 k + 19,5 k partidas nuevas y 325 k abiertas al inicio; TRAIN 3,96 M + 1,53 M + 150 k **[Medido]** | — |
| CLAUDE §7 | `just be-check`, `just be-test`, `just be-run`, `just be-score` «cuando exista backend/» | No existen aún en el `justfile`. `be-score` tiene que resolver el límite de 60 MB | Añadirlos con el backend |
| Web /datos | «Norma 43 (.txt)» | Los ficheros son `.n43` (como dice el diccionario) | Nada: manda el paquete |
| Web FAQ | «Te mostramos hasta 20 errores» | El evaluador devuelve hasta 50 (`MAX_ERRORS`) | Nada |

Supuestos sin respaldo que había en los docs y que ahora están medidos o desmentidos: «el starter usa ~8 GB» (no lo hemos medido; tarda 54 s); «ZA01 en LIVE son pagos de proforma → `CUSTOMER_ADVANCE`» (sigue siendo inferencia: los dos textos dicen `PROFORMA PF25-0100001/2`, que no existen como partidas en LIVE **[Medido]**, así que la etiqueta coherente con `POLICIES §4` es `CUSTOMER_ADVANCE`).

---

## 3. Medición de los datos

Todo lo de esta sección es **[Medido]** salvo que se marque otra cosa. Scripts: `01_volumes.py`, `02_golden.py`, `03_sources.py`, `04_drift.py`.

### 3.1 Volúmenes por fase

| | TRAIN | LIVE | FINAL **[Web]** |
| --- | --- | --- | --- |
| Periodo | 2021-07-01 → 2025-06-30 | 2025-07-01 → 2025-12-31 | 2026-01-01 → 2026-06-30 |
| Movimientos | 1.489.931 (916.487 cobros · 573.444 pagos) | 203.083 (124.428 · 78.655) | ~220.000 |
| Cuentas · sociedades · divisas | 48 · 17 · 11 | 49 · 18 (ZA01 con 2 movimientos) · 12 (ZAR) | +1 banco nuevo (ZA01) |
| Facturas emitidas · recibidas · abonos | 3.963.735 · 1.530.203 · 150.215 | 487.243 · 199.414 · 19.500 | — |
| Partidas abiertas al inicio | no hay | 325.419 (229.534 `ARI`, 68.356 `API`, 25.434 `ARC`, 2.095 `APC`; 32.091 con saldo parcial) | sí |
| Remesas de recibos (ficheros · filas · remesas) | 1.440 · 713.554 · 12.505 | 180 · 93.786 · 1.590 | — |
| Liquidaciones de tarjeta | 240 · 147.622 · 10.051 | 30 · 19.110 · 1.265 | — |
| Ingresos de cheques | 816 · 42.284 · 15.231 | 102 · 6.083 · 1.967 | — |
| Remesas de pago (ficheros · filas · remesas) | 1.056 · 1.420.037 · 2.945 | 132 · 205.713 · 386 | — |
| Avisos de remesa | 50.890 (csv 18.889 · pdf 16.669 · txt 12.950 · xlsx 2.382) | 6.889 (2.381 · 2.196 · 1.815 · 497) | — |
| PDFs | 131.637 (facturas 75.863 · fact. proveedor 27.765 · abonos 14.638 · abonos prov. 10.499 · proformas 2.239 · cartas de IBAN 633) | 16.688 | — |
| Filas del golden | 5.403.411 (5.260.781 pares + 142.630 sin partida) | oculto | oculto |
| En disco | 2,0 GB | 278 MB | — |

**Por formato de extracto** (TRAIN; LIVE en proporción): camt.053 736.151 movimientos en 14 cuentas (todo HPNB, RHEI, WATT, y MONC desde 2025-10), MT940 436.887 en 18 (LORV, VALD, NORT, MEZQ, CAZU, LING, UMVC), Norma 43 316.893 en 16 (PENA, MONC hasta 2025-09, RIBA). Las columnas que solo trae camt están rellenas en el 46 % de los movimientos (`counterparty_name`), 44 % (`end_to_end_id`), 40 % (`remittance_info`) y 10 % (`counterparty_account`); `orig_currency` solo en el 1,1 %.

**Por sociedad** (movimientos TRAIN · LIVE): US01 452.690 · 60.470 (el 30 %: tres cuentas USD en camt, ACH y lockbox), ES01 176.011 · 23.315 (seis cuentas N43: SEPA, confirming, TPV), AU01 121.560 · 16.537, FR01 120.442 · 16.059, CN01 80.252 · 10.898, ES00 78.808 · 11.264 (la cabecera: 7.922 cobros frente a 70.886 pagos; cash pool, fábrica de pagos, divisas), DE01 66.998, IT01 57.840, BR01 48.591, MX01 46.265, NL01 45.339, PT01 39.753, PL01 36.634, UK01 36.123, CH01 28.300, MA01 28.179, ES02 26.146.

**Por divisa** (movimientos TRAIN): EUR 609 k (26 cuentas), USD 455 k (10), AUD 121 k, CNY 78 k, BRL 49 k, MXN 45 k, GBP 36 k, PLN 36 k, CHF 28 k, MAD 28 k, CAD 5 k. Las facturas emitidas van en 11 divisas; `ar_invoices` de ES01 y CN01 incluyen USD, PL01 EUR y PLN, MA01 EUR y MAD: ahí nacen los cruces de divisa.

**Partidas:** facturas emitidas por método de pago: transfer 2,99 M, recibo domiciliado 762 k, tarjeta 161 k, cheque 46 k. Condiciones con descuento por pronto pago: `D2N30US` 342 k, `D2N30` 141 k, `D1N60` 134 k (el 15,6 % de las facturas). `customer_po` informado en el 59 %. Abonos: devolución/rectificación 73,7 k, abono de proveedor 52,5 k, **anulación de factura 12,8 k** (nunca se liquidan por banco, `POLICIES §5.7`), rappel 11,2 k. `related_document` en el 92,5 %.

### 3.2 El golden de TRAIN

**Forma.** 72 segmentos. Dificultad por movimiento: 1 → 27,4 %, 2 → 43,8 %, 3 → 28,8 % (es constante por segmento, salvo tres mixtos). Partidas por movimiento:

| Partidas por movimiento | Movimientos | Pares | Lectura |
| --- | --- | --- | --- |
| 0 (categoría) | 142.630 (9,6 %) | 0 | solo exactitud y, en `UNIDENTIFIED`, macro-F1 |
| 1 | 871.295 (58,5 %) | 871.295 (16,6 %) | dominan la exactitud |
| 2–4 | 303.152 | 809.872 | |
| 5–9 | 102.211 | 647.669 | |
| 10–49 | 59.879 | 1.158.724 | |
| 50+ | 10.764 (0,7 %) | 1.773.221 (33,7 %) | dominan el F1: remesas, avisos, tarjetas, pagos agregados (máximo: 1.540) |

Pares por tipo de partida: `ARI` 3.721.209, `API` 1.434.394, `ARC` 56.930, `APC` 48.248.

**Segmentos, en movimientos (exactitud) y en pares (F1).** Las dos columnas de porcentaje son las dos métricas grandes; `items/mov` dice si el segmento se gana por el F1 o por la exactitud.

| Segmento | Movs | % movs | Pares | % pares | items/mov | Dif. | Excepción dominante |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `ar_ref_noise` | 312.717 | 21,0 | 676.604 | 12,9 | 2,2 | 2,6 | — |
| `ap_payment_multi` | 174.406 | 11,7 | 598.314 | 11,4 | 3,4 | 2 | — |
| `ar_1to1` | 141.038 | 9,5 | 141.038 | 2,7 | 1 | 1 | — |
| `ap_payment_single` | 139.376 | 9,3 | 139.376 | 2,6 | 1 | 1 | — |
| `ar_same_amount_fifo` | 49.049 | 3,3 | 49.049 | 0,9 | 1 | 3 | — |
| `nonitem_bank_fees` | 46.984 | 3,1 | 0 | 0 | 0 | 1 | cat. `BANK_FEES` |
| `ar_1toN_text` | 46.644 | 3,1 | 259.925 | 4,9 | 5,6 | 2 | 985 `SHORT_DISCOUNT` |
| `ar_short_discount` | 42.704 | 2,9 | 48.081 | 0,9 | 1,1 | 2 | `SHORT_DISCOUNT` 42.704 |
| `ap_direct_debit` | 41.335 | 2,8 | 41.335 | 0,8 | 1 | 2,8 | — |
| `ar_same_amount_month` | 33.429 | 2,2 | 33.429 | 0,6 | 1 | 3 | — |
| `ap_paid_by_holding` | 33.363 | 2,2 | 82.599 | 1,6 | 2,5 | 2 | — (solo ES00) |
| `ar_instalment` | 33.008 | 2,2 | 33.008 | 0,6 | 1 | 3 | `PARTIAL` 22.994, vacía 9.859 (último plazo) |
| `ar_partial` | 27.750 | 1,9 | 27.750 | 0,5 | 1 | 2 | `PARTIAL` 13.886, vacía 13.864 (el resto) |
| `ar_dd_returned` | 26.397 | 1,8 | 26.397 | 0,5 | 1 | 2 | `RETURNED` |
| `unidentified` | 24.299 | 1,6 | 0 | 0 | 0 | 2 | `UNIDENTIFIED` |
| `ar_1toN_credit_note` | 23.466 | 1,6 | 229.078 | 4,3 | 9,8 | 2 | — (abonos netos) |
| `nonitem_bank_fees_intl` | 23.168 | 1,6 | 0 | 0 | 0 | 1 | cat. `BANK_FEES` |
| `ap_credit_note_netted` | 18.475 | 1,2 | 90.243 | 1,7 | 4,9 | 2 | — |
| `ap_partial` | 18.131 | 1,2 | 83.124 | 1,6 | 4,6 | 2 | `PARTIAL` 18.725 |
| `ap_supplier_refund` | 17.795 | 1,2 | 17.795 | 0,3 | 1 | 2,6 | — (liquida el `APC`) |
| `ar_cheque_deposit` | 15.231 | 1,0 | 42.284 | 0,8 | 2,8 | 2 | — |
| `ar_n_to_m` | 13.904 | 0,9 | 50.776 | 1,0 | 3,7 | 3 | `PARTIAL` 6.937 |
| `nonitem_cash_pool` | 12.576 | 0,8 | 0 | 0 | 0 | 1 | cat. `CASH_POOL` |
| **`ar_dd_batch`** | 12.505 | 0,8 | **713.554** | **13,6** | 57,1 | 1 | — |
| `ap_factored` | 10.934 | 0,7 | 26.777 | 0,5 | 2,4 | 2 | — |
| `unidentified_lookalike` | 10.354 | 0,7 | 0 | 0 | 0 | 3 | `UNIDENTIFIED` |
| `ar_short_withholding` | 10.148 | 0,7 | 35.160 | 0,7 | 3,5 | 2 | `SHORT_WITHHOLDING` 33.729 |
| `ar_card_settlement` | 10.051 | 0,7 | 147.622 | 2,8 | 14,7 | 1 | — |
| **`ar_1toN_remittance`** | 9.423 | 0,6 | **388.502** | **7,4** | 41,2 | 2,6 | `SHORT_DISCOUNT` 47.047 |
| **`ap_fx`** | 8.604 | 0,6 | **333.754** | **6,3** | 38,8 | 2 | `FX_DIFFERENCE` 14.763, `PARTIAL` 6.343 |
| `ar_dispute_settlement` | 7.784 | 0,5 | 7.784 | 0,1 | 1 | 2 | vacía (pago de lo disputado) |
| `ar_dd_represented_transfer` | 7.568 | 0,5 | 7.568 | 0,1 | 1 | 3 | — |
| **`ar_short_dispute`** | 7.553 | 0,5 | **688.803** | **13,1** | 91,2 | 3 | `SHORT_DISPUTE` 17.975, `SHORT_DISCOUNT` 7.888, `PARTIAL` 2.840 |
| `ar_retention` | 6.643 | 0,4 | 6.643 | 0,1 | 1 | 3 | `PARTIAL` |
| `ap_confirming` | 6.387 | 0,4 | 61.199 | 1,2 | 9,6 | 2 | — |
| `ar_fx` | 6.146 | 0,4 | 101.731 | 1,9 | 16,6 | 3 | `FX_DIFFERENCE` 97.501 |
| `ar_discount_late` | 5.837 | 0,4 | 20.350 | 0,4 | 3,5 | 3 | `PARTIAL` 6.799 |
| `ar_third_party_confirming` | 4.998 | 0,3 | 4.998 | 0,1 | 1 | 2 | — (ES01) |
| `ar_duplicate_payment` | 4.436 | 0,3 | 4.436 | 0,1 | 1 | 2 | `DUPLICATE_PAYMENT` |
| `ar_retention_release` | 4.145 | 0,3 | 4.145 | 0,1 | 1 | 3 | vacía |
| `nonitem_payroll` · `_intercompany` · `_leasing` · `_bank_reversal` | 3.897 · 3.187 · 2.832 · 2.664 | | 0 | | | 1 | categoría |
| `ar_overpayment` | 2.817 | 0,2 | 2.817 | 0,1 | 1 | 2 | `OVERPAYMENT` |
| `ar_third_party_agency` | 2.636 | 0,2 | 5.615 | 0,1 | 2,1 | 3 | mixtas |
| `customer_refund` · `customer_advance` | 2.611 · 2.008 | | 0 | | | | categoría |
| `ar_replaced_invoice` | 2.024 | 0,1 | 4.486 | 0,1 | 2,2 | 3 | mixtas |
| `ar_advance_deduction` | 2.003 | 0,1 | 2.003 | 0,0 | 1 | 3 | `PARTIAL` |
| `nonitem_internal_transfer` · `_fx_deal` | 1.936 · 1.551 | | 0 | | | 1 | categoría |
| `ar_third_party_parent` | 1.298 | 0,1 | 10.219 | 0,2 | 7,9 | 2,1 | — |
| `ap_returned_transfer` | 1.192 | 0,1 | 3.134 | 0,1 | 2,6 | 2 | `RETURNED` |
| `ar_new_iban` | 1.122 | 0,1 | 1.951 | 0,0 | 1,7 | 3 | — |
| `ar_short_bank_charges` | 1.121 | 0,1 | 1.121 | 0,0 | 1 | 2 | `SHORT_BANK_CHARGES` |
| `nonitem_tax_payment` · `_loan_repayment` · `_social_security` · `_card_expenses` | 957 · 832 · 816 · 718 | | | | | 1 | categoría |
| `ar_cheque_returned` · `ap_duplicate_payment` · `ap_duplicate_refund` · `ar_credit_note_paid_out` · `ar_card_chargeback` | 538 · 491 · 483 · 325 · 289 | | | | | 2 | `RETURNED` · `DUPLICATE_PAYMENT` · cat. `SUPPLIER_REFUND` · — · `RETURNED` |
| `nonitem_interest_income` · `_insurance` · `_interest_expense` · `ar_1to1_remittance` · `nonitem_loan_drawdown` · `ap_payment_run_aggregated` · `nonitem_tax_refund` | 320 · 220 · 181 · 60 · 32 · 5 · 4 | | | | | | (`ap_payment_run_aggregated`: 5 movimientos, 4.501 pares) |

**Lecturas:**

- **Cuatro segmentos son la mitad de los pares** (`ar_dd_batch`, `ar_short_dispute`, `ar_ref_noise`, `ap_payment_multi`: 50,9 %) y con `ar_1toN_remittance`, `ap_fx`, `ar_1toN_text` y `ar_1toN_credit_note` llegan al 74 %. Tres de ellos tienen **un fichero que dice la respuesta** (remesa de recibos, remesa de pago, aviso de remesa).
- **La exactitud la dominan los 1:1**: `ar_ref_noise` + `ar_1to1` + `ap_payment_single` + `ar_same_amount_*` + `ap_direct_debit` son el 50 % de los movimientos y casi todos de una partida.
- **Excepciones (filas):** `FX_DIFFERENCE` 113.508 (en 15.837 movimientos: `ar_fx`, `ap_fx`), `SHORT_DISCOUNT` 100.174 (44.692 movs), `PARTIAL` 91.664 (79.491 movs, 17 segmentos), `UNIDENTIFIED` 34.653, `SHORT_WITHHOLDING` 33.818 (10.210 movs), `RETURNED` 30.358, `SHORT_DISPUTE` 20.238 (8.273 movs), `DUPLICATE_PAYMENT` 4.927, `OVERPAYMENT` 2.838, `SHORT_BANK_CHARGES` 1.130. **Las cuatro últimas valen 8 puntos entre 9.000 filas.**
- **Categorías (142.630 filas sin partida):** `BANK_FEES` 70.152, `UNIDENTIFIED` 34.653, `CASH_POOL` 12.576, `PAYROLL` 3.897, `INTERCOMPANY` 3.187, `LEASING` 2.832, `BANK_REVERSAL` 2.664, `CUSTOMER_REFUND` 2.611, `CUSTOMER_ADVANCE` 2.008, `INTERNAL_TRANSFER` 1.936, `FX_DEAL` 1.551, `TAX_PAYMENT` 957, `LOAN_REPAYMENT` 832, `SOCIAL_SECURITY` 816, `CARD_EXPENSES` 718, `SUPPLIER_REFUND` 483, `INTEREST_INCOME` 320, `INSURANCE` 220, `INTEREST_EXPENSE` 181, `LOAN_DRAWDOWN` 32, `TAX_REFUND` 4.
- **¿Basta el código del banco para la categoría?** Casi: la categoría mayoritaria de cada combinación (banco, `bank_code`, `bank_subcode`) acierta el **95,5 %** de las filas sin partida; 109 de las 149 combinaciones son puras (p. ej. `PENA 17/310` → `BANK_FEES`, `RHEI CAMT/ACCB/ZABA` → `CASH_POOL`, `LORV NSAL` → `PAYROLL`). Lo que falla es lo esperable: los códigos genéricos de transferencia (`NTRF`, `PMNT/RCDT/ESCT`, `04/099`) mezclan `UNIDENTIFIED` con `CUSTOMER_REFUND`, `INTERCOMPANY`… y, sobre todo, **mezclan movimientos con y sin partida** (31 combinaciones, 1,28 M movimientos): el código no decide si hay factura; solo decide la categoría una vez que no la hay.

### 3.3 Qué fuente resuelve cada segmento

Para cada par del golden hemos buscado el número impreso de la partida en el texto del banco (estricto, o sus dígitos sin prefijo), en los ficheros de detalle, en el conjunto de todos los avisos de remesa de la fase (csv, txt, xlsx y pdf leídos como texto) y en el índice de PDFs; y para cada movimiento, si el importe es exactamente la suma de sus partidas (misma divisa, abonos en negativo) y si los diez primeros caracteres del nombre del tercero aparecen en el texto. Porcentaje de **movimientos cuyas partidas se encuentran todas** en la fuente (`03_sources.py`; las columnas `advice` y `detail` sobrestiman un poco porque buscan en todos los ficheros de la fase, no en el que toca):

| Segmento | Nº en texto (estricto / dígitos) | Importe exacto | Nombre en texto | Nombre + importe | Fichero de detalle | Aviso de remesa | PDF | `counterparty_name` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ar_1to1` | 98,7 / 98,7 | 100 | 93,5 | 93,5 | 14,5 | 19,4 | 1,5 | 51,2 |
| `ar_ref_noise` | **0,0 / 2,9** | **100** | **93,0** | **93,0** | 11,2 | 21,8 | 2,7 | 54,2 |
| `ar_same_amount_fifo` · `_month` | 0 / 0 | 99,6 | 93 | 93 | 15 | 18 | 3,9 | 50 |
| `ar_1toN_text` | 29,7 / 46,0 | 99,9 | 93,7 | 93,6 | 2,4 | 26,4 | 7,3 | 62,8 |
| `ar_1toN_credit_note` | 0,0 / 6,1 | 99,1 | 92,7 | 91,8 | 2,5 | 23,7 | 10,6 | 59,7 |
| `ar_1toN_remittance` | 0 / 0 | 87,9 | 95,1 | 83,8 | 0,1 | **99,9** | 36,8 | 59,4 |
| `ar_short_dispute` | 0 / 0 | 98,8 | 90,6 | 89,5 | 0,0 | **84,8** | 57,4 | 63,9 |
| `ar_dd_batch` | 0 / 0 | 100 | 0 | 0 | 44,5 (pares: 94,1) | 4,2 | 36,1 | 0 |
| `ar_card_settlement` | 0 / 0 | 0 (es el neto) | 0 | 0 | **100** | 0 | 0 | 41,1 |
| `ar_cheque_deposit` | 0 / 0 | 100 | 0 | 0 | 43,4 (pares: 70,1) | 0,9 | 5,0 | 0 |
| `ar_dd_returned` | 0 / 0 | 100 | 89,4 | 89,4 | **96,6** | 13,7 | 1,3 | 64,5 |
| `ar_short_discount` | 31,7 / 33,2 | 0 (falta el descuento) | 95,8 | 0 | 12,2 | 19,2 | 1,3 | 85,4 |
| `ar_short_withholding` | 30,3 / 33,9 | 0 (falta la retención) | 95,5 | 0 | 3,3 | 10,7 | 2,8 | 0 |
| `ar_short_bank_charges` | 24,2 / 26,9 | 0 | 96,1 | 0 | 8,8 | 10,2 | 0,4 | 72,6 |
| `ar_overpayment` | 34,9 / 37,3 | 0 (sobra dinero) | 93,9 | 0 | 12,9 | 17,9 | 1,3 | 51,0 |
| `ar_fx` | 14,4 / 16,5 | 0 (otra divisa; `orig_currency` 100 %) | 91,1 | 0 | 2,4 | 28,2 | 13,2 | 50,7 |
| `ar_instalment` · `ar_retention` · `ar_advance_deduction` · `ar_retention_release` | 70 / 71 · 36 / 38 · 34 / 37 · 53 / 68 | 98 (el plazo) | 93 | 91 | 12 | 15 | **100** | 60 |
| `ar_partial` | 50,5 / 52,2 | 100 | 92,8 | 92,8 | 14,8 | 19,7 | 1,2 | 50,7 |
| `ar_duplicate_payment` | 35,5 / 38,2 | 100 | 92,3 | 92,3 | 14,3 | 18,8 | 1,4 | 51,2 |
| `ar_replaced_invoice` | 0 / 0 (cita la anulada) | 91,2 | 92,2 | 84,0 | 10,4 | 21,6 | **100** | 59,1 |
| `ar_new_iban` | 0 / 0 | 100 | 83,9 | 83,9 | 22,4 | 33,4 | 2,3 | 16,6 |
| `ar_third_party_confirming` · `_parent` · `_agency` | 42 / 60 · 31 / 44 · 0 / 23 | 100 · 100 · 90 | 78 · 29 · 96 | 78 · 29 · 86 | 17 · 11 · 13 | 1 · 62 · 24 | 2 · 11 · 3 | 0 · 41 · 62 |
| `ap_payment_single` | 89,6 / 89,6 | 100 | 89,7 | 89,7 | **89,3** | 26,3 | 12,8 | 46,6 |
| `ap_payment_multi` | 74,1 / 74,1 | 100 | 89,1 | 89,1 | **89,1** | 22,9 | 24,0 | 46,7 |
| `ap_paid_by_holding` | 21,6 / 21,6 | 100 | 32,5 | 32,5 | **90,9** | 23,4 | 18,3 | 0 |
| `ap_partial` · `ap_credit_note_netted` | 63 / 63 · 59 / 61 | 100 · 100 | 83 · 84 | 83 · 84 | **90 · 89** | 23 · 22 | 25 · 39 | 42 |
| `ap_fx` | 87,0 / 87,0 | 0 (otra divisa) | 96,0 | 0 | **83,4** | 24,4 | 19,6 | 32,0 |
| `ap_confirming` | 0 / 0 | 100 | 0 | 0 | **73,1** (pares: 90,4) | 11,4 | 42,4 | 0 |
| `ap_factored` | 74,6 / 74,6 | 100 | 0 (paga al factor) | 0 | **86,7** | 19,7 | 58,6 | 39,4 |
| `ap_direct_debit` | 34,7 / 34,7 | 100 | 90,6 | 90,6 | 88,7 | 24,8 | 16,0 | 47,1 |
| `ap_supplier_refund` | 39,5 / 53,0 | 0 | 90,3 | 0 | 44,3 | 22,7 | 22,4 | 47,4 |
| `ap_returned_transfer` | 0 / 0 | 98,1 | 89,8 | 87,8 | **89,6** | 26,9 | 22,7 | 39,9 |

Totales sobre los movimientos con partida: número en el texto 41 % (43 % con dígitos), importe exacto 90 %, fichero de detalle 41 %, aviso 22 %, PDF 14 %. Sobre los pares: texto 22 %, fichero 49 %, aviso 39 %.

**Candidatos por importe** para los movimientos de una sola partida (facturas de la misma sociedad, divisa e importe emitidas en los 400 días anteriores, sin descontar las ya pagadas): `ar_ref_noise` **74,9 %** tiene un único candidato, 24,4 % entre 2 y 5; `ar_1to1` 66,6 % / 22,7 % / 10,6 % con más de 5; `ap_payment_single` 92 %; `ap_direct_debit` 87 %; `ar_same_amount_fifo` y `_month` **86 % con más de 5** (de ahí el nombre); `ar_dd_returned` 53 % con más de 5 (recibos de importe fijo). Con el saldo abierto y el tercero, la ambigüedad baja mucho **[Inferencia]**.

**Cómo es el ruido de `ar_ref_noise`** (muestra; `02_golden.py`): N43 `TRANSFERENCIA DE CONSTRUCCIONES LOMASE | CA S.L.` (nombre cortado a 38 y partido entre campos), `TRANSF. A SU FAVOR | 63327227-SPA VEGALTA S.L. | LIQUIDACION`; MT940 `PIX RECEBIDO MSP PISCINAS S.A.`, `TT IN XINLAN POOL SUPPLY CO., LTD. N/REF 2024-3328`, `VIR SEPA RECU /DE SPA RONCEVAL SAS /MOTIF FACT FA220124238 111794 112131` (varias facturas, unas con prefijo y otras no); camt `SEPA-UEBERWEISUNG EREF+NOTPROVIDED SVWZ+RECHNUNG 202731` con `counterparty_name` limpio, `ACH CREDIT SANTA LUCIA SPRI CCD PAYMENT ID:… RMR*IV*101230*PI*503.47` (número sin prefijo en un segmento EDI). El tercero casi siempre está; el número casi nunca entero.

### 3.4 Drift TRAIN → LIVE → FINAL

| Cambio | Fuente | Qué hemos visto |
| --- | --- | --- |
| **Banco del Moncayo, N43 → camt.053 el 2025-10-01** | POLICIES §6 | Confirmado: 7.300 movimientos MONC en N43 (jul–sep) y 6.583 en camt (oct–dic). El texto cambia de `TRANSFERENCIAS RAFAEL VIDAL ORTIZ \| RAFAEL VID PAGO FACTURA 110623` (nombre y referencia dentro de `text`, cortados) a `TRANSFERENCIA SEPA DE MLF FERRETERÍA S.COOP.` con `counterparty_name`, `remittance_info` (`PAGO FRA. FV25-0220471`) y `end_to_end_id` separados. **El código N43 sobrevive en `bank_subcode`** (`04532`, `17701`…) junto al `bank_code` ISO (`PMNT/RCDT/ESCT`), como dice el diccionario. 12.178 movimientos de LIVE tienen una plantilla de texto (formato, banco, dos primeras palabras) nunca vista en TRAIN; 11.700 de ellos son MONC en camt. Las reglas que lean el tercero y la referencia de `counterparty_name`/`remittance_info` cuando existan, y del texto si no, no necesitan nada especial |
| **Cambio de formato de avisos en septiembre de 2025** | POLICIES §5.4, §6 | 14 pagadores con ≥ 10 avisos cambian de formato en LIVE, casi todos de csv a un **xlsx nuevo**: hoja `Remittance`, cabecera con el nombre, `Payment advice`, nº y fecha, y columnas `Voucher, Invoice, PO, Inv. date, Amount, Deduction, Net paid`, con el número **sin prefijo ni ceros** (`213397` = `FA250213397`) y el `PO` del cliente. Los xlsx de TRAIN tenían `Document, Date, Gross, Deduction, Reason, Paid` con el número completo. Los xlsx pasan de 50/mes a 100/mes desde septiembre. Los avisos csv (`payment_ref,…` + `document,doc_date,gross,discount_or_deduction,reason,paid,your_order`), txt (correo con la lista) y pdf (`REMITTANCE ADVICE` con tabla) no cambian |
| **ZA01 / ZAR** | POLICIES §6, README | En LIVE ya hay 2 movimientos de `ZA01-UMVC-ZAR` (29 y 30 dic 2025, MT940, `EFT CREDIT POOL & SPA TAYLOR LTD PROFORMA PF25-0100001` y `/ORDP/OUTDOOR LIVING ASHBRIDGE LTD/REMI/PROFORMA PF25-0100002`). Ni la sociedad ni la cuenta están en los maestros; no hay ninguna partida `KWI…` en LIVE. FINAL traerá `final/masters_final/`, las partidas de ZA01 y un cambio de nombre el 2026-04-01 |
| **IT01 cambia de cuenta de cobros el 2026-02-01** | POLICIES §5.11 | Es FINAL. Pero ya hoy IT01 tiene una cuenta, **`IT01-VALD-EUR-2`, que no está en el maestro** (250 movimientos/mes). Las dos son válidas |
| **Clientes nuevos, renombrados, bloqueados** | POLICIES §5.5, §6 | LIVE factura a 41.220 clientes; 1.515 no aparecen en TRAIN; ninguno falta en el maestro. 143 clientes tienen más de un nombre en las facturas de TRAIN (renombrados; el maestro trae el actual y las facturas antiguas el antiguo). El maestro marca 10.627 clientes y 1.754 proveedores como bloqueados. El `counterparty_name` de camt coincide exactamente con un nombre del maestro en el 96,6 % (TRAIN) y 96,9 % (LIVE) |
| **«Payment behaviour gets slower in 2026»** | POLICIES §6 | En TRAIN no se mueve: mediana de 49 días desde la emisión y 8–9 sobre el vencimiento todos los años; 20 % paga con más de 30 días de retraso. Es FINAL: ventanas de fecha generosas (no filtrar candidatos por «vencido hace poco») |
| **Solapes de Banca Ribagorza** | DATA_DICTIONARY | Solo afectan a los extractos en bruto; `bank_transactions.csv.gz` ya está deduplicado. No hay que leer los extractos en bruto para nada **[Inferencia]** |
| **Estado inicial** | DATA_DICTIONARY | `open_items_at_start` de LIVE se reproduce desde TRAIN + golden **para todas las partidas que están en él** (325.419 en ambos, 0 solo en el fichero, 967 con importe distinto por cobros anteriores a TRAIN); lo que no se reproduce son las 233 k partidas que ni se liquidan ni aparecen (§2). Regla de cálculo que cuadra: saldo = total − Σ importes del golden, sumando los `RETURNED` de vuelta y sin restar los `DUPLICATE_PAYMENT` (13 partidas quedan negativas: sobrepagos) |

---

## 4. Baseline y techo de puntos por segmento

**Baseline oficial** (`starter.py`, número impreso en el texto + importe exacto; lo demás `UNIDENTIFIED` si es cobro y `BANK_FEES` si es pago), puntuado con `bankrec_score.py` **[Medido]**:

| Fase | Score | F1 pares | Precisión | Recall | Exactitud | Macro-F1 | Filas | Tiempo del starter | Tiempo del evaluador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TRAIN | **11,68** | 0,089 | 0,993 | 0,047 | 0,235 | 0,009 | 1.489.931 (247.445 casadas) | 54 s | 17 s (carga 7 s + puntuación 4 s) |
| sample (jun 2025, 8.499 movs) | 11,28 | 0,073 | 0,999 | 0,038 | 0,248 | 0,008 | 8.499 | 0,4 s | < 1 s |
| LIVE | no se envía | — | — | — | — | — | 203.083 (33.577 casadas) | 29 s | — |

Qué acierta el starter: `ar_1to1` 98,7 %, `nonitem_bank_fees` y `nonitem_bank_fees_intl` 100 % (por casualidad: todo pago sin casar es `BANK_FEES`), `unidentified` y `unidentified_lookalike` 100 % (por casualidad: todo cobro sin casar es `UNIDENTIFIED`, y eso le cuesta 732.099 falsos positivos de esa clase), `ap_payment_single` 58 %, `ar_dd_represented_transfer` 47 %. Todo lo demás, 0. Su precisión de pares es 0,993: la regla «número entero en el texto + importe exacto» casi no se equivoca.

**Techo por segmento.** `05_baseline.py` replica el evaluador en Polars (reproduce 11,68 y las tres métricas al sexto decimal) y calcula, para cada segmento, (a) cuánto sube la puntuación global si **solo ese segmento** pasa a perfecto partiendo del baseline y (b) cuánto se pierde si **todo lo demás es perfecto** y solo ese segmento se queda como lo deja el starter. Tres de los valores de (a) están verificados sustituyendo el segmento por el golden y pasando el fichero por el evaluador oficial: `ar_dd_batch` 22,89, `ar_ref_noise` 28,54, `ar_short_dispute` 24,75, idénticos a los predichos. Las ganancias no son aditivas (F1 y macro-F1 no son lineales): suman 125 cuando el margen es 88,3.

| Segmento | Movs | Pares | (a) sube si es perfecto | (b) se pierde si solo falla él | Por qué |
| --- | --- | --- | --- | --- | --- |
| `ar_ref_noise` | 312.717 | 676.604 | **16,9** | **11,4** | 21 % de los movimientos y 13 % de los pares |
| `ar_short_dispute` | 7.553 | 688.803 | **13,1** | 5,6 | 13 % de los pares en 7,5 k avisos; lleva `SHORT_DISPUTE` (2 pts) |
| `ap_payment_multi` | 174.406 | 598.314 | **12,9** | 6,5 | 12 % movs, 11 % pares; fichero de pago |
| `ar_dd_batch` | 12.505 | 713.554 | **11,2** | 4,2 | 13,6 % de los pares en 12,5 k remesas; fichero |
| `ar_1toN_remittance` | 9.423 | 388.502 | **7,9** | 3,0 | aviso de remesa; lleva `SHORT_DISCOUNT` |
| `ap_fx` | 8.604 | 333.754 | **6,3** | 2,0 | fichero de pago + `FX_DIFFERENCE` |
| `ar_1toN_text` | 46.644 | 259.925 | 5,3 | 3,0 | números en el texto |
| `ar_1toN_credit_note` | 23.466 | 229.078 | 4,4 | 2,1 | facturas menos abono |
| `ar_fx` | 6.146 | 101.731 | 4,0 | 2,4 | `orig_amount` + `FX_DIFFERENCE` |
| `ar_short_withholding` | 10.148 | 35.160 | 2,9 | 2,6 | clase propia (2 pts) |
| `ar_short_discount` | 42.704 | 48.081 | 2,9 | 2,4 | clase propia (2 pts) + 2,9 % movs |
| `ar_dd_returned` | 26.397 | 26.397 | 2,9 | 2,2 | `RETURNED` (2 pts) |
| `ar_card_settlement` | 10.051 | 147.622 | 2,7 | 1,2 | fichero |
| `ap_partial` | 18.131 | 83.124 | 2,5 | 1,0 | fichero + `PARTIAL` |
| `ap_payment_single` | 139.376 | 139.376 | 2,2 | 1,4 | el starter ya acierta el 58 % |
| `ar_overpayment` | 2.817 | 2.817 | **2,1** | **2,1** | **2.817 filas = 2 puntos** |
| `ar_duplicate_payment` | 4.436 | 4.436 | **2,1** | **1,9** | 4.436 filas = 2 puntos (con `ap_duplicate_payment`, 491) |
| `ar_short_bank_charges` | 1.121 | 1.121 | **2,0** | **2,0** | **1.121 filas = 2 puntos** |
| `ar_instalment` | 33.008 | 33.008 | 2,0 | 1,8 | `PARTIAL` + PDF |
| `ap_paid_by_holding` | 33.363 | 82.599 | 2,0 | 1,0 | fichero (ES00 paga por ES01/ES02/PT01) |
| `ap_credit_note_netted` | 18.475 | 90.243 | 1,9 | 0,8 | fichero |
| `ar_same_amount_fifo` | 49.049 | 49.049 | 1,9 | 2,0 | FIFO |
| `ar_partial` | 27.750 | 27.750 | 1,6 | 1,4 | `PARTIAL` |
| `ar_n_to_m` | 13.904 | 50.776 | 1,4 | 0,9 | |
| `ar_same_amount_month` | 33.429 | 33.429 | 1,3 | 1,5 | mes citado en el texto + PDF |
| `ap_direct_debit` | 41.335 | 41.335 | 1,2 | 0,8 | |
| `ap_confirming` | 6.387 | 61.199 | 1,2 | 0,4 | fichero |
| `ar_cheque_deposit` | 15.231 | 42.284 | 1,0 | 0,9 | fichero |
| `ar_discount_late` | 5.837 | 20.350 | 0,8 | 0,5 | `PARTIAL` fuera de plazo |
| `ap_factored` · `ar_retention` · `ap_supplier_refund` · `ap_returned_transfer` · `ap_duplicate_payment` · `ar_dispute_settlement` | 10.934 · 6.643 · 17.795 · 1.192 · 491 · 7.784 | | 0,6 · 0,5 · 0,5 · 0,5 · 0,4 · 0,3 | 0,3 · 0,4 · 0,6 · 0,2 · 0,1 · 0,4 | |
| `nonitem_cash_pool` | 12.576 | 0 | 0,2 | 0,4 | código puro |
| los 38 restantes | | | ≤ 0,2 cada uno | ≤ 0,2 | incluye todos los `nonitem_*`, `unidentified*` (ya acertados), terceros, PDF-only |

**Lo que dice la tabla [Inferencia a partir de lo medido]:**

1. **Seis segmentos con fichero o aviso valen 54 puntos marginales** (`ar_short_dispute`, `ap_payment_multi`, `ar_dd_batch`, `ar_1toN_remittance`, `ap_fx`, `ar_card_settlement`, más `ap_partial`, `ap_paid_by_holding`, `ap_credit_note_netted`, `ap_confirming`, `ar_cheque_deposit`, `ar_dd_returned`). Son deterministas: el fichero lista las partidas y el importe. Es el primer bloque.
2. **`ar_ref_noise` vale 17 puntos él solo** y no tiene fichero: tercero (nombre en el texto en el 93 %) + importe exacto (100 %) + saldo abierto. Es el segundo bloque y el más delicado, porque se parece a `unidentified_lookalike` (10 k cobros con importe de una factura ajena).
3. **La macro-F1 regala 8 puntos por 9.000 filas**: `OVERPAYMENT`, `DUPLICATE_PAYMENT`, `SHORT_BANK_CHARGES` y `SHORT_DISPUTE` (si los avisos se parsean) valen lo mismo que `FX_DIFFERENCE`. Cada clase pide una regla precisa; un falso positivo en una clase pequeña cuesta mucho más que en una grande.
4. **Lo que solo dice el PDF** (`ar_instalment`, `ar_retention`, `ar_advance_deduction`, `ar_replaced_invoice`, `ar_retention_release`, `ar_credit_note_paid_out`, `ar_new_iban`, `ap_factored`): 2,0 + 0,5 + 0,2 + 0,1 + 0,2 + 0 + 0,1 + 0,6 ≈ **3,7 puntos** marginales. Importan menos de lo que sugiere la web; lo que de verdad aportan es `PARTIAL` bien puesto (clase de 2 pts compartida con `ar_partial`, `ap_partial`, `ar_n_to_m`…).
5. **Las categorías sin partida** ya valen poco (el starter acierta `BANK_FEES` y `UNIDENTIFIED` sin querer); con el código del banco se cubre el 95 % del resto por ~1 punto. Lo caro no es la categoría, es **no forzar**: cada cobro `UNIDENTIFIED` casado a la fuerza resta en las tres métricas.

---

## 5. Mapa de oportunidades

Ordenado por puntos esperados / esfuerzo. «Techo» es la columna (a) de §4. «Fuente» es lo que decide, según §3.3. «Esperado» es nuestra estimación de lo que se puede conseguir el día del evento con reglas deterministas bien hechas **[Inferencia]**; «Esfuerzo» en horas-persona de un desarrollador con Claude Code **[Inferencia]**.

| # | Oportunidad | Segmentos | Techo | Fuente que decide | Regla determinista | Dónde hace falta extracción | Dónde no forzar | Esperado | Esfuerzo |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | **Remesas de pago (AP)** | `ap_payment_multi`, `ap_payment_single`, `ap_paid_by_holding`, `ap_partial`, `ap_credit_note_netted`, `ap_confirming`, `ap_fx`, `ap_factored`, `ap_payment_run_aggregated` | **29,6** | `payment_runs/*.csv` (89 % de los movimientos tienen todas sus partidas ahí) | Cargo → remesa por `run_id` en `ref`/texto (`PR010025061090-0001` en N43 `ref2`, `end_to_end_id` en camt) o por (cuenta deudora, fecha, importe); la fila de la remesa da el documento (número impreso del proveedor + `document_type`) → partida por (sociedad, proveedor, número); `run_type` dice si el cargo es uno por beneficiario, por fichero o por vencimiento. Abonos netados: filas con `document_amount` negativo. `ap_fx`: la partida va en la divisa de `document_amount` → `FX_DIFFERENCE` si difiere de la cuenta. `ap_paid_by_holding`: el `debtor_account_id` es de ES00 y la partida de la filial | ninguna | pagos sin remesa (11 %): número en el texto + proveedor + importe; si no, categoría por código | 24–27 | 4–6 h |
| 2 | **Remesas de recibos, tarjetas, cheques y devoluciones (AR agregados)** | `ar_dd_batch`, `ar_card_settlement`, `ar_cheque_deposit`, `ar_dd_returned`, `ar_cheque_returned`, `ar_card_chargeback`, `ar_dd_represented_transfer` | **18,0** | `direct_debit_batches`, `card_settlements`, `cheque_deposits` | Abono → remesa por `batch_id` en el texto (`REMESA SEPA CORE 03230816473`) o (cuenta, fecha, `batch_total`); cada recibo → factura por `remittance_info` (número, a veces `RECIBO 0108480` sin prefijo) o (mandato → cliente, importe). Tarjeta: liquidación por (cuenta, fecha, Σ `net`) → pedidos por `order_number` = número impreso (`TW22-9005950`), importe **bruto**. Cheques: `deposit_id` (`RCH25060201906`) o (cuenta, fecha, `deposit_total`); cheque → factura por `stub_reference` (incompleto) o (`drawer` → cliente, importe). Devolución: `MANDATO VTM-ES-0004847` + importe → el recibo original → `RETURNED` por el importe reabierto; `re_presentation=Y` en una remesa posterior va sin excepción | ninguna | — | 15–17 | 4–6 h |
| 3 | **Avisos de remesa** | `ar_1toN_remittance`, `ar_short_dispute`, `ar_dispute_settlement`, `ar_1to1_remittance`, parte de `ar_third_party_parent` | **21,3** | `remittance_advices/` (85–100 %) | Parsers de los cuatro formatos (csv con cabecera fija; txt-correo con lista `número fecha importe`; xlsx antiguo y nuevo; pdf con tabla `Document Date Gross Deduction Paid`). Aviso → cobro por `payment_ref` en el texto (`AVISO 8826032134`, `PMT ADVICE REM/2021/0798`), o (sociedad, pagador → cliente/grupo, importe total, fecha ± días: **el aviso puede llegar después**). Fila → partida por número (con o sin prefijo/ceros) y cliente; `discount_or_deduction` + `reason` → `SHORT_DISPUTE` (importe = `paid`) o `SHORT_DISCOUNT` (si el motivo es descuento y está en plazo); abonos negativos → fila `ARC` | **aquí sí**: PDFs cuya tabla no se parsea bien y layouts no vistos; un modelo extrae `(número, importe bruto, deducción, motivo)` por fila, con caché | si el aviso no cuadra con ningún cobro, no asignar por el aviso | 15–19 | 6–8 h (es el bloque más largo) |
| 4 | **Cobro con referencia ruidosa / 1:1** | `ar_ref_noise`, `ar_1to1`, `ar_1toN_text`, `ar_1toN_credit_note`, `ar_same_amount_fifo`, `ar_same_amount_month`, `ar_partial`, `ar_n_to_m`, `ar_new_iban`, terceros | **28,6** | texto del banco: números (46 % en `ar_1toN_text`), nombre del tercero (93 %), importe exacto (100 %) | (i) números impresos normalizados en texto/`remittance_info` (con y sin prefijo, con dígitos cortados: índice por sufijo); (ii) tercero: `counterparty_name` → maestro; si no, nombre en el texto (cortado a 38, partido en dos campos, nombre comercial, renombrado: índice de n-gramas sobre `name`, `trade_name` y los nombres históricos de las facturas); IBAN del ordenante (`counterparty_account`, `ORDENANTE ES…`) → `iban` del maestro y cartas de IBAN nuevo; matriz/grupo (`parent_customer_id`, `group_id`); (iii) con el tercero: subconjunto de sus partidas abiertas (facturas y abonos) cuya suma es el importe, una sola solución; empate de importes → FIFO, o el mes del texto (`MANT. MAYO 25`); (iv) un solo candidato en todo el sistema con ese importe exacto y nombre que casa **[Inferencia: hay que medir su precisión en TRAIN antes de activarlo]** | ninguna (los PDF de mes de servicio: pypdf + regex) | **sin tercero ni número, `UNIDENTIFIED`**, aunque el importe cuadre con una factura (10 k `unidentified_lookalike`) | 18–24 | 8–10 h |
| 5 | **Excepciones por importe** (clases de 2 pts) | `ar_short_discount`, `ar_discount_late`, `ar_short_withholding`, `ar_short_bank_charges`, `ar_overpayment`, `ar_duplicate_payment`, `ap_duplicate_payment`, `ar_fx` | **16,0** | condiciones de pago, país del cliente, divisa, saldo abierto | Con el tercero resuelto (bloque 4) y sus partidas abiertas: cobro = total − % descuento × total y fecha ≤ emisión + días + 3 → `SHORT_DISCOUNT` (si fuera de plazo, `PARTIAL`); cobro = total × (1 − 1,25/1,5/10 %) y cliente MX/BR/MA → `SHORT_WITHHOLDING`; cobro < total, diferencia ≤ 60 EUR y ≤ 2 %, origen fuera de SEPA (`TRANSFER. EN DIV.`, BIC extranjero) → `SHORT_BANK_CHARGES`; cobro > total de una sola factura → `OVERPAYMENT`; partida ya liquidada y vuelve a pagarse → `DUPLICATE_PAYMENT`; `orig_currency` ≠ divisa de la partida → importe = `orig_amount` y `FX_DIFFERENCE` (sustituye a vacío/`SHORT_*` salvo `PARTIAL`/`SHORT_DISPUTE`; abonos vacíos) | ninguna | si cuadran dos explicaciones, la que `POLICIES` prioriza; si ninguna, `PARTIAL` o `UNIDENTIFIED` | 10–14 | 4–6 h (depende del 4) |
| 6 | **Estado: plazos, retenciones, anticipos, anulaciones** | `ar_instalment`, `ar_retention`, `ar_retention_release`, `ar_advance_deduction`, `ar_replaced_invoice`, `ar_credit_note_paid_out`, `customer_advance` | **3,7** | PDF de la factura (100 %) + saldo abierto | pypdf sobre los PDFs de `index.csv` con regex para «vencimientos», «retención … %», «a deducir anticipo … de X», «anula y sustituye a Y», «servicios de <mes>», «se compensará / se abonará por transferencia», «cedido a <factor>», «nueva cuenta IBAN»; el saldo abierto decide `PARTIAL` (queda saldo) o vacío (último plazo, liberación); un pago que cita la anulada va a la sustituta | **modelo solo para PDFs que el regex no cubra**; medir en LIVE cuántos son | — | 2–3 | 3–4 h |
| 7 | **Categorías sin partida** | `nonitem_*`, `customer_refund`, `customer_advance`, `ap_supplier_refund`, `ap_duplicate_refund` | ~1,5 | código + texto (95,5 % de pureza por código) | tabla (banco, código, subcódigo) → categoría aprendida de TRAIN, con palabras clave para los códigos genéricos (`NOMINAS`, `CASH POOLING`, `IMPUESTOS MOD`, `ANULACION OPERACION INDEBIDA`, `PROFORMA`); `ap_supplier_refund` liquida el `APC` del proveedor (importe exacto) | ninguna | cobro sin nada → `UNIDENTIFIED` | 1–1,5 | 2 h |
| 8 | **Producto** (interfaz) | — | 0 en el CSV; el jurado «valora el enfoque» | `explanations.jsonl.gz` | vista de revisión: cola de `UNIDENTIFIED` y `FALLBACK-*` por sociedad e importe, cada fila con su regla y su evidencia; KPIs de autonomía y caja identificada | — | — | — | 4–8 h en paralelo |

Suma de lo esperado con todo hecho: **[Inferencia]** 85–95 en TRAIN; la web sitúa una «heurística con reglas bien trabajadas» en ≈ 61 en LIVE. El orden de ataque que maximiza puntos por hora: 1 → 2 → 3 (parsers csv/txt primero, pdf/xlsx después) → 4 → 5 → 7 → 6, con 8 en paralelo desde media mañana.

**Dónde hace falta un modelo y dónde no [Inferencia a partir de §3.3]:** los ficheros de detalle y los avisos csv/txt/xlsx son tablas regulares: parsers. Los avisos pdf tienen una tabla con cabecera fija (`Document Date Gross Deduction Paid`) y el texto sale bien con pypdf: parser con regex, modelo para el residuo. Las cláusulas de los PDFs de factura son frases fijas de un generador sintético («Forma de pago: 3 vencimientos…», «Retención en garantía del 10 % (2.875,57 EUR)…», «anula y sustituye a la factura X»): regex, modelo para el residuo. **El modelo nunca elige la partida**: convierte un documento en `(números, importes, deducciones, motivos, cláusulas)` y la regla decide. Presupuesto: en LIVE hay 6.889 avisos y 16.688 PDFs; si el residuo es el 5 %, son ~1.200 llamadas cortas a Haiku por fase (centavos, minutos en paralelo) **[Inferencia]**. En FINAL los documentos son nuevos: la caché no sirve, el paralelismo sí.

---

## 6. Diseños de pipeline candidatos

Los tres comparten la cadena `load → index → documents → rules → resolve → output → score` de `ARCHITECTURE.md` §7 y el principio «las reglas deciden; los modelos solo extraen». Se diferencian en **cómo se resuelve** (orden y estado) y en **cuánto modelo** entra. Requisito duro: FINAL se publica a las 18:00 y los envíos cierran a las 19:30; el sistema tiene que leer ~220 k movimientos, ~1 M de partidas, ~7 k avisos y ~17 k PDFs nuevos, escribir, validar y subir un solo fichero en **menos de 30 minutos de reloj**, dejando margen para un reintento **[Inferencia: 90 min menos tiempo de descarga, revisión humana y colchón]**.

### Diseño A — Pasadas por certeza, estado al final (recomendado)

```
load (Polars, céntimos) → index (partidas por sociedad+tercero, número normalizado, sufijo de dígitos, importe; terceros por n-gramas; ficheros por id)
→ documents (parsers de avisos y PDFs; modelo para el residuo, con caché)
→ rules en orden de certeza, cada una consume movimientos y partidas:
   R1 ficheros (remesas de pago, recibos, tarjetas, cheques)   R2 avisos de remesa   R3 números en texto
   R4 tercero + subconjunto de abiertos (FIFO / mes)            R5 devoluciones y duplicados (contra la historia)
   R6 categorías por código y texto                             R7 respaldo (UNIDENTIFIED / categoría)
→ resolve: el saldo abierto se reconstruye en orden de fecha a partir de las asignaciones de todas las reglas; policy.py
   pone importe y excepción (descuento, retención, comisión, FX, parcial, sobrepago, duplicado, devolución)
→ output (CSV, explanations, run.json) → score (local, con el límite de tamaño relajado)
```

- **Precisión:** alta en R1–R3 (fuentes explícitas); R4 depende de la resolución del tercero y de un subconjunto único. Un movimiento solo baja a R4 si R1–R3 no lo tocan.
- **Cobertura:** el 90 % de los pares tiene fuente explícita (§3.3); el resto es R4.
- **Coste de modelo:** cero en v1; residuo de documentos en v2.
- **Tiempo:** todo vectorizado en Polars salvo el subconjunto de R4 (por tercero, tamaños pequeños). Estimación: TRAIN en 3–6 min, LIVE/FINAL en < 1 min más documentos (pypdf en paralelo, ~2 min) **[Inferencia; el starter en Python puro tarda 54 s en TRAIN y 29 s en LIVE]**.
- **Riesgo:** el estado se calcula después de asignar, así que una regla temprana puede asignar una partida que una devolución o un duplicado posterior necesita; se mitiga con R5 sobre la historia y con el saldo como comprobación en `policy.py`. Es el diseño que mejor reparte el trabajo entre personas (una regla por persona, mismas interfaces).

### Diseño B — Simulación en orden de fecha, estado en vivo

```
load → index → documents → por cada movimiento en orden de booking_date:
   consultar el estado (saldo abierto por partida, historia de pagos) → evaluar las reglas R1…R7 → aplicar la mejor → actualizar el estado
→ output → score
```

- **Precisión:** la semántica de `PARTIAL` (queda saldo), último plazo (vacío), `DUPLICATE_PAYMENT` (ya liquidada), `RETURNED` (reabre) y FIFO sale **exacta por construcción**, porque cada decisión ve el estado real en esa fecha.
- **Cobertura:** la misma.
- **Coste de modelo:** igual que A.
- **Tiempo:** un bucle en Python por movimiento con índices en diccionarios: 220 k movimientos son segundos–minutos; TRAIN (1,49 M) varios minutos. Es más lento que A y más difícil de paralelizar entre personas: todas las reglas tocan la misma estructura de estado.
- **Riesgo:** un error en el estado se arrastra; depurar una regla exige reproducir la secuencia. Peor para iterar en TRAIN muchas veces en un día.

### Diseño C — Candidatos por reglas + modelo que decide

Las reglas generan candidatos por movimiento y un modelo (Claude con los candidatos y el texto) elige. **No lo recomendamos**: contradice el principio del repo, 200 k llamadas por fase no caben en 90 minutos ni en el presupuesto, la precisión en `unidentified_lookalike` sería peor que la de una regla que se abstiene, y el jurado no vería una regla por fila. Lo incluimos como contraste y porque una versión acotada (el modelo solo decide en los movimientos ambiguos de R4, < 2 %) es una extensión posible de A si sobra tiempo, siempre con caché y con la decisión registrada como `rule: "LLM-ARBITER"`.

| | A · pasadas por certeza | B · simulación por fecha | C · candidatos + modelo |
| --- | --- | --- | --- |
| Precisión | alta en fuentes explícitas; R4 según el tercero | la mejor para excepciones de estado | incierta; riesgo de forzar |
| Cobertura | 90 % con fuente explícita + R4 | igual | igual |
| Coste de modelo | 0 (v1) · residuo de documentos (v2) | igual | alto (una llamada por movimiento ambiguo) |
| Tiempo FINAL | < 5 min + documentos | 5–15 min | horas |
| Reparto entre personas | una regla por persona | difícil | — |
| Explicabilidad | regla + fuente por fila | igual | el modelo |

**Recomendación:** A, con el cálculo de estado de B como paso `resolve` (recorre las asignaciones por fecha para fijar `PARTIAL`/último plazo/duplicado/devolución). Es lo que `ARCHITECTURE.md` §7.3 ya describe, con una precisión: las reglas no consultan el estado al proponer (salvo R4 y R5, que necesitan el saldo abierto del tercero), y `policy.py` lo usa al cerrar.

---

## 7. Plan del día (sábado 7, 10:00–19:30)

Supuestos: equipo de 4–6 personas, cada una con Claude Code, repo compartido en ramas `KPI-*` por bloque, diseño A. Los hitos se miden con la puntuación local en `sample/` (segundos) y en TRAIN con el límite relajado (minutos), y con **pocos envíos a LIVE** (cada hito, no cada cambio; 20 al día). Las cifras de puntuación son objetivos **[Inferencia]**.

| Hora | Hito | Comprobación |
| --- | --- | --- |
| 10:00 | Esqueleto: `load`, `index`, `output`, `score` con el límite relajado, `FALLBACK-*` para todo; **primer envío a LIVE** con el fichero de respaldo (todos los movimientos, nada forzado) | TRAIN ≈ 12; LIVE validado y puntuado (sabemos que el formato pasa) |
| 11:30 | Bloques 1 y 2 (ficheros de detalle) integrados; categorías por código | TRAIN ≈ 45–55; envío a LIVE |
| 13:00 | Bloque 3 (avisos csv/txt/xlsx) y bloque 4 básico (número en texto, tercero + importe único) | TRAIN ≈ 65–75; envío a LIVE |
| 14:00 | Comida (con el cronómetro de un «ensayo FINAL» corriendo sobre LIVE: un comando, tiempo y tamaño del fichero) | tiempo total < 10 min |
| 15:30 | Bloque 5 (excepciones por importe), bloque 3 pdf, estado en `resolve` (`PARTIAL`/duplicado/devolución) | TRAIN ≈ 80–85; envío a LIVE; macro-F1 > 0,7 |
| 17:00 | Bloque 6 (PDFs), ajustes por segmento con la tabla de exactitud; **congelación de reglas**; segundo ensayo cronometrado sobre LIVE; vídeo y descripción grabándose | TRAIN ≈ 85–90; último envío a LIVE |
| 18:00 | FINAL: descarga, `sha256`, descomprimir en `db/final/`, **leer `masters_final/` y el README de FINAL** (ZA01, renombrado, IT01), ejecutar un solo comando | run.json con tiempo y conteos; todos los `bank_txn_id` cubiertos; tamaño < 60 MB |
| 18:30 | Revisión humana de 15 min: distribución por regla y por sociedad comparada con LIVE (ZA01 no puede ser todo `UNIDENTIFIED`); validar el fichero con `bankrec_score.py` (solo validación: sin golden) | sin errores de validación |
| 18:45–19:00 | **Un envío FINAL** por una persona del equipo | estado `received`/`scored` |
| 19:00–19:45 | Entrega del proyecto: vídeo, repo público, descripción | hecho antes de las 19:45 |

**Reparto en paralelo** (cada persona un bloque de §5, todos contra el mismo `index`/`state`/`policy`/`output` que fija la persona 1 en la primera hora):

| Persona | Mañana | Tarde |
| --- | --- | --- |
| 1 (núcleo) | esqueleto, índices, `policy.py`, `resolve`, scorer local, ensayo FINAL | integración, congelación, ejecución de FINAL y envío |
| 2 | bloque 1 (remesas de pago, AP) | bloque 5 AP (`ap_fx`, duplicados, devoluciones de transferencia) |
| 3 | bloque 2 (recibos, tarjetas, cheques, devoluciones) | bloque 7 (categorías) y `UNIDENTIFIED` |
| 4 | bloque 3 (avisos: csv/txt primero, xlsx nuevo, pdf) | bloque 3 residuo con modelo; `SHORT_DISPUTE`/`SHORT_DISCOUNT` desde el aviso |
| 5 | bloque 4 (tercero, números, subconjunto, FIFO/mes) | bloque 5 AR (descuento, retención, comisión, sobrepago, FX) |
| 6 (si hay) | bloque 6 (PDFs: regex sobre pypdf) | producto: interfaz de revisión sobre `explanations`, vídeo |

**Riesgos principales y qué hacer:**

1. **Forzar casaciones** (precisión): toda regla nueva se mide en TRAIN por segmento **y** se mira `unidentified_lookalike`; si baja, la regla no entra. Umbral de abstención explícito en R4.
2. **El fichero FINAL falla la validación o pesa más de 60 MB**: validar en local con el evaluador (sin golden) y medir el tamaño; nada de comillas, `amount` con dos decimales, sin filas duplicadas.
3. **ZA01 y `masters_final/`**: el código carga maestros de la fase si existen; nada de listas fijas de sociedades, cuentas o divisas; ZA01 pagos de proforma → `CUSTOMER_ADVANCE`. Probar antes de las 18:00 con un maestro de mentira que añada una sociedad.
4. **Tiempo de ejecución**: ensayo cronometrado sobre LIVE a las 14:00 y a las 17:00; si los PDFs no caben, se ejecutan solo los que citan movimientos sin resolver.
5. **Sobreajuste a LIVE**: pocos envíos; las decisiones se toman en TRAIN por segmento.
6. **Estado inicial**: en LIVE/FINAL, `open_items_at_start` manda sobre lo que calculemos; en TRAIN, las partidas anteriores a 2021-07 sin asignación no se tratan como abiertas salvo que algo las cite.
7. **Personas y ramas**: conflictos en `policy.py`/`resolve`: una sola persona los toca; las reglas viven en ficheros separados.
8. **Token y envíos**: el token en una variable de entorno; nadie pide una URL de subida «para probar».

---

## 8. Preguntas para la organización

1. **Puntuación local de TRAIN:** el evaluador rechaza ficheros > 60 MB y el golden de TRAIN pesa 325 MB. ¿Es intencionado que `score_train.py` solo valga para ficheros pequeños? ¿Hay una versión por trozos o se puede relajar el límite en local sin cambiar la métrica?
2. **Partidas anteriores a 2021-07:** 212 k partidas emitidas entre marzo y junio de 2021 ni se liquidan en el golden ni aparecen en `open_items_at_start` de LIVE. ¿Se pagaron antes de TRAIN? ¿Hay forma de saber el saldo inicial de TRAIN?
3. **Cuentas fuera del maestro:** `IT01-VALD-EUR-2` tiene movimientos en TRAIN y LIVE y no está en `bank_accounts.csv`. ¿Es un error del maestro o parte del reto?
4. **ZA01 en LIVE:** los dos movimientos de `ZA01-UMVC-ZAR` de diciembre de 2025 (pagos de proforma). ¿Qué etiqueta llevan en el golden de LIVE? ¿`CUSTOMER_ADVANCE`?
5. **`final/masters_final/`:** ¿sustituye a `masters/` por completo o solo añade ZA01 y los renombrados?
6. **Jurado:** ¿cómo pesa la entrega del proyecto (vídeo, repo, descripción) frente a la puntuación de FINAL en los premios? ¿Hay premios distintos (clasificación y jurado)?
7. **Envíos:** ¿el límite de 20 al día es por fase y se reinicia a medianoche? ¿Un fichero rechazado por la validación en LIVE gasta uno de los 20?
8. **FINAL:** ¿se puede subir un fichero FINAL antes de las 18:00 (p. ej. uno de LIVE por error) y queda consumido? ¿La validación de FINAL devuelve los errores con número de fila como en LIVE?
9. **Golden de LIVE:** ¿se publicará después del evento para aprender?
10. **Modelos:** ¿dan crédito de API de Anthropic o cada equipo usa el suyo?

---

## 9. Decisiones que necesito de ti

1. **Diseño:** ¿A (pasadas por certeza + estado en `resolve`)? Es mi recomendación; B es más exacto en estado y peor para repartir; C queda fuera.
2. **Modelo:** ¿v1 sin modelo (solo parsers) y v2 con Claude Haiku para el residuo de avisos y PDFs, con caché? ¿Qué presupuesto de API y qué clave? La caché: ¿en `runs/cache/` (fuera de git) o en una carpeta versionada por fase?
3. **Puntuación local de TRAIN:** ¿relajamos el límite de 60 MB en una copia local del evaluador (idéntica salvo esa constante, como hace `05_baseline.py`) o puntuamos por años? Afecta al `just be-score`.
4. **Equipo:** ¿cuántas personas y quién hace qué? El reparto de §7 supone 5–6; con 3, los bloques 1+2 van juntos, 3+6 juntos y 4+5 juntos, y el producto se reduce al vídeo.
5. **Producto:** ¿cuánto tiempo le damos a la interfaz? El frontend actual está congelado y modela el problema antiguo. Opciones: (a) solo vídeo con el CSV, las explicaciones y la puntuación por segmento; (b) una vista de revisión mínima sobre `explanations.jsonl.gz` (cola de `UNIDENTIFIED`, regla y evidencia por fila, KPIs por sociedad) reutilizando el shell y los componentes de `app/`; (c) nada. Mi propuesta: (b) a partir de las 15:00 si hay una sexta persona; si no, (a).
6. **Git durante el día:** una rama `KPI-<n>_<bloque>` por persona con PR a `main` cada hito, o `main` abierto con commits pequeños. Propongo lo primero con PRs de revisión rápida (minutos), y que `main` siempre ejecute de principio a fin.
7. **Docs:** ¿corrijo `PROBLEM.md`, `ARCHITECTURE.md`, `CONTRACT.md` y `CLAUDE.md` con la tabla de §2 en esta misma rama o en una PR aparte después de que revises el análisis?
8. **Ensayo FINAL:** ¿quién hace el envío y desde qué portátil? Esa máquina debe tener el repo, `db/`, el entorno y el token antes de las 17:00.
9. **Scripts de análisis:** ¿los dejamos en `scripts/analysis/` (propuesto) o los movemos a `backend/tools/` cuando exista el backend?

---

## 10. Anexos

### 10.1 Qué reutilizar del repo de Kalmora (`alfonsomayoral/talky-labs-hackathon`)

El repo ganador del primer hackathon de Talky resolvía otro problema (cierre contable con AP, facturación, bancos, cobros, intragrupo y asientos; 300 documentos y 300 líneas de banco al mes), pero su **forma de trabajar** es la que queremos aquí **[Fuente: su README y árbol de ficheros]**:

| De Kalmora | Aquí |
| --- | --- |
| «Las decisiones contables son deterministas; los modelos leen, no deciden»; ADR 0002 (frontera documento–LLM) | mismo principio (`ARCHITECTURE.md` §1) |
| Grabación y reproducción de cada extracción con modelo, con huella del documento | caché de `documents/` por hash; decidir dónde vive (§9.2) |
| Traza por partida con eventos y evidencia (`EXTRACT`, `MATCH`, `DECIDE`…) | `explanations.jsonl.gz` con `rule` y `sources` (CONTRACT.md); añadir `partyId` |
| El evaluador oficial envuelto sin modificarlo (ADR 0001, sha256) | aquí hay que relajar una constante para TRAIN: documentarlo y comprobar el sha256 del resto |
| Router de documentos: XML → pypdf → OCR → LLM residual, tipado con PydanticAI | avisos csv/txt/xlsx → parser; pdf → pypdf + regex → modelo residual; sin OCR (los PDFs son generados, con texto) |
| Front: resumen con autonomía, bandeja de atención con prioridad e importe, actividad, entregables | la vista de revisión de §9.5 (b): cola de `UNIDENTIFIED`/`FALLBACK`, KPIs por sociedad, regla y evidencia por fila |
| 32 herramientas MCP de solo lectura y asistente que solo copia cifras | fuera de alcance el día del evento; buena «siguiente etapa» para la descripción del proyecto |
| Evals por módulo (`evals/`, `docs/evaluation/`) | puntuación por segmento con el evaluador oficial, antes y después de cada regla |

Lo que **no** encaja: la escala (allí 300 líneas de banco; aquí 220 k por fase y 1,5 M en TRAIN): nada de bucles movimiento × partida ni de un modelo por documento; la cadena de seis módulos (aquí hay uno); FastAPI y MCP (no hacen falta para puntuar).

### 10.2 El valor de negocio que enseñar (para el vídeo y la descripción) [Inferencia]

La web lo dice: «lo que no se concilia no se cobra a tiempo» y «una buena solución dice por qué casa algo y marca lo que no sabe». Cifras que el producto puede enseñar con nuestros propios datos: movimientos conciliados sin intervención (%), importe identificado (ponderado en EUR: el evaluador lo calcula como `amount_weighted_accuracy`), cola de revisión (cuántos `UNIDENTIFIED` y `FALLBACK`, por sociedad, ordenados por importe), excepciones detectadas por tipo (disputas, retenciones, duplicados: lo que tesorería tiene que reclamar), devoluciones y duplicados (riesgo de caja) y, para cada fila, la regla y el documento que la respaldan (auditoría). En TRAIN el golden permite enseñar además la puntuación por segmento como «dónde el sistema sabe que no sabe».

### 10.3 Segmentos por familia (los 36 ejemplos de la web cubren uno por familia)

| Familia | Segmentos |
| --- | --- |
| Cobros 1:1 y referencias ruidosas | `ar_1to1`, `ar_ref_noise`, `ar_same_amount_fifo`, `ar_same_amount_month`, `ar_1to1_remittance` |
| 1:N | `ar_1toN_remittance`, `ar_1toN_credit_note`, `ar_1toN_text` |
| N:1 | `ar_instalment`, `ar_partial`, `ar_n_to_m` |
| Pagos de menos | `ar_short_discount`, `ar_discount_late`, `ar_short_bank_charges`, `ar_short_withholding`, `ar_short_dispute`, `ar_dispute_settlement` |
| Sobrepagos y duplicados | `ar_overpayment`, `ar_duplicate_payment`, `ap_duplicate_payment`, `ap_duplicate_refund` |
| Divisas | `ar_fx`, `ap_fx` |
| Paga un tercero | `ar_third_party_parent`, `ar_third_party_agency`, `ar_third_party_confirming`, `ap_paid_by_holding`, `ap_factored` |
| Devoluciones | `ar_dd_returned`, `ar_dd_represented_transfer`, `ar_cheque_returned`, `ar_card_chargeback`, `ap_returned_transfer` |
| Agregados | `ar_dd_batch`, `ar_card_settlement`, `ar_cheque_deposit`, `ap_confirming`, `ap_payment_multi`, `ap_payment_single`, `ap_payment_run_aggregated`, `ap_direct_debit`, `ap_partial`, `ap_credit_note_netted` |
| Solo en el documento | `ar_retention`, `ar_retention_release`, `ar_advance_deduction`, `ar_replaced_invoice`, `ar_new_iban`, `ar_credit_note_paid_out` |
| Sin partida | `nonitem_bank_fees`, `nonitem_bank_fees_intl`, `nonitem_cash_pool`, `nonitem_payroll`, `nonitem_intercompany`, `nonitem_leasing`, `nonitem_bank_reversal`, `nonitem_internal_transfer`, `nonitem_fx_deal`, `nonitem_tax_payment`, `nonitem_loan_repayment`, `nonitem_social_security`, `nonitem_card_expenses`, `nonitem_interest_income`, `nonitem_insurance`, `nonitem_interest_expense`, `nonitem_loan_drawdown`, `nonitem_tax_refund`, `customer_refund`, `customer_advance`, `ap_supplier_refund` |
| No identificados | `unidentified`, `unidentified_lookalike` |

### 10.4 Ficheros generados (fuera de git)

`runs/baseline/starter_{train,live,sample}.csv.gz` y sus logs; `runs/analysis/01_volumes.md`, `02_golden.md`, `03_sources_train.md`, `04_drift.md`, `05_ceilings.md` (tablas completas) y los `.json` con los mismos datos; `runs/analysis/parquet/` (caché de las tablas); `runs/analysis/verify_*.csv.gz` (los tres ficheros con un segmento sustituido por el golden).
