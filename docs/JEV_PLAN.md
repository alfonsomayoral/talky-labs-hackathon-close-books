# Plan: juicios de Jev en el pipeline, con Claude solo para excepciones

Estado: **piloto medido, FINAL sin Jev (§10)**; en ejecución desde las 13:20 (autorización de Alfonso para enviar datos del paquete a TypeSafe; clave en `backend/.env`, fuera del repo). Lectura aplicada de CLAUDE.md §5: Jev extrae qué número cita el texto, como un parser; el importe y la partida abierta deciden la casación. Escrito el 7 nov 2026 a las 12:10, con el backend en holdout 91,77 (main c44e505) y la sesión de Exactitud a mitad de su plan. Nada de esto entra hoy antes de la congelación de reglas de las 17:00 salvo decisión expresa; el piloto de §6 es lo único que cabe en una hora.

## 1. Objetivo

Subir la nota mejorando el pipeline, no aprendiendo particularidades de TRAIN o LIVE, y sin alargar la ejecución de forma apreciable. Jev entra donde el código ya tiene candidatos pero no tiene criterio semántico para elegir entre ellos; Claude (Haiku, Sonnet si hace falta) solo donde hay que leer un documento entero que ningún parser cierra. Presupuesto: 100 $ en total; objetivo de gasto por debajo de 40 $.

## 2. Principios, los mismos que CLAUDE.md §5

1. **Las reglas deciden; los modelos solo extraen.** Jev nunca casa un movimiento ni elige una categoría. Responde a «¿cuál de estos trozos es la referencia?», «¿cuál de estos nombres cita el texto?», «¿este motivo es descuento, retención o disputa?». La regla de siempre valida la respuesta (la referencia existe entre las partidas abiertas del tercero, el importe cuadra) y decide.
2. **El código encuentra los candidatos; Jev elige entre ellos o dice «ninguno».** Jev no escribe valores: cada pregunta es un `Choice` con los candidatos exactos más la opción «ninguno», o un `Noul` (sí/no con probabilidad). Lo elegido se copia tal cual del texto.
3. **Sin modelo, el resultado es el de hoy.** Si no hay clave, no hay red, se agota el presupuesto o la respuesta no pasa la validación, la línea sigue por el camino determinista actual. Una ejecución con la API apagada tiene que dar la misma nota que main.
4. **Caché por hash, versionada.** Clave = sha256(estado, preguntas, versión de la pregunta, modelo). Vive en `backend/cache/jev/` como la caché del modelo (CLAUDE.md §5). La segunda ejecución de una fase no llama a nada; FINAL llamará solo por sus líneas nuevas.
5. **Nada aprendido de los datos.** Ninguna lista de nombres, códigos ni importes. Los umbrales de probabilidad se fijan antes de mirar el golden y se validan después con la misma puerta que las reglas (§5).
6. **Cada fila de la entrega lleva su evidencia** (CONTRACT.md): la regla que la produjo cita la pregunta, los candidatos, la elección y su probabilidad, para que el panel de caso lo enseñe.

## 3. Dónde entra Jev y dónde no

Medido en `runs/perf-holdout-a` (holdout, 200 k movimientos) y en `docs/ACCURACY_PLAN.md`.

| # | Paso del pipeline | Hoy | Candidatos (código) | Pregunta a Jev | Validación (regla) | Volumen por fase | Ganancia esperada |
| --- | --- | --- | --- | --- | --- | --- | --- |
| J1 | Referencia en texto bancario sucio (`REF-TEXT`, `REF-SUBSET`, `REF-COMPLETED`) | Gramática de números por sociedad; falla con números cortados a 38 caracteres, sufijos, ruido | Todos los trozos del texto que parecen número de documento, con o sin prefijo o ceros, y los que completan una partida abierta | `Choice`: «¿cuál de estos trozos es el documento que cita este pago?» + «ninguno»; `Noul`: «¿cita más de un documento?» | El elegido es una partida abierta del tercero (o del grupo nombrado en la regla) y el importe cuadra como hoy | Solo líneas que llegan al motor sin referencia resuelta y con ≥ 2 candidatos: ≤ 20 k [Inferencia] | `ar_ref_noise` (42 k líneas, ~4.400 fallos en LIVE) y `ar_1toN_text` (~700) |
| J2 | Tercero incierto (`PartyIndex.find` con `certain=False`, homónimos) | Prefijo de 8 caracteres y formas jurídicas; se abstiene con dos candidatos | Los candidatos que ya da el índice, con nombre completo, país e IBAN | `Choice`: «¿a cuál de estos terceros se refiere este movimiento?» + «ninguno» | La regla de importe decide después como hoy; si Jev reparte la probabilidad, pregunta a una persona | 751 inciertos + empates por homónimos (3.582 líneas con tercero seguro tienen homónimo) | Parte de los 1.875 fallbacks con tercero no resuelto |
| J3 | Motivo de deducción en avisos (`policy._deducted`) | Dos listas fijas de palabras (`DISCOUNT_WORDS`, `WITHHOLDING_WORDS`) en seis idiomas; lo demás es disputa | El texto del motivo y el contexto del aviso (cliente, país, importes) | `Choice`: descuento por pronto pago, retención fiscal, disputa o pago corto, gastos bancarios, ninguno | El importe tiene que cuadrar con la tasa de retención o el descuento del maestro; si no, `PARTIAL` como hoy | Filas de aviso con motivo no vacío: cientos, no miles | Quita dos listas fijas, que es lo que no generaliza a un idioma o cliente nuevo; `ar_short_discount`, `ar_short_dispute` |
| J4 | Categoría de una línea sin partida cuando el código del banco no es puro (`CAT-TEXT`) | 20 expresiones regulares | Texto, código, signo e importe | `Choice` entre las 21 categorías + «ninguna» | Umbral de probabilidad fijado de antemano; por debajo, `FALLBACK` | ≤ 16 k líneas (categoría sin partida: 16.552) | Menor. **Aquí el modelo decide más de lo que extrae**: entra solo si la precisión medida por categoría es ≥ 0,95; si no, fuera |

**Donde Jev no entra:** casar importes (subconjuntos, ventanas, reparto), excepciones (`DUPLICATE`, `OVERPAYMENT`, `PARTIAL`), nada que dependa de aritmética. Eso es de las reglas y ya está en el plan de Exactitud.

**Claude, solo excepciones:**

| # | Paso | Modelo | Cuándo | Validación | Tope |
| --- | --- | --- | --- | --- | --- |
| C1 | Avisos (csv, xlsx, txt, pdf) que `_columns` o el parser de tabla rechazan | Haiku, salida JSON por fila (número, bruto, deducción, motivo, pagado) | Solo tras el rechazo del parser determinista y tras la detección de columnas por contenido que Exactitud adelanta hoy | Las filas suman el pagado; cada número existe entre las partidas de la fase; si no, se descarta el aviso entero | 3.000 documentos y 20 $ por fase; caché por hash del fichero |
| C2 | Producto: borrador de reclamación con el contexto del caso, explicación en lenguaje natural | Haiku | Bajo demanda desde la plataforma, nunca en la ejecución | No puntúa | 10 $ |

## 4. Cómo se integra sin alargar la ejecución

Lo que se sabe de Jev (docs de TypeSafe, 7 nov 2026): 0,042 $ por millón de tokens de entrada, salida gratis; 64 k tokens por petición y 32 k por pregunta; varias preguntas sobre el mismo estado en una petición, y una petición de 13 preguntas tardó 0,24 s en su ejemplo. No publican latencia ni límites de tasa: **se miden en el piloto**.

1. **Una etapa nueva, `enrich`, entre `rules` y `resolve`.** Recoge las líneas que van a llegar al motor sin resolver (las que ninguna pasada R1/R2 reclamó), calcula en código sus candidatos para J1 y J2, y hace las preguntas. El motor lee las respuestas como hechos más, igual que lee los avisos. J3 va dentro del parser de avisos, en `documents`. Ninguna regla cambia de sitio.
2. **Lotes.** Una petición lleva muchas líneas en `state` (una lista) y una pregunta por línea referenciando `lines[i]`, hasta ~150 líneas por petición (~300 tokens por línea). 20 k líneas son ~140 peticiones.
3. **Concurrencia.** Las peticiones son de red, no de CPU: 8 en paralelo con el cliente asíncrono, reintentos con espera exponencial, sin tocar el pool de procesos de `documents`.
4. **Presupuesto de tiempo:** cold ≤ +30 s en holdout (hoy 138 s), warm (caché llena) +0 s. Si el piloto mide más, se reduce el volumen con las puertas de §3 (solo líneas con ≥ 2 candidatos) antes que tocar la concurrencia.
5. **Guardián:** variables `TYPESAFE_API_KEY`, `ANTHROPIC_API_KEY`, `CB_MODEL_BUDGET_USD`; contador de tokens por ejecución en `run.json` (`modelCostUsd`, ya existe la casilla en el Resumen); al tope, se apagan las llamadas y se anota.
6. **FINAL.** Ensayo de LIVE con el código congelado antes de las 18:00 para llenar las cachés (PDF y Jev). FINAL llama solo por sus líneas nuevas: con 200 k movimientos y las puertas de §3, menos de un minuto cold [Inferencia], y si falla la red, la nota de hoy.

## 5. Puerta de entrada, la misma que para las reglas

Cada bloque (J1, J2, J3, J4, C1) es una PR con:

- holdout **y** drift: ningún segmento baja más de 0,002; precisión de pares ≥ 0,995; `unidentified` y `lookalike` en 1,000; las clases con la puerta por clase de `ACCURACY_PLAN.md`;
- **ejecución con la API apagada y caché vacía: nota idéntica a main** (cmp del CSV);
- ejecución cold y warm con tiempos y RSS; cold ≤ +30 s;
- precisión de las respuestas de Jev medida contra el golden de holdout, por pregunta, con el umbral fijado antes;
- las tres pruebas de robustez (sin fuga, sin bancos, layout inventado) repetidas;
- línea «Por qué generaliza» en el cuerpo.

## 6. Piloto de una hora, para decidir con datos y no con estimaciones

Sin tocar el pipeline. Un script en `scripts/analysis/06_jev_pilot.py`:

1. Toma 2.000 líneas de holdout de `ar_ref_noise` que hoy fallan, con sus candidatos calculados como en J1, y 500 líneas con tercero incierto como en J2.
2. Hace las preguntas en lotes de 150 y mide: latencia por petición, tokens, coste, y precisión y cobertura contra el golden por umbral de probabilidad (0,6, 0,7, 0,8, 0,9).
3. Decide: J1 entra si a algún umbral la precisión es ≥ 0,98 con cobertura ≥ 30 % de los fallos; J2 si ≥ 0,98 y ≥ 50 %. Si no, se documenta y se descarta.
4. Coste del piloto: < 1 $. Tiempo: 1 h de una sesión, sin carga en la máquina.

## 7. Orden y coste

| Orden | Bloque | Esfuerzo | Coste por fase | Condición |
| --- | --- | --- | --- | --- |
| 0 | Piloto (§6) | 1 h | < 1 $ | Clave de TypeSafe en variable de entorno |
| 1 | Proveedor común: cliente, lotes, caché, guardián, tests con respuestas grabadas | 2 h | 0 | No toca reglas; puede ir en paralelo a Exactitud |
| 2 | J1 referencia | 2 h | ~1 $ | Tras las PR de Exactitud en `party_amount.py` |
| 3 | J3 motivo de deducción | 1 h | < 1 $ | Tras la PR de columnas por contenido |
| 4 | J2 tercero | 1 h | < 1 $ | Tras la PR de homónimos |
| 5 | C1 avisos sin parser | 2 h | ≤ 20 $ | Reutiliza el proveedor acotado de la PR 68, con API de pago |
| 6 | J4 categoría, C2 producto | si sobra | ≤ 11 $ | Solo con precisión ≥ 0,95 medida |

Total previsto: < 40 $ de los 100 $. Ninguno de los bloques 2–6 cabe antes de la congelación de hoy a las 17:00 sin quitar tiempo a Exactitud; el piloto y el proveedor sí, en la sesión de backend parada, sin tocar ficheros de Exactitud.

## 8. Riesgos y cómo se acotan

- **Jev acierta menos de lo esperado en referencias cortadas.** Lo dice el piloto antes de escribir nada.
- **Latencia o límites de tasa que alargan la ejecución.** Puertas de volumen, lotes, caché; cold ≤ +30 s o el bloque no entra.
- **Que FINAL dependa de la red a las 18:00.** Cachés llenas con el ensayo de LIVE; si falla, el resultado de hoy.
- **Que el modelo decida en vez de extraer.** J4 es el único bloque en esa frontera y entra solo con precisión ≥ 0,95; los demás eligen entre candidatos que el código ya validó.
- **Conflictos con Exactitud.** El proveedor no toca sus ficheros; los enganches (tres puntos: `party_amount` referencias, `parties.find` inciertos, `advices` motivo) se hacen después de sus PR.

## 9. Decisiones pendientes de Alfonso

1. Si se hace el piloto hoy (1 h de la sesión de backend parada, sin carga) o queda para después del hackathon.
2. Clave de TypeSafe: ¿existe ya? Va en `TYPESAFE_API_KEY`, nunca en el repo.
3. Si C1 (Claude en avisos sin parser) se prepara como seguro para FINAL aunque Jev quede para después, dado el riesgo de 8 puntos medido con un layout inventado.

## 10. Piloto, medido (7 nov, API real, unos 0,035 $)

**Decisión:** FINAL va sin Jev. J1, J2 y J3 no pasan la puerta fijada antes de medir (precisión ≥ 0,98 al umbral 0,8 y, en J3, mejorar a las listas). El umbral no se movió después. El cliente queda en la rama `KPI-9_jev-client` (commit 019a954), sin fusionar: con tests y cliente falso, sin enganchar al pipeline.

| Medida a 0,8 | J1 documento citado | J2 tercero | J3 motivo de deducción |
| --- | --- | --- | --- |
| Precisión | **0,942** | **0,516** | 1,000 |
| Mejor precisión en cualquier umbral | 0,959 (a 0,6) | 0,680 (a 0,9) | 1,000 |
| Cobertura | 10,4 % de 2.500 fallos | 13,9 % de 570 fallos | 84,5 % de 14.325 líneas |
| Falsos en `unidentified` | 0, con solo 1 línea evaluable: no concluye | **10 de 300** | No aplica |
| Techo | Bajo: 78 % de los fallos no cita nada legible | 72 % tiene al tercero entre los candidatos | **0 o 1 de 1.161 fallos** |

**Por qué falla, según los ejemplos:**

- **J1:** Jev lee bien el número que cita el texto (p ≥ 0,97), pero el golden liquida otra partida: el ruido está en el dato, no en la lectura. En `ar_ref_noise` la precisión es 0,667. El 1,000 de `ar_1toN_text` (229 de 229) es casi trivial: el motor ya cita esos documentos.
- **J2:** falla en homónimos (misma razón social en varios terceros) y elige tercero en movimientos sin partida, justo el síntoma de forzar una casación. El IBAN no se envió, así que no se mide si ayudaría.
- **J3:** solo hay 8 motivos distintos, los mismos en TRAIN y holdout, y las listas aciertan los 14.325. Jev no reconoce la abreviatura «RET» (responde «none»). Casi todos los fallos de esos segmentos son de casación, no del motivo.

**Medidas de API:** latencia mediana 0,6 s por petición (p95 0,7 s). Los lotes de 150 líneas no caben: la API devuelve `max_tokens_exceeded`; 60 líneas con dos preguntas y 100 con una sí.

**Sin medir:** otros prompts, la cobertura del `Noul`, el impacto en la nota, y motivos de FINAL ausentes de TRAIN. Un motivo nuevo sería hoy `SHORT_DISPUTE`, como manda `_deducted`.

### 10.1 Piloto J4, categoría sin tabla (7 nov, 16:00, API real, 0,245 $)

**Decisión: J4 no se integra.** Con el vocabulario de hoy no mejora al fallback en ninguna categoría y categoriza el 3,7 % de los cobros UNIDENTIFIED, cuando la puerta exige 0. El código queda en la rama `KPI-11_categories-judged`, sin PR y sin enganchar.

Banco PENA de holdout, sin código ni tabla: 3.000 líneas con semilla fija de 5.656, 19 categorías más UNIDENTIFIED. Umbral 0,8, fijado antes de medir. Definiciones de `categories.csv` y POLICIES §4, sin tocar. El lote de 60 es el diseño fijado; **el lote de 1 es post-hoc**, añadido porque el de 60 parecía un artefacto.

| Cifras reponderadas a la población | Precisión | Cobertura | Exactitud, con fallback en el resto |
| --- | --- | --- | --- |
| Fallback sin tabla (TEXT_RULES + BANK_FEES) | 0,999 | 0,999 | 0,999 |
| Jev, lote de 60 | 0,872 | 0,294 | 0,956 |
| Jev, lote de 1 (post-hoc) | 0,965 | 0,829 | 0,970 |

| Falsos de Jev | Lote de 1 |
| --- | --- |
| `CASH_POOL` como `INTERNAL_TRANSFER` («TRASPASO PROPIO») | 124 |
| `CUSTOMER_REFUND` como `SUPPLIER_REFUND` | 21 |
| `INTERCOMPANY` como `LOAN_REPAYMENT` | 10 |
| `BANK_REVERSAL` como `SOCIAL_SECURITY` | 9 |
| Cobros UNIDENTIFIED categorizados (de 300; el fallback, 0) | 11, sobre todo «ANTICIPO» como `CUSTOMER_ADVANCE` |

**Por qué retomarlo después del evento.** El fallback sale favorecido: TEXT_RULES salió de TRAIN y PENA comparte ese vocabulario; se quitó la tabla, no el vocabulario. Contrafactual calculado con el texto de PENA, sin TEXT_RULES, como vocabulario nuevo: solo respaldo ≤ 0,748; Jev más respaldo 0,772 (lote de 60) y 0,908 (lote de 1), con ese 3,7 % de falsos. No se ha medido en un banco nuevo real, ni en FINAL ni en ZA01.

**Quien lo retome, en lote de 1.** Referenciar `lines[i]` en lotes grandes degrada a Jev: cobertura 0,26 frente a 0,77 y precisión 0,835 frente a 0,932 en la muestra. J1 y J2 (§10) se midieron en lotes, así que pudieron medir a la baja [Inferencia]. Coste del lote de 1: 0,15 s de mediana por petición; unos 5 min en frío para 16.000 líneas con 8 en paralelo [Inferencia], frente al tope de +30 s de §4.

