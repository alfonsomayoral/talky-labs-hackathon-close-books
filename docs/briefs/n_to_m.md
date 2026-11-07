# Brief: sesión «N a M» — cobros que pagan parte de varias facturas

Escrito el 7 nov 2026 a las 13:40 por la sesión orquestadora («Orquestador Close the Books», visible con `ListAgents`). Lee antes `CLAUDE.md`, `docs/ACCURACY_PLAN.md` (la puerta y la tabla del día), `docs/JEV_PLAN.md` (los tres pilotos de Jev medidos y descartados) y `docs/ANALYSIS.md` §3.3 y §4.3. Main está en 86bce6e: holdout 92,76, drift 92,52, LIVE oficial 92,01.

## 1. El problema, con números

Segmento `ar_n_to_m` del evaluador: un cobro de un cliente que **no cubre todas sus facturas abiertas**, y el golden reparte el dinero entre varias, dejando alguna parcial. En LIVE son 1.800 movimientos con exactitud 0,325: unos 1.200 fallan. Es el segundo segmento por errores del día después de las referencias ruidosas, y el único grande que no se ha movido en toda la jornada (0,324 esta mañana, 0,325 ahora).

Qué hace hoy el pipeline (`backend/src/closebooks/policy.py`):

- `allocate()` recibe el efectivo y las partidas que la regla propuso, y `_explain()` intenta explicarlo: cuadre exacto, sobrepago, descuento, retención, gastos bancarios; si nada cuadra, `_oldest_first()` reparte el efectivo por fecha de emisión y marca `PARTIAL` la última.
- Las partidas que llegan a `allocate` las eligen las reglas de `rules/party_amount.py`: `_unique_subset`, `_consecutive` (ventana de facturas consecutivas con `MAX_CHANCE`), `_short_paid`, y las citas del texto o del aviso.

Qué se sabe ya, medido por la sesión de Exactitud y por el análisis de la mañana:

| Hecho | Fuente |
| --- | --- |
| Ninguna hipótesis de reparto **sobre el total del segmento** supera el 55 % de acierto (más antigua primero, proporcional, por vencimiento) | Exactitud, 13:05, con saldos del golden |
| Los parciales sin cita dan 129 falsos si se fuerzan: se quedaron en fallback | PR 90 |
| En el segmento de referencias ruidosas, el 21,8 % de los movimientos tiene un aviso de remesa y el 11,2 % un fichero de detalle; el importe es la suma exacta de las partidas del golden en el 100 % | ANALYSIS §3.3 |
| El texto bancario casi nunca cita las facturas que faltan; Jev leyendo texto no ayuda (precisión 0,942, cobertura 10 %) | JEV_PLAN, piloto |
| Un abono del cliente puede estar netado dentro del cobro (`ar_1toN_credit_note`, 0,65) | ACCURACY_PLAN |

Lo que **no** se sabe y es la clave: qué hace el golden **por subtipo**. Una regla que acierta el 55 % en el total puede acertar el 99 % en un subtipo y el 10 % en otro. El trabajo es encontrar los subtipos con señal y codificar solo esos.

## 2. Objetivo y lo que no se hace

Subir `ar_n_to_m` (y lo que arrastra: `ar_partial`, `ar_1toN_credit_note`) **solo con reglas que generalicen**: derivadas de POLICIES, de un documento que lo diga o de una convención contable que se sostenga en holdout **y** en drift. Nunca una heurística que acierte en TRAIN porque sí. Nunca un umbral ajustado mirando el golden: se fija antes y se documenta. Si un subtipo no tiene señal, se queda en fallback con pregunta a una persona, y se escribe cuántas líneas son y por qué.

Jev: queda **fuera de este bloque salvo una excepción**. Es un problema de aritmética y convención, y Jev no suma. La única entrada posible es como desempate semántico, con `Noul` sobre el texto («¿menciona pago parcial o a cuenta?», «¿menciona un abono?»), **solo** entre dos explicaciones que ya cuadran al céntimo, y solo si aparecen tales casos; cliente ya escrito en la rama `KPI-9_jev-client`, clave en `backend/.env`, umbral 0,8 fijado. Si aparecen avisos en formatos que ningún parser lee, eso es extracción de documentos (Haiku, bloque C1 de JEV_PLAN) y se comunica a la orquestadora antes de hacer nada.

## 3. Plan de trabajo, con agentes Opus en paralelo desde el primer minuto

Lanza los tres agentes a la vez (modelo Opus), cada uno sobre ejecuciones ya generadas (`runs/acc-*`, `runs/live-*`) y el golden de TRAIN y holdout. Ninguno lanza `closebooks run`: la máquina (24 GB) admite una ejecución pesada a la vez y es de la sesión de Exactitud; las ejecuciones las pide la sesión a la orquestadora (§6).

**Agente 1, «subtipos» (Opus).** Para cada movimiento `ar_n_to_m` del holdout que falla, clasifícalo y mide qué hace el golden en cada clase:

| Subtipo | Qué mirar | Hipótesis a medir (acierto por hipótesis, 0 falsos) |
| --- | --- | --- |
| Con aviso de remesa enlazable (mismo cliente o pagador del grupo, total igual o igual más gastos, fecha ± días) | El aviso trae importe por factura | ¿El pipeline no lo enlazó? ¿Por qué (llega después, pagador ≠ cliente, total distinto, formato)? |
| Con fichero de detalle o remesa | Idem | Idem |
| Con PDF de plan de pagos o de cuotas | Cuota k/n | ¿Cierra la cuota y deja el resto? |
| Con abono abierto del cliente | Cobro = facturas − abono, con alguna parcial | ¿El golden neta el abono primero? |
| Texto con «a cuenta», «parcial», «resto», «saldo», «acompte», «Teilzahlung», «acconto», «parcial» | Pago parcial declarado | ¿Qué factura: la citada, la más antigua, la del importe más cercano? |
| Sin documento ni texto | Solo importes y fechas | Más antigua primero con última parcial; por vencimiento; la de importe más cercano por debajo; consecutivas por emisión; cierra todas menos la mayor |

Salida a la hora: tabla subtipo × líneas × hipótesis ganadora × acierto × falsos, en `docs/N_TO_M.md`. **Umbral de interés fijado ahora:** un subtipo entra si alguna hipótesis acierta ≥ 0,98 de sus líneas en holdout con 0 falsos sobre `unidentified` y `unidentified_lookalike`; lo demás no.

**Agente 2, «enlace de avisos» (Opus).** Para los subtipos con documento, lee `documents/advices.py` y `rules/advices.py` y averigua con datos por qué el aviso o el detalle no se enlazó al cobro: ventana de fechas, pagador del grupo, total con gastos, número sin prefijo. Propone el cambio mínimo de enlace, con test, en una rama propia. Esto es lo que más líneas puede dar con menos riesgo: el documento dice la respuesta.

**Agente 3, «reglas» (Opus), cuando 1 y 2 tengan resultados.** Escribe en la rama `KPI-11_n_to_m` las reglas de los subtipos que pasen el umbral, con TDD: un test por comportamiento con un caso inventado (no líneas del golden), que falla antes y pasa después; reparto en `policy._explain` o `_oldest_first` solo para el subtipo identificado, y nunca cambiando el comportamiento de los demás. Cada regla con docstring «por qué generaliza» (POLICIES, documento o convención contable) y evidencia en la fila (`sources`, `candidates`) para que el panel de caso la enseñe.

La sesión integra, mide (§6) y abre PRs pequeñas, una por subtipo, en cuanto cada una pase la puerta; no espera a tener todo.

## 4. Puerta, la misma que todas las PR de hoy

Holdout **y** holdout-drift: ningún segmento baja más de 0,002; precisión de pares ≥ 0,995; `unidentified` y `unidentified_lookalike` en 1,000; `DUPLICATE_PAYMENT` y `OVERPAYMENT` ≥ 0,95 de precisión o apagadas, el resto de clases sin bajar más de 0,002; CSV determinista; RSS ≤ 7,5 GB; ≤ 150 s. Medir con `just be-score <run> --compare <run-main>` y `just be-diff <run> --segment ar_n_to_m`. Una PR que sube `ar_n_to_m` y baja `ar_partial` o `ar_same_amount_fifo` no está terminada.

## 5. Coordinación: qué ficheros y cuándo

- La sesión de Exactitud escribe ahora mismo en `rules/party_amount.py`, `rules/parties.py` y quizá `policy.py` (cuatro reglas: confirming parcial, reembolso de proveedor, fábrica de pagos, última cuota) hasta ~14:30, y abre su PR final de robustez a las 15:30. **No toques `party_amount.py` ni `parties.py` hasta que la orquestadora te diga que esas PR están en main**; `policy.py` solo en `_explain`/`_oldest_first`, y rebasa sobre main antes de cada PR.
- Rama: `KPI-11_n_to_m` sobre main. Commits `[KPI-11] type: subject`, sin atribución a IA. `git push` y PR solo cuando la orquestadora lo pida; ella fusiona.
- Nunca se modifica `db/`, nunca se envía nada a la clasificación, la caché de modelos no se toca.
- Congelación de reglas a las **17:00**. Lo que no haya pasado la puerta a las 16:30 queda documentado en `docs/N_TO_M.md` para después del evento, con cifras.

## 6. Máquina y ejecuciones

24 GB de RAM; **una** ejecución pesada en toda la máquina a la vez (5,5–6,5 GB y 2,5 min cada una), y por defecto es de Exactitud. Para medir una regla: pide a la orquestadora un hueco por `SendMessage` con el nombre de la rama y el número de ejecuciones (holdout primero; drift solo si holdout pasa). Mientras esperas, sigue escribiendo. Los agentes solo leen ficheros ya generados; pytest completo también se pide.

## 7. Comunicación con la orquestadora

Por `SendMessage` a «Orquestador Close the Books» (busca el nombre con `ListAgents`). Mensajes cortos, con la primera línea autocontenida. Manda: (1) a la hora, la tabla de subtipos; (2) cada hipótesis que pase o falle el umbral, con números; (3) cada petición de hueco; (4) cada PR lista con la tabla antes/después por segmento en holdout y drift. La orquestadora responde con decisiones, huecos y lo que haya cambiado en main. Si una decisión no es tuya (tocar un fichero de Exactitud, un umbral, Jev), pregunta antes, no después.

## 8. Qué significa terminado

- `docs/N_TO_M.md` con la tabla de subtipos, las hipótesis medidas, lo que entra y lo que queda fuera con cifras.
- Una PR por subtipo que pase la puerta, fusionada antes de las 17:00, con test, docstring y evidencia.
- Expectativa honesta: si los subtipos con documento son la mitad de los fallos y el enlace se arregla, `ar_n_to_m` puede pasar de 0,33 a 0,6–0,7 y arrastrar `ar_partial`; eso son 0,3–0,6 puntos en LIVE. Si no hay señal, el entregable es saberlo con números.
