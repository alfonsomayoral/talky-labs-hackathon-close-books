# Brief: sesión «Auditoría por ejemplos» — lo que los ejemplos oficiales dicen y nuestras reglas no hacen

Escrito el 7 nov 2026 a las 14:20 por la sesión orquestadora («Orquestador Close the Books», visible con `ListAgents`). Lee antes `CLAUDE.md`, `docs/ACCURACY_PLAN.md`, `docs/briefs/n_to_m.md` (método y límites, iguales aquí) y la página oficial de ejemplos, que se lee con el navegador porque se renderiza con JavaScript: https://hackathon.usetalky.com/ejemplos (36 casos resueltos, uno por segmento, con el movimiento, las candidatas, el documento que decide, las filas del CSV, el «por qué» y la «trampa habitual»). Main está en 7571009+: holdout 92,76, drift 92,52, LIVE oficial 92,01.

## 1. Qué hace esta sesión

Para cada segmento débil de LIVE, comparar la lógica que el ejemplo oficial declara con lo que hace nuestro motor sobre los fallos de holdout, y encontrar la diferencia concreta. El ejemplo es la fuente: dice qué documento decide y cuál es la trampa. Si nuestro motor cae en la trampa o no lee el documento que el ejemplo nombra, eso es una regla que generaliza por construcción, porque está escrita por el reto. Si el ejemplo no explica el fallo, se mide y se documenta sin inventar.

Trabaja con tres agentes Opus en paralelo desde el primer minuto sobre ejecuciones ya generadas (`runs/acc-group-holdout` es la base de holdout, 92,76; `runs/live-amount-c` la LIVE enviada) y el golden de holdout. Ninguna ejecución pesada sin pedir hueco a la orquestadora (24 GB, una a la vez, por defecto de Exactitud). Reglas candidatas en la rama `KPI-12_segments_audit`, en ficheros nuevos o con cambios mínimos, **sin tocar `rules/party_amount.py`, `rules/parties.py` ni `resolve.py` hasta que la orquestadora confirme que las PR de Exactitud y N a M están en main** (previsto ~14:45). Nunca `db/`, nunca envíos. Congelación de reglas a las 17:00.

## 2. Segmentos a auditar, por errores en LIVE, y lo que dice su ejemplo

| Segmento | LIVE | Errores | Lo que el ejemplo dice que decide | Sospecha a comprobar en nuestros fallos |
| --- | --- | --- | --- | --- |
| `ar_third_party_agency` | 0,461 | ~190 | «La agencia paga por cuenta del cliente: el ordenante no es cliente, pero el concepto nombra al deudor o la factura». Ejemplo: ordenante RECOBROS ÁGORA, texto `EXPTE 45553 TERESA IGLESIAS GUTI`, importe exacto de la única factura abierta de ese deudor | `PartyIndex.find` exige el nombre entero cuando el ordenante no está en el maestro (`whole_only`); el nombre del deudor llega cortado. Medir: ordenante desconocido + nombre de cliente en el texto (prefijo ≥ 10 caracteres o ≥ 2 palabras) + importe exacto de una única partida abierta de ese cliente ⇒ candidato único |
| `ar_overpayment` | 0,419 | ~200 | «Paga algo más de lo que debe; la factura se liquida por su importe y el exceso queda a cuenta». Ejemplo: cita la factura, +50 € sobre 5.809 € | La precisión de la clase es 0,976 pero el recall es bajo: ¿los fallos citan la factura y aun así no la casamos? ¿`SMALL_OVERPAYMENT_RATIO`/`ROUND_OVERPAYMENT_RATIO` dejan fuera excesos que el golden acepta? ¿O el motor prefiere otro subconjunto que cuadra? Medir la distribución del exceso en los fallos |
| `ar_fx` | 0,762 | ~180 | «Factura en divisa cobrada en euros al cambio del banco; `amount` en la divisa de la factura; FX_DIFFERENCE». Ejemplo: `orig_amount` 1610,69 USD = factura | ¿Fallan los que traen `orig_amount` (cuadre exacto en divisa) o los que no lo traen (habría que casar por tercero y única partida abierta en esa divisia)? ¿Ponemos la excepción cuando no toca o al revés? |
| `ar_advance_deduction` | 0,703 | ~80 | «La factura descuenta un anticipo ya cobrado contra una proforma, lo dice el PDF: se cobra el neto, PARTIAL». Cláusula: «A deducir anticipo recibido según proforma … Importe neto a pagar …» | ¿Nuestro parser de PDF extrae esa cláusula en los seis idiomas? ¿Y `policy` la aplica como PARTIAL con el neto? Medir cuántos fallos tienen la cláusula en su PDF |
| `ar_retention` | 0,799 | ~200 | «El PDF fija un porcentaje retenido hasta la recepción; el cliente paga el resto: PARTIAL por lo cobrado». Cláusula: «Retención en garantía del 10 % … Importe a pagar al vencimiento …» | Igual que arriba: cobertura de la cláusula y su aplicación. Hoy una condición de país la rompió y se arregló: comprobar que no queda otra |
| `ar_short_dispute` / `ar_dispute_settlement` | 0,75 / 0,863 | ~450 | «El cliente descuenta una reclamación de una factura de la remesa: esa fila lleva lo realmente pagado y SHORT_DISPUTE». Trampa: «aplicar el descuento a otra factura de la remesa» | El piloto de Jev mostró que el motivo se clasifica bien y que los fallos son de casación: ¿asignamos la deducción a la factura equivocada? ¿Cómo dice el aviso cuál es? Medir en los fallos si la fila del aviso con deducción es la que marcamos |
| `ar_short_withholding` | 0,896 | ~150 | «Solo va en la partida que sufre la retención», no en todas las filas de la remesa | ¿Marcamos SHORT_WITHHOLDING en todas las filas de una remesa cuando solo una la sufre? Medir filas con la excepción frente al golden |
| `ar_same_amount_fifo` / `_month` | 0,936 / 0,965 | ~560 | «Varias facturas abiertas con el mismo importe; sin más pistas, la más antigua (FIFO), como dice POLICIES». `_month`: la del mismo mes | ¿Cuándo nos apartamos de FIFO? Sospecha: una cita parcial o un aviso mal enlazado gana a FIFO; o el saldo de apertura ya no tiene la más antigua. Medir en los fallos qué factura elegimos y por qué |
| `ap_confirming` | 0,803 | ~170 | «Un único cargo paga facturas de varios proveedores en la misma remesa; una fila por factura». Trampa: «casarlo con un solo proveedor» | Exactitud escribe hoy «confirming parcial». No duplicar: solo medir lo que quede tras su PR |
| `customer_advance` | 0,788 | ~60 | Cobro de un cliente sin factura aún (anticipo): categoría, sin partida | ¿Lo dejamos en UNIDENTIFIED o lo casamos con una factura posterior? Medir |
| `ar_instalment` | 0,919 | ~380 | «El PDF dice que se paga en varios vencimientos; este cobro es uno de ellos: PARTIAL» | Exactitud hace hoy «última cuota de un plan con importes distintos». Medir solo lo que quede: cuotas de importe igual sin cita, planes que el parser no lee |

Fuera de alcance aquí: `ar_ref_noise` (sin señal en texto, medido), `ar_n_to_m` y `ar_partial` (sesión N a M), `ar_1toN_credit_note` (N a M, R4).

## 3. Método por segmento

1. **Agente «diff» (Opus):** `just be-diff runs/acc-group-holdout --segment <s>` ya existe y no carga la máquina; con su salida y el golden, clasifica los fallos del segmento por causa y comprueba la sospecha de la tabla con números: cuántos fallos tienen la señal que el ejemplo nombra (documento, nombre en texto, importe exacto) y qué hizo el motor en su lugar (regla, candidatos, excepción). Umbral fijado ahora: una regla entra si en holdout explica ≥ 0,98 de las líneas que activa con 0 falsos sobre `unidentified`/`unidentified_lookalike`.
2. **Agente «documentos» (Opus):** para retención, anticipo, cuotas y FX, revisa `documents/pdfs.py` y `documents/advices.py` contra las cláusulas de los ejemplos y mide la cobertura real sobre los PDFs de holdout (texto ya extraído en caché `runs/cache/pdfs/`).
3. **Agente «reglas» (Opus):** TDD con casos inventados calcados de los ejemplos oficiales (el ejemplo es un test perfecto: entrada y filas esperadas), solo para los segmentos que pasen el umbral. Docstring «por qué generaliza»: cita el ejemplo oficial y POLICIES.

La sesión integra, pide hueco para medir (holdout; drift una vez al final), abre una PR por segmento y la orquestadora fusiona.

## 4. Puerta y entregables

Puerta: la de `ACCURACY_PLAN.md` (ningún segmento −0,002 en holdout y drift, pares ≥ 0,995, `unidentified`/`lookalike` 1,000, clases, CSV determinista, ≤ 7,5 GB, ≤ 150 s).

Entregables: a la hora, `docs/SEGMENTS_AUDIT.md` con la tabla «segmento × causa de fallo × señal del ejemplo presente sí/no × líneas»; después, PRs por segmento con test, docstring y evidencia; a las 16:30, lo que queda fuera con cifras. Comunicación con la orquestadora por `SendMessage`: tabla a la hora, cada hipótesis con números, cada hueco, cada PR.
