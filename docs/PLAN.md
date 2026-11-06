# PLAN.md — Pipeline y plataforma para Close the Books, con tres sesiones en bucle

Plan de trabajo para la noche del 6 al 7 de noviembre de 2026 y el día del evento. Parte de [ANALYSIS.md](ANALYSIS.md) (cifras, techos por segmento, drift) y de [ARCHITECTURE.md](../ARCHITECTURE.md) §7 (diseño del backend). Lo marcado **[Inferencia]** es estimación nuestra; lo demás sale del paquete oficial, de la web del reto o de lo medido.

## 0. Qué significa «terminado»

Dos productos, un criterio comprobable cada uno:

| Producto | Terminado cuando |
| --- | --- |
| **Pipeline** (`backend/`) | `closebooks run --phase final` corre de principio a fin en < 15 min sobre una fase nunca vista, escribe un `submission.csv.gz` que pasa la validación oficial, cubre todos los `bank_txn_id`, pesa < 60 MB y, sobre el *holdout* (§4), puntúa ≥ 95 con exactitud ≥ 0,9 en todos los segmentos de más de 1.000 movimientos **[objetivo; el 100 % no está garantizado, ver §8]** |
| **Plataforma** (`app/` + API) | Con una ejecución real de LIVE cargada (203 k movimientos, ~750 k filas), cada pantalla de §3 abre en < 2 s, muestra los datos del paquete y el resultado del pipeline con su regla y evidencia por fila, y las tres interacciones con el agente (pregunta, borrador de correo, regla de memoria) funcionan de extremo a extremo con cero errores en consola; `just fe-check` y `just be-check` en verde |

Lo que **no** es terminado: una regla que sube un segmento y baja otro; una pantalla que solo funciona con los fixtures; un envío a la clasificación hecho por un agente (prohibido: lo hace una persona).

## 1. Resumen del proyecto

Grupo Valtermia (17 sociedades, 12 divisas, 13 bancos) recibe ~220 k movimientos bancarios por semestre. El reto: para cada movimiento, decir qué partidas (facturas y abonos, propios y de proveedor) liquida y por qué importe, o qué es si no liquida ninguna, marcando las excepciones de una lista cerrada. Se puntúa con un evaluador público (F1 de pares 50 %, exactitud por movimiento 30 %, macro-F1 de excepciones 20 %). TRAIN (4 años) trae las respuestas; LIVE se puntúa en una clasificación pública; FINAL se publica a las 18:00 del sábado con un único envío y decide el ganador. El jurado valora además vídeo, repo y descripción.

Lo que vamos a construir:

1. **Un pipeline determinista** (Python, Polars) que reconcilia en pasadas por certeza (ficheros de detalle → avisos de remesa → números en el texto → tercero + importe + saldo abierto → categorías → respaldo), con un modelo (Haiku o Sonnet) solo para extraer hechos de documentos que los parsers no lean, con caché. Cada fila sale con su regla, su evidencia, su confianza y su tercero: eso alimenta la plataforma.
2. **Una plataforma operativa** sobre esos resultados, en el estilo de Kapia/Stuut/Rex: no una tabla de casaciones, sino **casos** que el sistema cierra solo o que necesitan a una persona, con una bandeja de decisiones, borradores de correo a clientes y proveedores que una persona revisa y «envía», preguntas del agente cuando una regla no decide, y reglas de memoria que el pipeline aplica en la siguiente ejecución. Con los datos del paquete: exploración de movimientos, partidas, terceros, cuentas y documentos a escala real.
3. **Un banco de pruebas** con el que las sesiones iteran sin gastar envíos: `sample/` (segundos), TRAIN por segmento (minutos), un *holdout* que imita FINAL (los últimos seis meses de TRAIN con sus partidas abiertas al inicio y un mutador de drift) y LIVE como termómetro de una persona.

## 2. Arquitectura objetivo

```
db/<fase>/ + masters ──▶ backend (closebooks) ──▶ runs/<fase>-<ts>/ ──▶ API (FastAPI + DuckDB) ──▶ app/ (React)
                                                      │                        ▲
                               submission.csv.gz ◀────┘                        │  decisiones, reglas de memoria,
                               explanations, cases, facts, questions, run.json  │  borradores aprobados (runs/<id>/human/)
```

**La carpeta de ejecución es el contrato** entre las dos sesiones (CONTRACT.md v2, §2.1). Backend y frontend se desarrollan contra ella; ninguna sesión importa código de la otra.

### 2.1 CONTRACT.md v2: lo que escribe una ejecución

| Fichero | Para qué | Quién lo lee |
| --- | --- | --- |
| `submission.csv.gz` | La entrega oficial | evaluador, consola FINAL |
| `explanations.jsonl.gz` | Una línea por fila del CSV: `rule`, `confidence`, `partyId`, `sources[]` (aviso, fichero, PDF, maestro, otro movimiento), `reference` extraída, `candidates[]` descartados (solo en reglas ambiguas) | plataforma: detalle del movimiento |
| `cases.jsonl.gz` | **Un caso por movimiento o por lote** con `status` (`auto`, `needs_review`, `question`, `fallback`), `kind` (p. ej. `unidentified_receipt`, `dispute`, `duplicate_payment`, `returned_dd`, `supplier_invoice_mismatch`, `overdue_customer`), `priority`, `amountEur`, `entity`, `party`, `summary`, `suggestedAction` | bandeja, colas, KPIs |
| `facts/documents.parquet` | Hechos extraídos de avisos y PDFs: `(documento, número, importe, deducción, motivo, cláusula)` con el método (`parser` / `model`) y la caché | detalle de evidencia; auditoría del uso de modelo |
| `facts/parties.parquet` | Tercero resuelto por movimiento (cómo: `counterparty`, `iban`, `name-ngram`, `mandate`, `group`) y su confianza | detalle, explorador de terceros |
| `state/open_items.parquet` | Saldo abierto por partida al final de la fase y su historia de liquidaciones | aging, cobros (*collections*), cuentas |
| `questions.jsonl` | Preguntas del agente: `id`, `case`, `question`, `options[]`, `defaultAction`, `rulePreview` (qué regla de memoria propondría la respuesta) | bandeja «te necesitan» |
| `drafts.jsonl` | Borradores de correo: a cliente (cobro vencido, duplicado a devolver, disputa) o a proveedor (factura que no cuadra con la remesa, duplicado nuestro), con `to`, `subject`, `body`, `attachments[]` (ids de documentos) | bandeja, pantalla de revisión y envío |
| `run.json` | Fase, commit, duración, filas, `byRule`, `byCase`, modelos usados, llamadas y coste, puntuación local si hay golden (por segmento) | resumen, historial de ejecuciones |
| `human/` (lo escribe la plataforma) | `decisions.jsonl` (respuestas a preguntas, casos marcados), `memory_rules.jsonl` (reglas guardadas: «el pagador X paga por el cliente Y», «ignorar sufijo Z en las referencias de W», «el proveedor P siempre neta sus abonos»), `outbox.jsonl` (correos aprobados y «enviados»: simulado, con registro) | el pipeline en la siguiente ejecución (`closebooks run --memory runs/<id>/human/`) |

Invariantes que ya están en CONTRACT.md v1 (todos los `bank_txn_id`, validación oficial, una explicación por fila, `FALLBACK-*` sin forzar, determinismo byte a byte con la misma caché) se mantienen.

### 2.2 Backend (`backend/`)

Python 3.12, Polars, DuckDB para servir, pypdf, openpyxl, rapidfuzz, SDK de Anthropic, FastAPI. Módulos como en ARCHITECTURE §7.2, con tres añadidos: `cases.py` (construye los casos y las acciones sugeridas a partir de explicaciones y estado), `memory.py` (carga `human/memory_rules.jsonl` y las aplica como regla de máxima prioridad, con su evidencia `memoryRule`) y `api/` (FastAPI de solo lectura sobre `runs/` y `db/`, con escritura solo en `runs/<id>/human/`).

**Reglas, en el orden de certeza** (los bloques y techos son los de ANALYSIS §5):

| Pasada | Regla | Segmentos | Techo |
| --- | --- | --- | --- |
| R1 | `FILE-PAYMENT-RUN` (remesas de pago por `run_id`/`end_to_end_id`/cuenta+fecha+importe), `FILE-DD-BATCH`, `FILE-CARD`, `FILE-CHEQUE`, `FILE-DD-RETURN` | todos los `ap_*` con fichero, `ar_dd_batch`, `ar_card_settlement`, `ar_cheque_deposit`, `ar_dd_returned`, chargebacks | 47,6 |
| R2 | `ADVICE-*` (aviso → cobro por referencia o por pagador+importe+fecha; filas → partidas; deducciones → `SHORT_DISPUTE`/`SHORT_DISCOUNT`; abonos) | `ar_1toN_remittance`, `ar_short_dispute`, `ar_dispute_settlement` | 21,3 |
| R3 | `REF-EXACT`, `REF-NOPREFIX`, `REF-SUFFIX`, `REF-MULTI` (varios números en el texto, suma = importe, abonos netos) | `ar_1to1`, `ar_1toN_text`, `ar_1toN_credit_note`, `ap_payment_single` sin fichero | 10 |
| R4 | `PARTY-AMOUNT` (tercero por `counterparty`/IBAN/n-gramas/mandato/grupo/factor; subconjunto único de sus partidas abiertas; FIFO o mes del texto) | `ar_ref_noise`, `ar_same_amount_*`, `ar_partial`, `ar_n_to_m`, terceros, `ar_new_iban` | 24 |
| R5 | `HISTORY-DUPLICATE`, `HISTORY-RETURNED`, `HISTORY-REPRESENTED` (contra la historia de la partida) | duplicados, devoluciones sin fichero | 4,6 |
| R6 | `CAT-CODE`, `CAT-TEXT` (tabla banco/código/subcódigo aprendida de TRAIN + palabras clave) y `CAT-SUPPLIER-REFUND` (liquida el `APC`) | `nonitem_*`, `customer_*`, `ap_supplier_refund` | 1,5 |
| R7 | `FALLBACK-UNIDENTIFIED`, `FALLBACK-CATEGORY` | lo demás | — |
| `policy.py` | importe y excepción: descuento en plazo (+3 días de gracia), retención por país y tasa, comisión ≤ 60 EUR y ≤ 2 % fuera de SEPA, sobrepago, FX por `orig_currency`, parcial/último plazo/retención/anticipo por saldo y PDF, `RETURNED` por importe reabierto | clases de 2 puntos | 16 + 3,7 |
| `memory.py` | reglas de memoria de `human/`: prioridad máxima, evidencia `memoryRule` | — | — |

**Extracción con modelo, acotada.** Parsers primero (avisos csv/txt/xlsx en los dos layouts; pdf vía pypdf + regex con la tabla `Document Date Gross Deduction Paid`; cláusulas de los PDFs de factura con regex). El modelo (`claude-haiku-5-5`; Sonnet solo si Haiku falla una validación) recibe únicamente el texto del documento que el parser no ha cerrado y devuelve un JSON tipado `(filas, cláusulas)` que se valida (sumas, formatos) antes de usarse; se guarda en caché por hash del fichero, en `backend/cache/documents/` **versionado por fase** (decisión §9) para que viaje entre portátiles. Presupuesto: ≤ 2.000 llamadas por fase **[Inferencia: residuo del 5 %]**, con contador en `run.json` y corte duro configurable. **El modelo nunca elige una partida.** En desarrollo, las llamadas se hacen con la clave de API del equipo; si no la hay, con `claude -p --model haiku` bajo la suscripción, en serie y solo para el residuo.

**Borradores de correo** (clientes y proveedores) los redacta el modelo a partir de un caso y sus documentos, con plantilla por `kind` e idioma del tercero, **solo bajo demanda** de la plataforma (botón «preparar correo») o para los N casos de mayor importe al final de la ejecución (N configurable, 0 por defecto en los bucles de desarrollo). Nunca se envía nada: `outbox.jsonl` registra el «envío».

**Preguntas del agente**: una regla que se queda entre dos candidatos con la misma evidencia (p. ej. dos facturas del mismo tercero e importe sin FIFO aplicable, un aviso que cuadra con dos cobros, un pagador desconocido que paga el importe exacto de un cliente) **no fuerza**: emite `FALLBACK-*` en el CSV y una `question` con las opciones y la regla de memoria que resultaría. La respuesta humana se guarda y la siguiente ejecución la aplica. En la puntuación, estas preguntas son exactamente los casos que hoy perderíamos; en la plataforma, son la demostración de «sabe que no sabe».

**CLI** (`just be-*` por debajo): `closebooks run --phase <sample|train|holdout|live|final> [--memory DIR] [--max-model-calls N] [--out runs/...]`, `closebooks score <run>` (evaluador oficial con el límite de 60 MB relajado en local y desglose por segmento; con `--compare <run>` enseña qué segmentos suben y bajan), `closebooks validate <csv>` (solo validación, sin golden), `closebooks serve <run>` (API), `closebooks holdout build` (§4).

### 2.3 Plataforma (`app/` + API)

Se **descongela el frontend** (hoy fase 0 para el problema antiguo: decisión §9). Se conserva el shell, los tokens de Talky, los dos temas, `DataTable`, `SidePanel`, `Amount`, `Mono` y el registro de vistas; se sustituyen el dominio, la capa de datos (del zip en el navegador a la API paginada) y las vistas. Stack: React 19, Vite, TypeScript estricto, TanStack Query + Virtual, CSS Modules, vitest, oxlint.

Pantallas, por orden de prioridad (las cuatro primeras son el mínimo para el vídeo):

| # | Pantalla | Qué enseña | Fuente |
| --- | --- | --- | --- |
| 1 | **Resumen** (como el «pulso» de Kapia) | Movimientos conciliados sin intervención (% y nº), importe identificado en EUR, cola de revisión, excepciones por tipo, evolución por día de la fase; por sociedad; puntuación por segmento si hay golden | `run.json`, `cases`, `state` |
| 2 | **Bandeja: te necesitan** | Casos `needs_review`/`question`/`fallback` ordenados por prioridad e importe, con filtros (tipo, sociedad, antigüedad, responsable). Cada caso: *Responder* (pregunta con opciones), *Revisar correo* (borrador editable, «enviar» o «llevarlo yo»), *Marcar gestionado*. Al responder, opción «guardar como regla» | `questions`, `drafts`, `cases`, `human/` |
| 3 | **Conciliación** (movimientos) | Tabla virtualizada de los 203 k movimientos con búsqueda y facetas (sociedad, cuenta, formato, regla, excepción, estado del caso); panel lateral con el movimiento tal y como llega del banco, las partidas asignadas con importe y excepción, la regla, la evidencia (aviso, fichero, PDF, maestro) abierta en línea, el tercero y los candidatos descartados | `bank_transactions`, `explanations`, `facts` |
| 4 | **Cobros** (*collections*, como Rex) | Clientes con saldo vencido: aging, promesas (de las decisiones), disputas abiertas (`SHORT_DISPUTE` pendientes), duplicados a devolver, riesgo (patrón de pago que cambia); acción: preparar correo de reclamación con las facturas adjuntas | `state/open_items`, `cases` |
| 5 | **Proveedores** | Facturas de proveedor cuyo pago no cuadra con la remesa o se pagó dos veces; acción: correo al proveedor (pedir abono, reclamar reembolso) | `cases`, `facts` |
| 6 | **Cuentas bancarias** | Las 49 cuentas con banco, formato (y el cambio de octubre), divisa, movimientos y saldo acumulado del periodo, % conciliado por cuenta | `bank_transactions`, maestro |
| 7 | **Explorador de datos** | Partidas (AR, AP, abonos, abiertas al inicio), terceros (clientes con grupo y matriz, proveedores), documentos (avisos y PDFs con su texto extraído y los hechos), ficheros de detalle | `db/` vía API |
| 8 | **Memoria y reglas** (como el «contexto» de Kapia) | Reglas de memoria guardadas, con quién las creó y a cuántos movimientos afectan; las políticas (`POLICIES.md`) como documento de referencia | `human/memory_rules` |
| 9 | **Ejecuciones** | Historial de ejecuciones con duración, filas por regla, llamadas a modelo y coste, puntuación; comparación entre dos ejecuciones por segmento; **consola FINAL**: estado de la descarga, un botón «ejecutar», validación, tamaño, y el envío lo hace una persona desde la terminal | `run.json` |

Reglas de diseño: las de CLAUDE.md §6 (marca Talky, dos temas, una acción primaria por vista, tarjetas, tokens). Las vistas se comprueban en el navegador con una ejecución real de LIVE cargada, no con fixtures; cero errores en consola; capturas en la PR.

## 3. El método: tres sesiones en bucle

| Sesión | Papel | Agentes que levanta |
| --- | --- | --- |
| **Orquestadora** (esta) | Guarda el objetivo y el contrato; reparte trabajo por mensajes; revisa y **fusiona las PRs a `main`** (con tu autorización explícita); mide cada hito (puntuación por segmento, capturas); corrige el rumbo; mantiene `docs/STATUS.md` con el estado cada hora | revisores de PR (`/code-review`), medición |
| **Backend** | Implementa `backend/` por bloques en ramas `KPI-<n>_be-<bloque>`; cada bloque con TDD sobre casos reales y puntuación antes/después por segmento; abre PR cuando el bloque no baja ningún segmento | un agente por bloque de §2.2 en paralelo (ficheros, avisos, referencias, tercero, política, categorías, API), más un agente de evaluación que mantiene el holdout |
| **Frontend** | Implementa la plataforma por pantallas en ramas `KPI-<n>_fe-<pantalla>` contra la API y una ejecución real; cada pantalla se abre en el navegador y se captura | un agente por pantalla, un agente de diseño (`impeccable`, `web-design-guidelines`), un agente de API/contratos coordinado con backend |

**Comunicación.** Las sesiones no se hablan directamente: todo pasa por la orquestadora (mensajes a cada sesión; cada sesión me avisa cuando bloquea o termina un bloque). El punto de encuentro técnico es el contrato (§2.1): cualquier cambio en la carpeta de ejecución lo propone una sesión en una PR que toca solo `CONTRACT.md` y la fusiono antes de que la otra sesión lo use. La API lleva un `openapi.json` versionado que el frontend tipa con `openapi-typescript`.

**Bucle de cada sesión** (`/goal` con el criterio de §0 y los hitos de §5; si `/goal` no está disponible en esa sesión, `/loop` con el mismo texto):

1. Elegir el bloque de más puntos por hora pendiente (backend) o la siguiente pantalla (frontend).
2. Escribir el test que falla (backend: un caso real de `sample/` o TRAIN por comportamiento; frontend: un test de la capa de datos) y el objetivo medible (segmento y puntuación esperada; pantalla y captura).
3. Implementar en rama, correr `just be-check`/`just be-test`/`just fe-check`, medir (`closebooks score --compare` con el último `main`; navegador).
4. Si ningún segmento baja y el check está en verde: PR con la tabla antes/después y las capturas, y aviso a la orquestadora. Si algo baja: no se abre PR; se explica en el mensaje.
5. Volver a 1. Cada hora, resumen de estado a la orquestadora (hecho, medido, bloqueado, siguiente).

**Guardarraíles para todas las sesiones:** nunca enviar nada a la clasificación ni pedir una URL de subida; nunca escribir en `db/`; nunca commitear datos, `runs/` ni el token; cero llamadas a modelos en bucles de desarrollo salvo el residuo de documentos con el contador; Haiku por defecto; commits `[KPI-n] type: subject` sin atribución; PR solo con el check en verde y la medición pegada; `main` siempre ejecuta de principio a fin.

**Coste.** Lo que cuesta de verdad son las sesiones y sus agentes, no el pipeline. Para contenerlo: agentes con `model: sonnet` para implementar y `haiku` para medir y buscar; la orquestadora revisa con `/code-review` en nivel medio; sin agentes ociosos (cada uno nace con un bloque y muere con su PR); los bucles medidos con `sample/` (segundos) y solo cada hito con TRAIN completo (minutos).

## 4. Banco de pruebas y datos sintéticos de FINAL

| Conjunto | Qué es | Para qué | Tiempo |
| --- | --- | --- | --- |
| `sample/` | Junio de 2025 con golden (8.499 movimientos) | el bucle de cada regla | segundos |
| TRAIN | 4 años con golden, puntuado con el evaluador oficial y el límite de tamaño relajado, por segmento | cada hito; decisiones de prioridad | 3–6 min **[Inferencia]** |
| **Holdout «pseudo-FINAL»** | TRAIN cortado el 2024-12-31: `db/holdout/` con los movimientos de 2025-01 → 2025-06, las partidas emitidas en ese periodo, **`open_items_at_start` calculado** desde TRAIN + golden hasta 2024-12-31 (la fórmula se validó contra el de LIVE: coincide en todas las partidas que aparecen; las 212 k de antes de 2021-07 sin estado conocido se excluyen), los ficheros de detalle, avisos y PDFs de esos meses, los maestros y el golden de esos meses. Es una fase con la misma forma que FINAL y con respuestas | ensayo de FINAL con puntuación real: estado inicial, cobertura, tiempo, tamaño | 1 min |
| **Holdout mutado** | El holdout con drift aplicado por `closebooks holdout build --drift`: (a) una sociedad nueva «ZA01» creada clonando MA01 con cuenta, banco, divisa ZAR (tipo de `fx_rates`), numeración `KWI…` y maestros solo en `masters_final/`; (b) un banco que pasa de N43 a camt a mitad de fase (transformación de columnas, el código N43 a `bank_subcode`); (c) el 10 % de los clientes renombrados en el maestro y no en las facturas; (d) los avisos de los 20 mayores pagadores reescritos al layout xlsx nuevo; (e) una cuenta nueva de IT01 que no está en el maestro; (f) pagos 15 días más lentos (desplazar `booking_date` de los cobros 1:1). El golden se transforma con ellos | que ninguna regla dependa de listas fijas, formatos ni nombres; medir la caída por cada tipo de drift | 1 min |
| LIVE | 203 k movimientos sin golden | termómetro: solo una persona envía, en cada hito (§5), ≤ 10 envíos en todo el día | el envío tarda minutos |
| Pruebas unitarias | Un caso real por comportamiento (los 36 ejemplos de la web son el primer lote) y los bordes: referencia cortada, sin prefijo, dígito transpuesto, varias divisas, duplicado, devolución, aviso que llega después, tercero renombrado | `just be-test` | segundos |

El evaluador se usa sin copiarlo (`db/bankrec-docs-and-masters/starter/bankrec_score.py`), con el sha256 comprobado y solo `MAX_UNCOMPRESSED` relajado en local. `closebooks validate` lo usa sin golden para el fichero de FINAL.

## 5. Plan por fases

Hora de Madrid. Las puntuaciones son objetivos **[Inferencia]** en TRAIN (el holdout debería ir 2–5 puntos por debajo por el estado inicial).

| Fase | Cuándo | Backend | Frontend | Orquestadora | Hito medible |
| --- | --- | --- | --- | --- | --- |
| **P0 · cimientos** | 00:00–01:30 | esqueleto: `load`, `index`, `state`, `policy` (vacía), `output`, `score` con límite relajado, `FALLBACK-*`; `holdout build`; CI `be-check`/`be-test` | descongelar: nueva capa de datos contra la API (mock por fixtures de la carpeta de ejecución), dominio v2, shell y rutas de §2.3; `fe-check` | CONTRACT v2, `docs/STATUS.md`, arrancar las dos sesiones, revisar PRs | `closebooks run --phase sample` y `holdout` corren; TRAIN ≈ 12 con todo `FALLBACK`; `app` abre con una ejecución de muestra |
| **P1 · ficheros y categorías** | 01:30–03:30 | R1 (remesas de pago, recibos, tarjetas, cheques, devoluciones), R6 (categorías), `ap_fx` en `policy` | Resumen (1), Conciliación (3) con detalle y evidencia, API `serve` sobre una ejecución real de LIVE | fusionar; primer `closebooks run --phase live` y medir tiempo y tamaño | TRAIN ≈ 55–60; LIVE cargada en la app |
| **P2 · avisos y referencias** | 03:30–05:30 | R2 (parsers de los 4 formatos + layout nuevo; modelo residual con contador), R3, estado en `resolve` (`PARTIAL`, último plazo) | Bandeja (2) con preguntas y borradores leídos de la ejecución; Cuentas (6); Explorador (7) | fusionar; cuadro de puntos por segmento; redirigir a lo que más sube | TRAIN ≈ 75–80; macro-F1 > 0,5 |
| **P3 · tercero y excepciones** | 05:30–08:00 | R4 (tercero por n-gramas/IBAN/mandato/grupo; subconjunto; FIFO/mes), R5, `policy` completa (descuento, retención, comisión, sobrepago, duplicado, FX), PDFs con regex, `memory.py`, `questions`, `cases` | Cobros (4), Proveedores (5), acciones de la bandeja escribiendo en `human/` (responder, guardar regla, revisar y «enviar» correo), Memoria (8) | fusionar; holdout mutado: tabla de caída por drift; `unidentified_lookalike` vigilado | TRAIN ≈ 88–92; holdout ≥ 85; una regla de memoria cambia una ejecución |
| **P4 · endurecer y ensayar** | 08:00–09:30 | `run --phase holdout-drift` sin tocar código; tiempo < 10 min; tamaño; `validate`; borradores de correo para los N casos mayores; `closebooks serve` estable | Ejecuciones (9) con consola FINAL; pulido visual (`impeccable`); capturas para el vídeo | ensayo FINAL cronometrado completo (descarga simulada → run → validate → fichero listo); `docs/STATUS.md` final; lista de riesgos para el día | holdout mutado ≥ 85 sin cambios de código; app sin errores en consola; `fe-check` y `be-check` verdes |
| **Evento** | 10:00–19:30 | el plan de ANALYSIS §7 con el equipo presencial: envíos a LIVE por hito, congelación a las 17:00, FINAL a las 18:00 | vídeo y descripción con la plataforma sobre LIVE | — | un envío FINAL válido antes de las 19:00; entrega del proyecto antes de las 19:45 |

Si a las 05:30 TRAIN no llega a 70, se recorta: el frontend se queda en las pantallas 1–3 y 9, y el backend concentra a todos los agentes en R2 y R4.

## 6. Qué puede ir mal

| Riesgo | Señal | Qué hacemos |
| --- | --- | --- |
| Forzar casaciones (precisión) | `unidentified_lookalike` baja, precisión de pares < 0,98 | umbral de abstención en R4; la regla no entra si baja ese segmento |
| Dos sesiones chocan en el contrato | la app no lee una ejecución nueva | el contrato solo cambia por PR fusionada por la orquestadora; `openapi.json` versionado |
| Las sesiones agotan presupuesto en bucles largos | tokens por hora altos sin PRs | agentes con bloque y muerte; medir con `sample/`; sin modelo en los bucles |
| El estado inicial de TRAIN confunde a R4 | FIFO elige una factura de 2021 pagada antes de TRAIN | en TRAIN, las partidas anteriores a 2021-07 sin asignación no son candidatas; en LIVE/FINAL manda `open_items_at_start` |
| Drift en FINAL | caída en el holdout mutado | nada de listas fijas; maestros de la fase; prueba de ZA01 sintética |
| Tiempo en FINAL | ensayo > 10 min | PDFs solo de los movimientos no resueltos; paralelismo; modelo con corte duro |
| Fichero inválido o > 60 MB | `validate` falla | se arregla antes de subir; sin comillas, dos decimales, sin duplicados |
| Alguien envía por error | — | el token solo lo tiene la persona que envía; los agentes no lo ven |

## 7. Cómo arrancamos (en cuanto apruebes)

1. Fusiono esta rama (`KPI-5_analysis`: análisis, plan y scripts) a `main` tras tu visto bueno, y actualizo `CLAUDE.md` (frontend descongelado, comandos `be-*`), `CONTRACT.md` (v2) y `ARCHITECTURE.md` (§7 con `cases`, `memory`, `api`, holdout).
2. Arranco la **sesión backend** con un brief que contiene §0, §2.1, §2.2, §3, §4 y la fase P0, y la **sesión frontend** con §0, §2.1, §2.3, §3 y P0. Cada una en su worktree, ramas `KPI-6_be-*` y `KPI-7_fe-*`.
3. Cada hora: leo sus resúmenes, mido en `main` (TRAIN por segmento, holdout, capturas), fusiono o devuelvo, y reoriento. `docs/STATUS.md` lleva el estado para que lo leas al despertar.
4. A las 09:30 te espero con: puntuación en TRAIN y holdout, tiempo del ensayo FINAL, la app sobre LIVE y la lista de decisiones del día.

## 8. Límites honestos

- **El 100 % no está garantizado.** Hay segmentos inherentemente ambiguos con la información disponible (`unidentified_lookalike` frente a `ar_ref_noise`, FIFO con facturas de importe fijo, avisos que llegan días después y cuadran con dos cobros). El golden sigue `POLICIES.md` al pie de la letra, así que el techo real es alto, pero el objetivo medible es ≥ 95 en TRAIN y ≥ 90 en holdout, con precisión de pares ≥ 0,99.
- **Las sesiones no se hablan entre sí**: pasan por mí. Es más lento que un canal directo, pero evita que dos sesiones cambien el contrato a la vez.
- **El «envío» de correos es simulado** (registro en `outbox.jsonl`): los terceros son sintéticos y no hay servidor de correo. El borrador, la edición y la aprobación son reales.
- **El modelo entra poco**: documentos residuales y borradores bajo demanda. Si el residuo de documentos resulta mayor del 5 %, hay que decidir presupuesto (§9).
- **Una noche no da para las nueve pantallas con calidad igual**: el orden de §2.3 es el orden de recorte.

## 9. Decisiones que necesito de ti

1. **Aprobar este plan** y el reparto de §5 (fases, horas y recorte a las 05:30).
2. **Modelo y clave:** ¿clave de API de Anthropic para el residuo de documentos y los borradores (recomendado: Haiku, con corte duro de 2.000 llamadas por ejecución), o solo `claude -p` bajo la suscripción? ¿Presupuesto en euros para la noche y para el día?
3. **Caché de documentos versionada** en `backend/cache/` (sí: viaja entre portátiles y hace reproducible la ejecución) o fuera de git como hasta ahora.
4. **Descongelar el frontend** y sustituir la capa de datos del zip por la API (sí: a escala real no cabe en el navegador).
5. **Fusionar a `main` sin tu revisión fila a fila:** confirmas la autorización para las PRs de las dos sesiones cuando el check está en verde y la medición no baja ningún segmento. Las PRs que toquen `CONTRACT.md`, `POLICIES`-dependientes (`policy.py`) o la consola FINAL te las dejo listadas en `STATUS.md`.
6. **Modelo de las sesiones y agentes:** Sonnet para implementar, Haiku para medir; Opus solo en la orquestadora. ¿De acuerdo?
7. **Alcance de pantallas** para esta noche: las nueve de §2.3 en ese orden de recorte, o fijas ya un mínimo (p. ej. 1–4 y 9).
8. **Holdout:** corte el 2024-12-31 (seis meses de validación, como FINAL). Alternativa: 2025-03-31 (tres meses, más TRAIN para aprender las tablas de códigos).
9. **Quién envía** a LIVE durante la noche, si alguien: propongo ningún envío nocturno; el primero a las 10:00 con el fichero de respaldo.

## 10. Lo que faltaba para el 100 % y para el jurado (añadido tras revisión)

| # | Hueco | Qué se añade | Dónde |
| --- | --- | --- | --- |
| 1 | **Bucle de errores, no solo de puntuación.** Una cifra por segmento no dice *por qué* falla un movimiento | `closebooks diff <run>`: por segmento, lista los movimientos mal resueltos con la regla usada, lo que dice el golden y una **causa** asignada automáticamente (tercero no resuelto, número no encontrado, importe fuera de tolerancia, excepción equivocada, forzado, falta fila, sobra fila). Agrupa por causa y da los 20 ejemplos más representativos. Es lo que cada agente lee antes de tocar una regla | backend, P1; la orquestadora lo usa en cada hito |
| 2 | **Conformidad con la política, cláusula a cláusula.** El golden sigue `POLICIES.md` «al pie de la letra»: cada cláusula (descuento ≤ emisión + días + 3, comisión ≤ 60 EUR y ≤ 2 %, retención 1,25/1,5/10 %, FX sustituye a vacío/`SHORT_*`, FIFO, mes citado, abonos netos vacíos, `RETURNED` por importe reabierto…) se puede **verificar al 100 % en TRAIN** antes de implementarla | `backend/tests/policy_conformance/`: un test por cláusula que recorre el golden y afirma que la cláusula explica el 100 % de sus filas; si no, la cláusula está mal entendida y se corrige antes de codificarla. Es la forma barata de acercarse al 100 %: aprender la regla exacta, no aproximarla | backend, P1–P3 |
| 3 | **Consistencia global de las asignaciones.** Dos movimientos no pueden liquidar la misma partida más allá de su saldo; una regla temprana no debe robar la partida de una devolución o un duplicado posterior | `resolve` termina con una pasada de **conflictos**: por partida, suma de asignaciones ≤ saldo (salvo `DUPLICATE_PAYMENT`/`OVERPAYMENT` explícitos); en conflicto gana la regla de más certeza y la otra se reabre a la siguiente pasada o al respaldo; y una **prueba de determinismo** (dos ejecuciones, mismo CSV byte a byte) | backend, P2 |
| 4 | **Matriz de confusión de excepciones** en cada medición. Cada clase vale 2 puntos y un falso positivo en una clase pequeña cuesta cien veces más que en una grande | `closebooks score` imprime la matriz golden × enviada por clase y el coste en puntos de cada celda; umbral: ninguna clase con precisión < 0,95 entra en `main` | backend, P1 |
| 5 | **Árbitro acotado para lo ambiguo** (la extensión de C, solo si sobra tiempo): tras R4 quedan movimientos con dos o tres candidatos de igual evidencia | `rule: "ARBITER"`: Haiku recibe el texto del banco y los candidatos (número, tercero, fecha, importe, saldo) y devuelve uno o «ninguno», con caché y contador; se activa **solo si en TRAIN su precisión ≥ 0,98** sobre esos casos; si no, siguen como pregunta y `FALLBACK` | backend, P4 u evento |
| 6 | **Entregables para el jurado** desde el principio, no al final | `README.md` reescrito para el jurado (problema, cifras, arquitectura con diagrama, resultados por fase y segmento, cómo ejecutar), `docs/DEMO.md` (guion del vídeo de 5 min pantalla a pantalla, con LIVE cargada), `docs/SUBMISSION.md` (la descripción que pide la web: ideas clave, stack y modelos, qué haríamos después, equipo), y `docs/HANDOFF.md` para el equipo presencial (cómo arrancar, medir, dónde está cada cosa, cómo se envía). El repo se hace público al entregar | orquestadora, P4 |

Y tres aclaraciones de alcance frente a lo que pediste:

- **«Una factura que no casa con su pedido».** En este paquete no hay pedidos: solo `customer_po` en nuestras facturas y `our_po` en las de proveedor, y las remesas de pago. Lo que sí se puede enseñar y es real: una factura de proveedor pagada por un importe distinto al documento (`ap_partial`, `SHORT_*`), pagada dos veces (`ap_duplicate_payment`), rechazada por el banco del beneficiario (`ap_returned_transfer`), cedida a un factor, o un abono del proveedor que no se ha compensado. Cada uno abre un caso con borrador de correo al proveedor. El producto lo enseña como «factura de proveedor con incidencia», no como «factura contra pedido».
- **«Gestión de pedidos».** Se reduce a lo que los datos permiten: el pedido del cliente como referencia de pago (`customer_po` en el texto del banco y en los avisos nuevos) y el nuestro en las facturas de proveedor. No hay flujo de pedidos que procesar.
- **«Ver los resultados en Chrome en todo momento».** `just fe-dev` y `closebooks serve` quedan en `.claude/launch.json`; la sesión frontend abre la app en el navegador de su sesión en cada pantalla y adjunta capturas en la PR; tú la abres en Chrome en `http://localhost:5180` con la última ejecución de LIVE cargada.

**Sobre el 100 %.** Con 1, 2 y 3 el objetivo pasa a ser verificable cláusula a cláusula, que es lo máximo que permite el método; lo que quede fuera después de eso son casos sin información suficiente en los datos (dos facturas idénticas del mismo cliente sin referencia ni mes, un cobro de un desconocido con el importe de una factura ajena), y ahí la política dicta la respuesta (FIFO, `UNIDENTIFIED`), así que también se puede acertar. El riesgo real no es el techo, es el tiempo: por eso el orden de ataque va por puntos por hora y el recorte de las 05:30 está escrito.
