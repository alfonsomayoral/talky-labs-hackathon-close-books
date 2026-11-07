# Brief: sesión «Residuos» — los fallos que nadie cubre, con señal o sin ella

Escrito el 7 nov 2026 a las 13:40 por la sesión orquestadora. Lee antes `CLAUDE.md`, `docs/ACCURACY_PLAN.md`, `docs/JEV_PLAN.md` (incluido el piloto medido) y `docs/ANALYSIS.md` §3.3. Main está en d7cfd55 (holdout 92,70, drift 92,47, LIVE oficial 91,86 con una versión anterior).

## 1. Qué hace esta sesión y qué no

**Hace:** averiguar, con datos y por causa, dónde está la respuesta de los fallos que la sesión de Exactitud ha medido como «sin señal en el texto», y convertir en regla solo lo que tenga señal en alguna fuente y pase la puerta. Trabaja con varios agentes en paralelo desde el primer minuto.

**No hace:** escribir en `backend/src/closebooks/rules/`, `policy.py`, `resolve.py` ni `state.py` mientras la sesión de Exactitud esté activa (hasta las 17:00, congelación de reglas). Esta sesión produce **diagnóstico medido y reglas candidatas en una rama propia con tests**, y la orquestadora decide si pasan a Exactitud antes de la congelación o quedan para después del evento. Nunca envía nada a la clasificación. Nunca modifica datos de entrada. Nunca ajusta un umbral mirando el golden.

**Alineación con Exactitud:** mismo objetivo (generalizar, no la nota), misma puerta (§4), mismos ficheros prohibidos. Cualquier hallazgo se comunica a la orquestadora, no a Exactitud directamente.

## 2. Los residuos, medidos en holdout por Exactitud (13:00)

| Residuo | Líneas | Lo que ya se sabe | Lo que esta sesión tiene que responder |
| --- | --- | --- | --- |
| R1 `ar_ref_noise` «sin cita, conjunto disperso» | 2.282 | El texto no cita nada; mediana de 38 facturas abiertas candidatas; el importe es la suma exacta de las partidas del golden en el 100 % de los casos (ANALYSIS §3.3); el 21,8 % del segmento tiene aviso de remesa y el 11,2 % fichero de detalle | ¿Cuántas de las 2.282 tienen un aviso, fichero de detalle o PDF que **sí** lista las partidas y que el pipeline no enlaza al cobro (aviso que llega días después, pagador distinto del cliente, importe total distinto por gastos)? ¿Qué convención sigue el golden en las que no tienen documento: más antiguas, mismo mes, mismo vencimiento, misma remesa del cliente? Medirlo, no suponerlo |
| R2 `ar_ref_noise` «varios números, faltan los demás» | 646 | Las partidas que faltan no dejan rastro en el texto | ¿Están en un aviso? ¿Son las siguientes consecutivas a las citadas (texto cortado a 38)? ¿Comparten vencimiento con las citadas? |
| R3 `ar_partial` reparto | ~930 en LIVE | Ninguna hipótesis de reparto supera el 55 %; parciales sin cita dan 129 falsos | Medir el reparto por **tipo de parcial**: con aviso, con PDF de plan, con texto «a cuenta / parcial / resto», sin nada. Puede que una convención gane en un subtipo y no en el total |
| R4 `ar_1toN_credit_note` | ~1.170 en LIVE | `REF-COMPLETED` cubre un abono exacto; varios abonos o abono + descuento no | ¿Cuántos tienen el abono citado en el texto o en el aviso? ¿Cuántos son «factura − abono» con `related_document` del abono apuntando a la factura? Exactitud midió que `related_document` «apenas añade», sin separar notas nuevas de ya correctas: separarlo |
| R5 `ar_n_to_m` | ~1.220 en LIVE | `_oldest_first` reparte por antigüedad y el golden de otra forma | Medir en TRAIN qué hace el golden cuando un cobro no cubre varias facturas: ¿reparte proporcional, cierra las citadas y deja parcial la última, cierra por vencimiento? Tabla por hipótesis con % de acierto |
| R6 Tercero no encontrado, nombre tocado | 1.329 | Solo 18 exactas por IDF, 0 falsos; matriz/grupo (247) lo hace Exactitud ahora; agencia sin nombre (115) | ¿Está el tercero en el IBAN del ordenante, en un aviso, en el fichero de detalle o en un cobro anterior con la misma cuenta ordenante? Jev J2 falló por nombre; probar **solo con candidatos que vengan de esas fuentes**, no del nombre |

## 3. Método: varios agentes desde el primer minuto

Lanza en paralelo, cada uno sobre ejecuciones ya generadas en `runs/acc-*` y `runs/live-*` y el golden de TRAIN/holdout, sin ejecuciones pesadas (la máquina es de Exactitud; cualquier `closebooks run` se pide a la orquestadora):

1. **Agente «fuentes» (Sonnet):** para cada línea de R1, R2 y R4 del holdout, busca sus partidas del golden en avisos (csv/txt/xlsx/pdf como texto), ficheros de detalle y PDFs de la fase, con `scripts/analysis/03_sources.py` como base. Salida: tabla «residuo × fuente donde está la respuesta × por qué el pipeline no la enlazó».
2. **Agente «convención» (Sonnet):** para R1 sin documento, R3 y R5, prueba hipótesis de convención del golden sobre TRAIN (más antigua primero, vencimiento, mismo mes de emisión, misma serie, consecutivas) y mide el % de acierto por hipótesis **y por subtipo**. Umbral de interés: ≥ 0,98 de precisión en algún subtipo con 0 falsos sobre `unidentified`/`lookalike`.
3. **Agente «tercero» (Haiku):** para R6, cuenta cuántas líneas tienen IBAN de ordenante conocido en un cobro anterior ya casado, aviso con pagador, o fichero de detalle; y cuántas se resolverían con cero falsos por cada fuente.
4. **Agente «Jev» (Sonnet, tope 1 $, solo si 1–3 encuentran candidatos de fuente):** con candidatos que vengan de documentos o de cobros anteriores (nunca del nombre solo), `Choice` + «ninguno» al umbral 0,8 fijado ya; precisión contra el golden ≥ 0,98 o no entra. La clave está en `backend/.env`; el cliente, en la rama `KPI-9_jev-client`.

Tú integras: a la hora de empezar, mándame la tabla 1 aunque esté parcial; a las dos horas, hipótesis con números; después, reglas candidatas solo donde haya señal, en la rama `KPI-10_residuals`, **tocando solo ficheros nuevos** (`rules/residuals.py` + tests) o `documents/` si la causa es un enlace de aviso que falla, con la regla desconectada del `PASSES` hasta que la orquestadora lo apruebe.

## 4. Puerta, la misma que Exactitud

Holdout **y** drift sin ningún segmento −0,002; precisión de pares ≥ 0,995; `unidentified` y `unidentified_lookalike` en 1,000; clases DUPLICATE y OVERPAYMENT ≥ 0,95 o apagadas, el resto sin bajar más de 0,002; CSV determinista; RSS ≤ 7,5 GB; ≤ 150 s. Con Jev, además: CSV idéntico con Jev apagado, cold ≤ +30 s. Cada regla candidata con su línea «por qué generaliza»: deriva de POLICIES o de un comportamiento contable, nunca de un patrón visto.

## 5. Entregables y horas

- 14:40: tabla «dónde está la respuesta» de R1, R2, R4 y R6, con números.
- 15:40: hipótesis de convención medidas para R1 sin documento, R3 y R5.
- 16:30: reglas candidatas con tests en `KPI-10_residuals`, desconectadas, con la estimación de líneas y falsos por regla; y `docs/RESIDUALS.md` con todo lo medido, incluido lo que no tiene señal.
- Lo que pase la puerta antes de las 16:45 se lo paso a Exactitud para la PR final; lo demás queda documentado para después del evento.

## 6. Límites de máquina

24 GB de RAM; una ejecución pesada en toda la máquina a la vez y es de Exactitud. Tus agentes leen ficheros ya generados. Si necesitas una ejecución de holdout para medir una regla candidata, pídesela a la orquestadora con el nombre de la rama; te dirá cuándo.
