# PROBLEM.md

El problema que resolvemos en **Close the Books**, el reto del Claude Code Hackathon. Es la fuente de verdad del equipo y de los agentes: léelo antes de construir nada.

> **Alcance.** Describe el problema: qué entra, qué sale, cómo se puntúa y qué no sabemos. No describe nuestra solución; eso está en [ARCHITECTURE.md](ARCHITECTURE.md).
>
> **Fuentes** (leídas el 6 nov 2026):
> - La web del reto: [inicio](https://hackathon.usetalky.com/), [ejemplos](https://hackathon.usetalky.com/ejemplos), [reglas](https://hackathon.usetalky.com/reglas), [datos](https://hackathon.usetalky.com/datos), [proyecto](https://hackathon.usetalky.com/proyecto), [enviar](https://hackathon.usetalky.com/enviar) y [FAQ](https://hackathon.usetalky.com/faq).
> - El paquete oficial `bankrec-docs-and-masters.zip`, en local en `db/bankrec-docs-and-masters/`: `README.md`, `POLICIES.md`, `DATA_DICTIONARY.md`, `FORMAT.md`, `masters/`, `sample/` y `starter/` (con `bankrec_score.py`, el mismo evaluador del servidor).
> - Los datos de TRAIN (completo) y LIVE, en local en `db/train/` y `db/live/`. Las cifras de la §9 las hemos medido nosotros sobre ellos.
>
> **Jerarquía.** Si este documento contradice al paquete, manda el paquete; y dentro del paquete, **`POLICIES.md` manda sobre el etiquetado** («las etiquetas las siguen al pie de la letra»). Lo marcado **[Inferencia]** no lo dice ninguna fuente: es una lectura nuestra.
>
> **Cambio respecto a la v0.** La v0 suponía un cierre contable con libro mayor, historial del ERP, pedidos, contratos y detección de fraude. **El reto real es otro: conciliación bancaria a escala.** No hay libro mayor, ni asientos, ni historial del ERP, ni pedidos ni contratos. `POLICIES.md` §7: «No journal entries are needed».

## 1. En una frase

Para cada movimiento bancario de un grupo de 17 sociedades, decir qué partidas abiertas (facturas y abonos, de clientes y de proveedores) liquida y por qué importe, o, si no liquida ninguna, qué es (comisión, nómina, cash pooling…), marcando por qué el dinero no cuadra con los documentos. Se entrega como un CSV y se puntúa automáticamente contra un golden oculto.

## 2. El evento

| | |
| --- | --- |
| Nombre | Claude Code Hackathon — Close the Books. Titular de la web: «¿Puedes conciliar más de 55.000 M€ en un día?» |
| Fecha y lugar | Sábado 7 nov 2026, 09:00–21:00, La Nave (Madrid). ~70 personas |
| Organiza | Talky con UCppM, con el apoyo de Anthropic |
| Equipos | De 1 a 8 personas. «Una persona, un equipo». Cada equipo tiene un token para enviar |
| Herramientas | «Cualquier lenguaje, librería, modelo o herramienta» (LLMs incluidos). «Lo que cuenta es el CSV que envías» |
| Cómputo | El nuestro (portátil o nube). Solo se limitan los envíos (§7.4) |

### 2.1 Agenda

| Hora | Hito |
| --- | --- |
| 09:00 | Acreditación |
| 09:30 | Presentación del reto |
| **10:00** | **Arranca el hackathon y abre la fase LIVE** |
| 14:00 | Comida |
| **18:00** | **Se publican los datos FINAL** |
| **19:30** | **Cierre de envíos** |
| **19:45** | **Entrega del proyecto** (vídeo, repositorio y descripción) · presentaciones |
| 20:30 | Revelación de la clasificación final y premios |

Entre los datos FINAL y el cierre de envíos hay **90 minutos**. Ese es el tiempo para ejecutar el sistema sobre datos que no hemos visto y enviar un único fichero.

### 2.2 Entrega del proyecto (antes de las 19:45)

«Además del CSV, el jurado valora vuestro enfoque.» Se entrega en [/proyecto](https://hackathon.usetalky.com/proyecto) con el token del equipo:

1. **Vídeo:** «qué es lo CLAVE de vuestra solución, el enfoque y los resultados». Recomendado ≤ 5 min, 720p.
2. **Repositorio** de GitHub, visible para el jurado (público al entregar o con acceso compartido).
3. **Descripción:** ideas clave, stack y modelos usados, qué haríais a continuación y miembros del equipo.

## 3. El reto

**Grupo Valtermia** es un grupo industrial ficticio, del tamaño de una empresa del IBEX 35, que diseña, fabrica y distribuye equipos, recambios, química y servicios para instalaciones de agua (piscina, wellness, riego). Factura unos 3.600 M€ a distribuidores, cadenas e instaladores de unos 47 países. Todo es sintético salvo los tipos de cambio, que son los de referencia reales del BCE.

| Dimensión | Valor |
| --- | --- |
| Sociedades | 17 en TRAIN y LIVE (`masters/entities.csv`); 18 en FINAL, con la nueva ZA01 (Sudáfrica, ZAR) |
| Divisas | 11 en los extractos de TRAIN (EUR, USD, AUD, CNY, BRL, MXN, GBP, PLN, CHF, MAD, CAD); ZAR aparece en LIVE |
| Bancos y cuentas | 13 bancos; 47 cuentas en `masters/bank_accounts.csv`, 48 con movimientos en TRAIN y 49 en LIVE |
| Formatos de extracto | Norma 43 (`.n43`), SWIFT MT940 (`.sta`) y ISO 20022 camt.053 (`.xml`) |
| Movimientos | ~1,91 M en total (TRAIN 1,49 M · LIVE 203 k · FINAL 220 k) |

**El trabajo, por movimiento bancario:**

- Si liquida partidas: una fila por partida con su `item_id` y el importe liquidado **en la divisa de la partida**.
- Si no liquida ninguna: una sola fila con una `category` de la lista cerrada.
- En cada fila, una `exception` de la lista cerrada que explica por qué el dinero no cuadra con los documentos, o vacía si cuadra.

Las **partidas** son cuatro tipos de documento: facturas emitidas (`ARI-`), abonos emitidos (`ARC-`), facturas de proveedor (`API-`) y abonos de proveedor (`APC-`). Proformas, avisos de remesa, ficheros de pago y cartas **no** son partidas.

## 4. Fases

| Fase | Periodo | Movimientos | Qué se recibe | Envíos |
| --- | --- | --- | --- | --- |
| **TRAIN** | 2021-07-01 → 2025-06-30 | 1,49 M | Entradas **y golden** (`golden_allocations.csv.gz`) | No se envía: se puntúa en local con `starter/score_train.py` |
| **LIVE** | 2025-07-01 → 2025-12-31 | 203 k | Entradas y partidas abiertas al inicio. Sin golden | Clasificación pública; cuenta la mejor puntuación |
| **FINAL** | 2026-01-01 → 2026-06-30 | 220 k | Entradas, partidas abiertas al inicio y `final/masters_final/`. Se publica a las 18:00 | **Un único envío puntuado**, oculto hasta las 20:30. **Decide el ganador** |

Cada movimiento pertenece a una sola fase, por fecha de operación. Las descargas son `train-lite` (460 MB: todas las tablas con golden, extractos en bruto y PDFs solo desde 2024-07), `train` (657 MB), `live` (87 MB) y `final` (a las 18:00). Tenemos en local `train` completo y `live`.

### 4.1 Drift entre fases

Está puesto a propósito (`POLICIES.md` §6):

- **Banco del Moncayo** pasa de Norma 43 a camt.053 el **2025-10-01**: los textos cambian de forma a mitad de LIVE.
- **Un gran cliente** cambia el formato de sus avisos de remesa en **septiembre de 2025**.
- **Nueva filial ZA01** (Sudáfrica, ZAR, banco nuevo, numeración propia «KWI…») desde el **2026-01-01**, renombrada el **2026-04-01**. Sus maestros llegan en `final/masters_final/`.
- **IT01** cambia su cuenta de cobros el **2026-02-01**, y algunos clientes siguen pagando a la antigua durante meses: las dos son válidas.
- Clientes que se renombran, cambian de banco o pagan más tarde («payment behaviour gets slower in 2026»).

**[Inferencia]** Lo que funcione solo porque TRAIN se parece a LIVE puede fallar en FINAL. El sistema tiene que aguantar una sociedad, una divisa y una numeración que no ha visto nunca.

## 5. Entradas

Todas las fases tienen la misma estructura (`DATA_DICTIONARY.md`). Fechas ISO; importes con punto, dos decimales, en la divisa de la fila; tablas grandes en `.csv.gz` (UTF-8, coma, cabecera).

### 5.1 Movimientos bancarios

| Fichero | Contenido |
| --- | --- |
| `bank_statements/<cuenta>/<cuenta>_<YYYYMM>.<n43\|sta\|xml>` | Extractos en bruto, tal y como los manda el banco. Los de Banca Ribagorza se **solapan** (repiten los últimos días del mes anterior) |
| `bank_transactions.csv.gz` | **Vista normalizada** de las mismas líneas, sin duplicados. Es la fuente de `bank_txn_id` |

Columnas de `bank_transactions`: `bank_txn_id` (`BT-<año>-<7 dígitos>`, único y estable), `account_id`, `entity`, `bank`, `statement_format`, `statement_file`, `booking_date`, `value_date`, `amount` (con signo: + cobro, − pago, en la divisa de la cuenta), `currency`, `bank_code`, `bank_subcode` (los bancos los usan de forma inconsistente), `ref1`, `ref2`, `text` (texto libre del banco: en N43, campos de 38 caracteres unidos con ` | ` y palabras cortadas en el límite), `counterparty_name`, `counterparty_account`, `end_to_end_id` y `remittance_info` (estos cuatro, solo en camt), y `orig_amount` y `orig_currency` (importe instruido si la operación va en otra divisa).

### 5.2 Partidas

| Fichero | Contenido |
| --- | --- |
| `ar_invoices.csv.gz` | Facturas emitidas: `item_id`, `entity`, `document_number` (el número impreso, el que cita el cliente), fechas, cliente, divisa, base, impuesto, total, `payment_terms`, `customer_po` y `payment_method` (`transfer`, `dd`, `card`, `cheque`) |
| `ap_invoices.csv.gz` | Facturas de proveedor: el número impreso es `supplier_invoice_number`; además `our_po` y `payment_method` |
| `credit_notes.csv.gz` | Abonos AR y AP, con importe positivo, `related_document` (la factura que rectifican) y `reason` |
| `open_items_at_start.csv.gz` | Solo LIVE y FINAL: partidas abiertas al cierre de la fase anterior y su `open_amount`. En LIVE son 325 k |

El `item_id` no significa nada: **el banco nunca lo trae**. El cliente cita el número impreso, y a menudo mal.

### 5.3 Documentos de detalle

Son los que deciden los casos agregados y los que solo se resuelven leyendo:

| Ruta | Qué resuelve |
| --- | --- |
| `remittance_advices/<entidad>/RA_*.{pdf,csv,xlsx,txt}` + `index.csv` | Avisos de pago de grandes clientes: qué documentos paga un cobro, deducciones y motivos. Puede llegar días **después** del cobro |
| `direct_debit_batches/<entidad>_<sucursal>_<YYYYMM>.csv` | Remesas SEPA/BACS/ACH: un abono del banco agrupa todos sus recibos. `re_presentation=Y` marca un recibo devuelto y presentado otra vez |
| `card_settlements/<entidad>_<YYYYMM>.csv` | Liquidaciones del adquirente: un abono neto que liquida varios pedidos por su **bruto** |
| `cheque_deposits/<entidad>_<sucursal>_<YYYYMM>.csv` | Ingresos de cheques y lockbox (EE. UU., Francia, Marruecos) |
| `payment_runs/<entidad>_<YYYYMM>_<n>.csv` | Nuestros pagos a proveedores: `transfers` (un cargo por beneficiario), `aggregated` (un cargo por fichero) o `confirming` (un cargo por vencimiento) |
| `pdfs/<entidad>/*.pdf` + `index.csv` | PDFs de un **subconjunto** de documentos. Sus cláusulas no están en ningún CSV: plazos, retención en garantía, anticipo a deducir, «anula y sustituye», mes del servicio, rappel compensado o pagado, factura cedida a un factor, IBAN nuevo |

### 5.4 Maestros (`masters/`, foto a 2025-12-31)

| Fichero | Para qué |
| --- | --- |
| `entities.csv` | 17 sociedades con país, moneda funcional y papel. ES00 es la cabecera de cash pooling y la fábrica de pagos |
| `bank_accounts.csv` | Cuentas propias: IBAN, divisa, banco y formato de extracto (y el nuevo desde 2025-10-01) |
| `customers.csv` | 55,7 k clientes: tipo, IBAN conocido, mandato SEPA, condiciones, divisa, `group_id` y `parent_customer_id` |
| `suppliers.csv` | 12,8 k proveedores: IBAN, método y condiciones de pago |
| `categories.csv` | Las 21 categorías válidas para movimientos sin partida |
| `payment_terms.csv` | 13 condiciones de pago; cuatro con descuento por pronto pago (`D2N30`, `D1N60`, `D3N45`, `D2N30US`) |
| `fx_rates.csv` | Tipos diarios del BCE (unidades por EUR, solo días TARGET; en festivos vale el último). MAD derivado de la cesta de Bank Al-Maghrib |

Los maestros son una foto: los clientes renombrados salen con el nombre actual y los cambios de IBAN no siempre están reflejados.

### 5.5 Volumen

| | TRAIN | LIVE |
| --- | --- | --- |
| Movimientos | 1.489.931 | 203.083 |
| Facturas emitidas | 3.963.735 | 487.243 |
| Facturas recibidas | 1.530.203 | 199.414 |
| Abonos | 150.215 | 19.500 |
| PDFs | 131.638 | 16.689 |
| Avisos de remesa | 50.891 | 6.890 |
| Filas del golden | 5.403.411 | oculto (~750 k según el README) |

El paquete completo pesa 2,3 GB en disco. El starter tarda «unos minutos» y usa ~8 GB de RAM sobre TRAIN.

## 6. Salida

Un CSV por fase (`FORMAT.md`): UTF-8, coma, con cabecera, opcionalmente `.csv.gz`. **≤ 60 MB sin comprimir y ≤ 3 M filas.**

```
bank_txn_id,item_id,amount,category,exception
BT-2025-0001234,ARI-2025-0456789,1210.00,,
BT-2025-0001234,ARI-2025-0456790,605.00,,
BT-2025-0001234,ARC-2025-0012345,121.00,,
BT-2025-0001240,,,BANK_FEES,
BT-2025-0001300,ARI-2025-0400001,980.00,,SHORT_DISCOUNT
BT-2025-0001301,,,UNIDENTIFIED,UNIDENTIFIED
BT-2025-0001302,ARI-2025-0400002,400.00,,PARTIAL
BT-2025-0001310,API-2025-0077777,15300.00,,FX_DIFFERENCE
```

| Columna | Regla |
| --- | --- |
| `bank_txn_id` | Un movimiento de la fase. **Los que falten cuentan como fallo** |
| `item_id` | `ARI\|ARC\|API\|APC-<año>-<7 dígitos>`. Vacío si el movimiento no liquida ninguna partida |
| `amount` | Importe liquidado de esa partida, **en la divisa de la partida**, **positivo** (también en abonos y devoluciones), con punto decimal. Vacío si no hay `item_id` |
| `category` | Solo en la fila sin partida, de `categories.csv`. Vacía en las filas con partida |
| `exception` | Vacía o un valor de la lista cerrada (§8.2) |

**Validación** (el envío se rechaza con el número de fila si algo falla): cabecera con las cinco columnas exactas; todo `bank_txn_id` de la fase; ningún par `(bank_txn_id, item_id)` repetido; como mucho una fila sin partida por movimiento; un movimiento no puede tener a la vez filas con partida y fila de categoría; `amount` obligatorio y no negativo con `item_id`, vacío sin él; `category` y `exception` de sus listas.

## 7. Puntuación

### 7.1 Fórmula

Se calcula sobre **todos** los movimientos de la fase y es determinista:

> **Score = 100 × (0,5 · Allocation F1 + 0,3 · Transaction accuracy + 0,2 · Exception macro-F1)**, con dos decimales.

| Métrica | Peso | Cómo se mide (`bankrec_score.py`) |
| --- | --- | --- |
| **Allocation F1** | 50 % | Sobre pares `(bank_txn_id, item_id)`. Un par enviado es acierto si está en el golden y su importe está dentro de la tolerancia. Precisión = aciertos / pares enviados; recall = aciertos / pares del golden. **La excepción no cuenta aquí** |
| **Transaction accuracy** | 30 % | Un movimiento es correcto si su conjunto completo de (partida, importe, excepción) es igual al del golden: ni una partida de más ni de menos. Sin partidas, si coinciden categoría y excepción. Cada movimiento pesa lo mismo |
| **Exception macro-F1** | 20 % | F1 de cada clase de excepción no vacía presente en el golden, por fila, y la media sin ponderar. Una excepción en un par que no está en el golden cuenta como falso positivo de esa clase |

**Tolerancia de importe:** `|enviado − golden| ≤ max(0,01; 0,5 % del golden)`.

La página de resultado enseña además, sin peso: precisión, recall, exactitud ponderada por importe (en EUR) y exactitud por segmento (1:1, 1:N, FX, devoluciones…).

### 7.2 Referencias

| Solución | Puntuación |
| --- | --- |
| `starter.py` (número impreso en el texto + importe exacto) | ~10–15 |
| Naive con respaldo por importe exacto | ≈ 19 |
| Heurística con «reglas bien trabajadas» | ≈ 61 |
| Perfecta (el golden) | 100 |

### 7.3 Lo que se deduce del evaluador [Inferencia]

- **Cada métrica premia una cosa distinta.** El F1 de asignaciones pesa por pares, así que lo dominan los movimientos con muchas partidas: remesas de recibos, avisos de remesa y pagos múltiples a proveedores (§9.2). La exactitud por movimiento pesa por líneas, así que la dominan los cobros 1:1 con referencia ruidosa (§9.1). La macro-F1 pesa por clase, así que `SHORT_BANK_CHARGES` (~1 k filas en TRAIN) vale lo mismo que `FX_DIFFERENCE` (~114 k).
- **Ningún movimiento sin fila.** Uno que falta es un fallo seguro; uno marcado `UNIDENTIFIED` puede ser un acierto. La FAQ lo dice así: «si no sabes qué es algo, márcalo como UNIDENTIFIED».
- **Enviar pares de más cuesta.** Baja la precisión del F1 y tumba la exactitud de ese movimiento. Forzar una casación es peor que no casar.
- **Una excepción mal puesta cuesta dos veces:** el par sigue contando en el F1, pero el movimiento deja de ser correcto y la clase pierde precisión. Una excepción de más en una fila acertada también resta.
- **El importe tiene que ser el que dicta la política,** no el cobrado: en un descuento por pronto pago va el total de la factura; en un parcial, lo cobrado (§8.1).

### 7.4 Envíos

| | LIVE | FINAL |
| --- | --- | --- |
| Cuántos | Un envío cada **3 min** y **20 al día**, por fase | **Uno**. Cuenta el primer fichero válido; no se repite ni se cambia |
| Puntuación | En minutos; cuenta la mejor | Oculta hasta las 20:30. Es la clasificación final |
| Empates | Gana quien la consiguió antes | Gana el envío FINAL más temprano |
| Fichero inválido | Consume el hueco del límite | No gasta el envío FINAL; se corrige y se vuelve a subir |

- Pedir la URL de subida ya consume un hueco, aunque luego no se suba nada.
- Los equipos sin envío FINAL no entran en la clasificación final.
- Se envía desde la web o por API (`/api/submissions/upload-url` → subida a S3 → `/score` → consulta del estado). Hay script en [/enviar](https://hackathon.usetalky.com/enviar). Consultar como mucho cada 5 s: toda la sala comparte IP. El token va en una variable de entorno, nunca en el código.
- Juego limpio: no compartir el token, no atacar la plataforma ni saltarse los límites, y no intentar obtener el golden de LIVE o FINAL.

## 8. Reglas de etiquetado

Resumen de `POLICIES.md`. **Ante cualquier duda manda el original**; donde no dice nada, «el historial de TRAIN muestra cómo se ha hecho siempre».

### 8.1 Importe de cada fila

| Caso | `amount` |
| --- | --- |
| Pago normal | Importe abierto de la partida |
| Abono compensado en un pago | Su importe completo, positivo, sin excepción |
| Liquidación completa con diferencia explicada (`SHORT_DISCOUNT`, `SHORT_BANK_CHARGES`, `SHORT_WITHHOLDING`, `FX_DIFFERENCE`, `OVERPAYMENT`) | **Importe abierto completo** de la partida, aunque haya llegado menos (o más) dinero |
| No liquidada del todo (`PARTIAL`, `SHORT_DISPUTE`) | **Lo realmente aplicado** a esa partida |
| `DUPLICATE_PAYMENT` | Lo pagado otra vez, en la divisa de la partida |
| `RETURNED` | Lo que se reabre: el importe de la asignación original que se revierte |

### 8.2 Excepciones (lista cerrada)

| Código | Cuándo |
| --- | --- |
| *(vacío)* | Pagado según el documento. También el **último** plazo de un plan, la liberación de una retención, el resto tras un parcial, el pago de un importe que estaba en disputa, un recibo representado y los abonos compensados |
| `PARTIAL` | Tras este movimiento la partida **sigue abierta** y no aplica ningún motivo concreto: pago «a cuenta», cada plazo salvo el último, el primer pago de una factura con retención en garantía, una factura con anticipo de proforma a deducir y un descuento por pronto pago tomado **fuera de plazo** |
| `SHORT_DISCOUNT` | Descuento por pronto pago **dentro de plazo**: las condiciones de la factura tienen descuento, la **fecha de operación** ≤ fecha de factura + días de descuento **+ 3 de gracia**, y el cobro = total − % × **total**, redondeado al céntimo |
| `SHORT_BANK_CHARGES` | Transferencia internacional de fuera de SEPA con comisión de un banco intermediario: diferencia ≤ **60 EUR equivalentes** y ≤ **2 %** de la partida. Por encima, `PARTIAL` |
| `SHORT_WITHHOLDING` | Retención fiscal en origen (algunos clientes de México, Brasil y Marruecos; 1,25 %, 1,5 % o 10 % del total) |
| `SHORT_DISPUTE` | Deducción **con motivo** (diferencia de precio, mercancía dañada, entrega incompleta, penalización…), casi siempre visible solo en el aviso de remesa. Lo disputado queda abierto; si se paga después, ese pago va sin excepción |
| `OVERPAYMENT` | Pago de más sobre una sola factura. El exceso queda a cuenta del cliente, sin fila extra |
| `DUPLICATE_PAYMENT` | La partida ya estaba liquidada y se paga otra vez. La lleva el movimiento posterior. La devolución del duplicado es la categoría `CUSTOMER_REFUND` o `SUPPLIER_REFUND` |
| `RETURNED` | Un cobro o pago vuelve y reabre la partida: recibo devuelto (cualquier código R), cheque impagado, contracargo de tarjeta o transferencia a proveedor rechazada. La llevan todas las partidas de la operación devuelta |
| `UNIDENTIFIED` | Un cobro sin ninguna partida abierta que le corresponda. Una fila con categoría `UNIDENTIFIED` y excepción `UNIDENTIFIED`. **No se fuerza:** hay cobros no identificados con el importe exacto de una factura ajena |
| `FX_DIFFERENCE` | El movimiento va en **otra divisa** que la partida. El banco convierte con un diferencial sobre el BCE del 0,1–0,6 % (G10) o del 0,4–1,5 % (emergentes), siempre por debajo del 3 %. Sustituye a vacío, `SHORT_DISCOUNT`, `SHORT_WITHHOLDING` y `SHORT_BANK_CHARGES` en las **facturas** liquidadas del todo; `PARTIAL` y `SHORT_DISPUTE` se mantienen; los abonos van vacíos |

### 8.3 Movimientos sin partida (`category`)

`BANK_FEES`, `INTEREST_INCOME`, `INTEREST_EXPENSE`, `PAYROLL`, `SOCIAL_SECURITY`, `TAX_PAYMENT`, `TAX_REFUND`, `LOAN_DRAWDOWN`, `LOAN_REPAYMENT`, `LEASING`, `FX_DEAL`, `CASH_POOL`, `INTERCOMPANY`, `INTERNAL_TRANSFER`, `CUSTOMER_ADVANCE`, `CUSTOMER_REFUND`, `SUPPLIER_REFUND`, `CARD_EXPENSES`, `INSURANCE`, `BANK_REVERSAL` y `UNIDENTIFIED`.

Las reglas que no se ven solo por el nombre:

- La comisión de una transferencia internacional suele llegar como **otra línea el mismo día** (`BANK_FEES`).
- La liquidación de tarjetas **no** es una comisión: liquida los pedidos por su bruto, y la comisión del adquirente no es excepción.
- `CASH_POOL`: barridos entre la cabecera y las filiales, las dos patas. `INTERNAL_TRANSFER`: entre cuentas de la misma sociedad. `INTERCOMPANY`: financiación entre sociedades del grupo. `FX_DEAL`: las dos patas.
- `BANK_REVERSAL`: el apunte erróneo del banco **y** su anulación.
- `CUSTOMER_ADVANCE`: el pago de una proforma, porque la factura aún no existe.
- Si un proveedor nos reembolsa uno de **sus abonos**, no es categoría: liquida el `APC`.

### 8.4 Cómo se eligen las partidas

1. **No siempre paga el cliente:** la matriz por sus filiales (`group_id`, `parent_customer_id`), un banco de confirming («CONFIRMING … ORD. <cliente>») o una agencia de recobro («EXPTE …»). Se asigna a las facturas del cliente por el que se paga.
2. **Fábrica de pagos:** ES00 paga facturas de proveedor de ES01, ES02 y PT01 desde sus cuentas. Las partidas son las de la filial.
3. **Agregados:** remesas de recibos, liquidaciones de tarjeta, ingresos de cheques, remesas de pago y confirming liquidan todo lo que lista su fichero de detalle (§5.3). Una transferencia individual liquida lo de su `end_to_end_id`.
4. **Avisos de remesa:** dicen qué documentos paga un cobro, a veces con los números de comprobante del cliente o el nuestro sin prefijo. El texto del banco solo trae la referencia de pago del cliente.
5. **Referencias ruidosas:** sin prefijo ni ceros a la izquierda, erratas, dígitos cambiados de sitio, cortadas a 16, 35 o 38 caracteres, el pedido del cliente en vez de nuestro número, un número anulado, o nada (solo nombre o IBAN). El nombre del ordenante viene truncado o es un nombre comercial; los clientes renombrados salen en el maestro con el nombre actual.
6. **Mismo importe, varias facturas abiertas:** sin referencia, la **más antigua** (FIFO por fecha de factura). Si el texto nombra un mes («MANT. MAYO 25»), la factura de **ese mes de servicio**, que se emite a principios del mes siguiente.
7. **Anula y sustituye:** un pago que cita la factura anulada liquida la **sustituta**. La anulada y su abono nunca se liquidan por banco.
8. **Plazos, retenciones y anticipos:** solo los dice el PDF de la factura.
9. **Abonos:** los de devolución o precio citan su factura. Los de rappel son trimestrales y su PDF dice si se compensan o se pagan por transferencia. Los de proveedor se compensan en la siguiente remesa o los reembolsa el proveedor.
10. **Recibos devueltos:** a menudo se representan en una remesa posterior (`re_presentation=Y`) o el cliente paga luego por transferencia.
11. **Cuenta nueva:** los clientes avisan por carta (PDF) de un nuevo IBAN de pago.

## 9. Qué dice el golden de TRAIN

Medido por nosotros sobre `train/golden_allocations.csv.gz` (6 nov 2026). Columnas: `bank_txn_id, item_id, amount, category, exception, segment, difficulty`. Hay 72 segmentos y una dificultad de 1 a 3 por movimiento.

### 9.1 Por movimientos (manda en la exactitud, 30 %)

1.489.931 movimientos. El 68 % liquida una sola partida o es una fila sin partida; el 4,7 % liquida 10 partidas o más (máximo: 1.540). Dificultad: 27 % nivel 1, 44 % nivel 2, 29 % nivel 3.

| Segmento | Movimientos | % |
| --- | --- | --- |
| `ar_ref_noise` (cobro con referencia ruidosa) | 312.717 | 21,0 |
| `ap_payment_multi` (pago a proveedor de varias facturas) | 174.406 | 11,7 |
| `ar_1to1` (cobro 1:1 limpio) | 141.038 | 9,5 |
| `ap_payment_single` (pago a proveedor de una factura) | 139.376 | 9,4 |
| `ar_same_amount_fifo` | 49.049 | 3,3 |
| `nonitem_bank_fees` | 46.984 | 3,2 |
| `ar_1toN_text` | 46.644 | 3,1 |
| `ar_short_discount` | 42.704 | 2,9 |
| `ap_direct_debit` | 41.335 | 2,8 |
| `ar_same_amount_month` | 33.429 | 2,2 |
| `ap_paid_by_holding` | 33.363 | 2,2 |
| `ar_instalment` | 33.008 | 2,2 |
| Resto (60 segmentos) | | 26,6 |

### 9.2 Por pares (manda en el F1 de asignaciones, 50 %)

5.260.781 pares. Cinco segmentos son más de la mitad:

| Segmento | Pares | % | Acumulado |
| --- | --- | --- | --- |
| `ar_dd_batch` (remesas de recibos) | 713.554 | 13,6 | 13,6 |
| `ar_short_dispute` (avisos de remesa con deducciones) | 688.803 | 13,1 | 26,7 |
| `ar_ref_noise` | 676.604 | 12,9 | 39,5 |
| `ap_payment_multi` | 598.314 | 11,4 | 50,9 |
| `ar_1toN_remittance` | 388.502 | 7,4 | 58,3 |
| `ap_fx` | 333.754 | 6,3 | 64,6 |
| `ar_1toN_text` | 259.925 | 4,9 | 69,6 |
| `ar_1toN_credit_note` | 229.078 | 4,4 | 73,9 |

Por tipo de partida: `ARI` 3,72 M, `API` 1,43 M, `ARC` 57 k, `APC` 48 k; y 143 k filas sin partida.

### 9.3 Excepciones (manda en la macro-F1, 20 %)

| Excepción | Filas | Sobre todo en |
| --- | --- | --- |
| `FX_DIFFERENCE` | 113.508 | `ar_fx`, `ap_fx` |
| `SHORT_DISCOUNT` | 100.174 | `ar_1toN_remittance`, `ar_short_discount` |
| `PARTIAL` | 91.664 | `ar_instalment`, `ap_partial`, `ar_partial`, `ar_n_to_m` |
| `UNIDENTIFIED` | 34.653 | `unidentified`, `unidentified_lookalike` |
| `SHORT_WITHHOLDING` | 33.818 | `ar_short_withholding` |
| `RETURNED` | 30.358 | `ar_dd_returned`, `ap_returned_transfer` |
| `SHORT_DISPUTE` | 20.238 | `ar_short_dispute` |
| `DUPLICATE_PAYMENT` | 4.927 | `ar_duplicate_payment`, `ap_duplicate_payment` |
| `OVERPAYMENT` | 2.838 | `ar_overpayment` |
| `SHORT_BANK_CHARGES` | 1.130 | `ar_short_bank_charges` |

Categorías más frecuentes en las filas sin partida: `BANK_FEES` (70 k), `UNIDENTIFIED` (35 k), `CASH_POOL` (13 k), `PAYROLL`, `INTERCOMPANY`, `LEASING`, `BANK_REVERSAL`, `CUSTOMER_REFUND` y `CUSTOMER_ADVANCE` (2–4 k cada una).

## 10. Casos tipo

La página de [ejemplos](https://hackathon.usetalky.com/ejemplos) resuelve 36 casos reales de TRAIN, uno por segmento. Lo que decide cada familia y la trampa que señalan:

| Familia | Segmentos | Qué decide | Trampa |
| --- | --- | --- | --- |
| Cobros 1:1 | `ar_1to1`, `ar_ref_noise`, `ar_same_amount_fifo`, `ar_same_amount_month` | Número impreso; si no hay, ordenante + importe exacto; si hay empate, FIFO o el mes citado | Buscar el `item_id` en el texto; quedarse sin respuesta por no haber número |
| 1:N | `ar_1toN_remittance`, `ar_1toN_credit_note`, `ar_1toN_text` | El aviso de remesa; los números del concepto, que siguen en el siguiente campo de 38 caracteres | Buscar combinaciones que sumen el importe; olvidar el abono como fila propia |
| N:1 | `ar_instalment`, `ar_partial`, `ar_n_to_m` | El PDF (plazos) o el importe pagado | Poner el total de la factura en un parcial |
| Pagos de menos | `ar_short_discount`, `ar_short_bank_charges`, `ar_short_withholding`, `ar_short_dispute`, `ar_discount_late` | Condiciones de pago y fechas, origen no SEPA, país del cliente, aviso de remesa | Marcar `PARTIAL` un descuento; poner la excepción en todas las filas de la remesa |
| Sobrepagos y duplicados | `ar_overpayment`, `ar_duplicate_payment`, `ap_duplicate_payment` | Que la partida ya estuviera liquidada | Buscar otra factura parecida para no dejarlo sin casar |
| Divisas | `ar_fx`, `ap_fx` | `orig_amount`/`orig_currency` y `fx_rates.csv` | Escribir el importe en la divisa de la cuenta |
| Paga un tercero | `ar_third_party_parent`, `ar_third_party_agency`, `ar_third_party_confirming`, `ap_paid_by_holding`, `ap_factored` | Maestro de clientes, concepto con el ordenante real, PDF de cesión | Buscar facturas solo del ordenante |
| Devoluciones | `ar_dd_returned`, `ar_cheque_returned`, `ar_card_chargeback`, `ap_returned_transfer` | El mandato o el cheque de la operación original | Tratarlo como comisión |
| Agregados | `ar_dd_batch`, `ar_card_settlement`, `ar_cheque_deposit`, `ap_confirming`, `ap_payment_multi` | El fichero de detalle | Casar el total con una sola partida; usar el neto de tarjeta |
| Solo en el documento | `ar_retention`, `ar_retention_release`, `ar_advance_deduction`, `ar_replaced_invoice`, `ar_new_iban`, `ar_credit_note_paid_out` | El PDF | Casar con la factura anulada; descartar un IBAN desconocido |
| Sin partida | `nonitem_*`, `customer_refund`, `customer_advance`, `ap_supplier_refund` | Código y texto del banco | Forzar una factura con importe parecido |
| No identificados | `unidentified`, `unidentified_lookalike` | Que ni el tercero ni el texto respalden ninguna partida | Casar solo por importe |

## 11. Implicaciones para el desarrollo [Inferencia]

1. **FINAL es un solo disparo con 90 minutos.** El sistema completo (ingesta, casación, escritura y validación local del CSV) tiene que correr de principio a fin sin tocar código, sobre datos nuevos y con una sociedad nueva, en bastante menos de 90 minutos. Se ensaya con LIVE antes de las 18:00, cronometrado.
2. **TRAIN es el banco de pruebas, LIVE el termómetro.** El scorer oficial corre en local sobre TRAIN sin gastar envíos, con desglose por segmento. LIVE da 20 envíos al día. Ajustar reglas hasta el último decimal de LIVE es sobreajustar: FINAL trae drift.
3. **Primero cubrir, luego acertar.** Desde el primer envío: todos los movimientos con fila, con un respaldo seguro (cobro sin casación → `UNIDENTIFIED`; cargo sin casación → la categoría más probable por código y texto).
4. **Lo que más puntos mueve:** los agregados con fichero de detalle (remesas, tarjetas, cheques, remesas de pago), que dan muchos pares casi deterministas; el cobro con referencia ruidosa (21 % de los movimientos); y los avisos de remesa (1:N con descuentos y disputas).
5. **Las clases raras valen lo mismo que las comunes en la macro-F1.** `SHORT_BANK_CHARGES`, `OVERPAYMENT` y `DUPLICATE_PAYMENT` piden reglas propias y precisas.
6. **Hay que leer PDFs y avisos de remesa en cuatro formatos** (pdf, csv, xlsx y texto de correo). Son 16,7 k PDFs y 6,9 k avisos en LIVE: o se extraen con reglas o un LLM a esa escala necesita presupuesto de tiempo y coste.
7. **Hay que llevar el saldo abierto de cada partida** a lo largo de la fase, en orden de fecha: es lo que distingue `PARTIAL` del último plazo, `DUPLICATE_PAYMENT` de un pago normal y `RETURNED` de un cobro. Se parte de `open_items_at_start` más las partidas emitidas en la fase.
8. **Escala:** ~200 k movimientos y ~1 M de partidas por fase en LIVE y FINAL; 1,5 M y 5,6 M en TRAIN. Nada de bucles movimiento × partida: índices por sociedad, tercero, importe y número normalizado.
9. **El jurado ve el enfoque.** Vídeo, repositorio y descripción antes de las 19:45: cada casación debería poder explicarse con la regla y el documento que la produjo.

## 12. Discrepancias y huecos en las fuentes

| Tema | Lo que dicen | Qué hacemos |
| --- | --- | --- |
| Divisas | La web dice 9; el README, 12; los extractos de TRAIN tienen 11, más ZAR en LIVE | Leerlas de los datos, nunca de una lista fija |
| Cuentas | La web dice ~56; el README, ~50; el maestro trae 47; hay 48 con movimientos en TRAIN y 49 en LIVE | Igual |
| ZA01 en LIVE | Se adquiere el 2026-01-01, pero LIVE ya trae 2 movimientos de la cuenta `ZA01-UMVC-ZAR` (29 y 30 dic 2025, «PROFORMA PF25-…») que no están en el maestro | **[Inferencia]** Son pagos de proforma, así que `CUSTOMER_ADVANCE`. Comprobarlo con la organización |
| Fichero inválido | FAQ: «Un envío no válido sigue consumiendo un hueco». Reglas: en FINAL «no gasta el envío» | Lo leemos como compatible: gasta un hueco del límite de frecuencia, no el envío FINAL. Validar siempre en local con `bankrec_score.py` antes de subir |
| Pesos del ranking | El ranking final es la puntuación de FINAL; el jurado «valora vuestro enfoque» | No se publica cómo pesa el jurado en los premios. Preguntar |

### 12.1 Preguntas para la organización

- [ ] ¿Cómo influye el jurado (vídeo, repo, descripción) en los premios frente a la puntuación de FINAL?
- [ ] ¿Los 2 movimientos de ZA01 en LIVE son intencionados? ¿Qué etiqueta llevan?
- [ ] ¿`final/masters_final/` sustituye a `masters/` o lo complementa?
- [ ] ¿El límite de 20 envíos al día se reinicia a medianoche? (El evento dura un solo día, así que en la práctica son 20 en LIVE.)

## 13. Glosario

| Término | Significado |
| --- | --- |
| Movimiento | Una línea del extracto bancario (`bank_txn_id`), con signo: + cobro, − pago |
| Partida abierta | Factura o abono pendiente de cobrar o pagar: `ARI`, `ARC`, `API`, `APC` |
| Número impreso | El número que lleva el documento y cita la contraparte (`FV25-0400572`). No es el `item_id` |
| Asignación | Una fila del CSV: un par (movimiento, partida) con su importe y su excepción |
| Golden | Las respuestas correctas. Solo existen públicamente para TRAIN |
| Aviso de remesa | Documento del cliente que dice qué facturas paga una transferencia |
| Remesa de recibos | Cobro agrupado de recibos domiciliados (SEPA, BACS, ACH) que llega como un solo abono |
| Confirming | Servicio por el que un banco paga a los proveedores por cuenta del cliente |
| Cash pooling | Barridos automáticos de saldo entre las cuentas de las filiales y la cuenta cabecera (ES00) |
| Norma 43 · MT940 · camt.053 | Formatos de extracto bancario: español (AEB), SWIFT e ISO 20022 |
| Drift | Cambios a propósito entre fases: formatos, clientes, una filial nueva |

## 14. Terminado

- [ ] El sistema lee una fase completa (`train`, `live` o `final`) sin modificar los datos de entrada.
- [ ] Escribe un CSV que pasa la validación de `bankrec_score.py`, con **una fila o más para cada movimiento** de la fase.
- [ ] Se puntúa en local sobre TRAIN con desglose por segmento, y supera la referencia heurística (≈ 61).
- [ ] Ha enviado LIVE y está en la clasificación.
- [ ] Ejecuta LIVE de principio a fin, cronometrado, en un tiempo que deja margen dentro de los 90 minutos de FINAL.
- [ ] Soporta una sociedad, una divisa y una numeración nuevas sin cambiar código (ZA01).
- [ ] Cada asignación lleva la regla y el documento que la produjeron.
- [ ] FINAL enviado antes de las 19:30; vídeo, repositorio y descripción entregados antes de las 19:45.
