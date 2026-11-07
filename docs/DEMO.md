# DEMO.md: guion del vídeo (5 minutos)

Grabar a 1440 × 900 como mínimo (720p o más), en un tema: el oscuro lee mejor en vídeo; el cambio a claro se enseña una vez. Antes de grabar:

Arranca `serve` **dos minutos antes** de grabar: tarda cerca de un minuto en aceptar conexiones y ocupa unos 4 GB. El detalle está en [HANDOFF.md](HANDOFF.md).

```bash
just be-serve runs/live-<la última con buena puntuación>
```

```bash
just fe-dev
```

Las cifras `<…>` salen de la ejecución servida:

```bash
node app/mock/figures.mjs
```

**Comprobaciones previas** (todas con la ejecución que se va a enseñar):

- La última ejecución de LIVE tiene preguntas y borradores (`questions.jsonl` y `drafts.jsonl` con filas). Sin ellos, los pasos 3 y 4 no se pueden grabar.
- Hay al menos una pregunta con `rulePreview` y un caso `overdue_customer` con borrador. Si no hay `overdue_customer`, se graba la variante B del paso 4.
- Se conoce un movimiento con un aviso de remesa en su evidencia: apúntate su id para el paso 2.
- Las cifras entre `<…>` se rellenan con lo que enseñe esa ejecución. No se dice una cifra que no esté en pantalla.
- Nunca se enseña el token ni la terminal desde la que se envía a la clasificación.

| # | Tiempo | Pantalla | Qué se hace | Qué se dice |
| --- | --- | --- | --- | --- |
| 1 | 0:00–0:40 | **Resumen** `/` | Se abre con LIVE cargada. Se pasa por la franja de cifras y se señala el gráfico por día | «Un grupo de 17 sociedades, 12 divisas y 203.083 movimientos en seis meses. El sistema ha cerrado solo el `<X> %`, y `<N>` casos esperan a una persona. Ha costado `<Y>` dólares de modelo: las reglas deciden, el modelo solo lee documentos» |
| 2 | 0:40–1:40 | **Conciliación** `/conciliacion` | Se busca un movimiento de aviso de remesa y se abre el panel: partidas, regla, evidencia con el aviso abierto en línea, tercero, línea del banco | «Cada fila de la entrega dice qué regla la produjo y en qué se apoya. Aquí está el aviso que llegó, y qué factura liquida cada línea. Si no hay evidencia, no se fuerza: sale como no identificado» |
| 3 | 1:40–2:40 | **Te necesitan** `/bandeja` | Se abre una pregunta, se elige una opción, se marca «Guardar como regla» y se responde | «Dos facturas iguales y un pagador desconocido: en lugar de adivinar, pregunta. La respuesta se convierte en memoria, y la próxima ejecución ya no preguntará» |
| 4 | 2:40–3:20 | **Cobros** `/cobros` | Se abre el cliente con más saldo vencido, se edita una línea del correo y se envía | «La misma bandeja lleva el cobro: tramos de vencimiento, disputas y un correo preparado con las facturas adjuntas. Una persona lo revisa. En esta demo se registra: no sale ningún correo» |
| 5 | 3:20–3:40 | **Proveedores** `/proveedores` | Se abre una incidencia y se enseña el correo al proveedor | «Facturas de proveedor pagadas por otro importe o dos veces, cada una con su correo. Lo que no hay en los datos, pedidos de compra, no lo fingimos» |
| 6 | 3:40–4:00 | **Memoria y reglas** `/memoria` | Se enseña la regla recién guardada | «Aquí está lo que el sistema ha aprendido, quién lo enseñó y de qué caso salió» |
| 7 | 4:00–4:25 | **Cuentas** `/cuentas` y **Explorador** `/explorador` | Una cuenta con cambio de formato; una pestaña del Explorador con un documento abierto | «Los datos del paquete, a escala real: un banco que cambia de formato en octubre sin tocar código» |
| 8 | 4:25–5:00 | **Ejecuciones** `/ejecuciones` | Historial, comparar dos ejecuciones por segmento, consola FINAL | «Cada ejecución queda medida. La consola deja lista la fase FINAL en un solo paso, en `<Z>` minutos sobre datos nunca vistos. El envío lo hace una persona: aquí no hay botón» |

## Variante B del paso 4 (40 s, sin `overdue_customer`)

Se decide a las 09:15 con la ejecución que haya. Si ningún cliente tiene caso de cobro, Cobros no tiene correo que preparar: se enseña el aging y las disputas, y el correo se enseña en el paso 5.

| # | Tiempo | Pantalla | Qué se hace | Qué se dice |
| --- | --- | --- | --- | --- |
| 4B | 2:40–3:20 | **Cobros** `/cobros` | Se señala el reparto por tramos, se abre el cliente con más saldo vencido y se bajan sus partidas y disputas | «La misma plataforma lleva el cobro: quién debe qué, desde cuándo y qué tiene en disputa, con el riesgo calculado a la vista. El correo es el mismo que vais a ver con el proveedor» |

En ese caso el paso 5 sube a 40 s: se edita una línea del correo al proveedor, se envía y se dice «Una persona lo revisa. En esta demo se registra: no sale ningún correo».

## Si algo falla al grabar

- **La API no responde:** la barra lateral dice «Sin conexión con la API». Arranca `just be-serve` otra vez.
- **Una pantalla va lenta la primera vez:** `serve` no acepta conexiones hasta acabar la precarga, así que no debería pasar. Si pasa, ábrela antes de grabar.
- **Sin preguntas o borradores en la ejecución:** la bandeja sigue funcionando con «Marcar gestionado», pero los pasos 3 y 4 pierden su sentido: pide una ejecución que los genere antes de grabar.
