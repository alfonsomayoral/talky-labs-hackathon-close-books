# FINAL_REHEARSAL.md: qué prueba el ensayo de FINAL

`scripts/analysis/07_final_rehearsal.py` copia una fase cambiando los nombres de una sociedad: código, banco, formato de extracto y divisa no vistos, en movimientos, partidas, maestros, ficheros de detalle e índices, y la divisa impresa en los avisos. Los importes no cambian y la divisa nueva lleva los tipos de la antigua, así que cualquier caída viene de una regla atada a un nombre.

## Resultado

Holdout, `main` `c2ffaf6`, MA01 → XX01, LORV → QNTM, MAD → HUF:

| Prueba | Score | Movimientos distintos |
| --- | --- | --- |
| holdout | 93,52 | — |
| holdout-final, sin arreglo | 93,52 | 2 de 199.987 |
| holdout-final, con arreglo | 93,52 | 2 de 199.987 |

Las 2 líneas son del ensayo: citan una remesa de diciembre de 2024, cuyo fichero de la fase anterior conserva la cuenta antigua.

## El arreglo del banco nuevo

Un banco fuera de la tabla de categorías usa lo que su código significa en los demás bancos.

| Prueba | Efecto |
| --- | --- |
| Holdout normal | CSV idéntico con `cmp`: ningún banco conocido cambia |
| holdout-final | 0 líneas del CSV: en LORV el respaldo ya acertaba con `BANK_FEES` |
| holdout-drift | CSV idéntico, 93,27 |
| Tabla sin MONC ni MEZQ | `customer_refund` sigue en 0,9576 y ningún segmento cambia; 2 líneas pasan de una categoría errónea a otra |
| Sample, DE01 renombrada | Recupera 5 líneas de `CUSTOMER_REFUND` |

**No hay ganancia medible en holdout**, solo en sample, y nada baja. Las 15 líneas de `customer_refund` que se pierden sin MONC usan el código `04 533`, que solo tiene ese banco: consultar los demás bancos no puede recuperarlas.

## Lo que no prueba

- **Una sociedad sin historial:** XX01 conserva clientes y partidas; ZA01 llega sin ellos. `--no-history` quita lo que arrastra.
- **Numeración nueva:** se mantiene la antigua. La prueba `holdout-drift` (KWI).
- **Las partidas cerradas de TRAIN** conservan el código antiguo.
- **Los PDFs de factura** conservan la divisa antigua en su texto; solo se reescriben los avisos.
- **Divisa sin tipo:** en sample no cae, y `load.py` avisa por stderr. Sobre MA01 inflaría los importes en euros; no se ha corrido en holdout.
