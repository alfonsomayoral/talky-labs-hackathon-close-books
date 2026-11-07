# DEMO.md: guion del vídeo (5 minutos)

Grabar a 1440 × 900 como mínimo (720p o más), en un tema: el oscuro lee mejor en vídeo; el cambio a claro se enseña una vez. Antes de grabar:

Arranca `serve` **dos minutos antes** de grabar: tarda cerca de un minuto en aceptar conexiones y ocupa unos 4 GB. El detalle está en [HANDOFF.md](HANDOFF.md).

```bash
just be-serve runs/live-<la última con buena puntuación>
```

```bash
just fe-dev
```

Las cifras salen de la ejecución servida:

```bash
node app/mock/figures.mjs
```

## Datos del guion

Con `<ejecución>`, la última de LIVE enviada antes de la congelación. Los `<…>` de esta página se rellenan con ella antes de grabar: `node app/mock/figures.mjs` da las cifras, y los ids se abren uno a uno con la ejecución servida.

| Marcador | De dónde sale | Con `live-final-a`, solo de referencia |
| --- | --- | --- |
| `<ejecución>` | `figures.mjs` | `live-final-a` |
| `<auto>` | `figures.mjs` | 87,0 % |
| `<decisiones>`, `<por revisar>`, `<cobros>` | `figures.mjs` | 235, 18.018, 15.305 |
| `<llamadas>` | `figures.mjs` | 0 |
| `<id-aviso>`, `<cliente-aviso>` | Un movimiento con un aviso de remesa en su evidencia | `BT-2025-0200180`: Villar Mantenimientos S.A., 826,93 EUR, 2 facturas, una con pago parcial |
| `<id-pregunta>` | Una pregunta con `rulePreview` | `CASE-BT-2025-0378685`, pregunta `Q-000128`: Wellness Navarro S.L., 1.035,17 EUR, dos opciones |
| `<id-cliente>`, `<cliente>`, `<importe-correo>`, `<importe-panel>` | Un cliente con caso `overdue_customer` y borrador | `CES01000094`: Montalbar Hidrotecnia S.L., 138 facturas, borrador `D-000050` con 2 adjuntos; correo 418.279,57 €, panel 460.396,55 € |
| `<id-proveedor>`, `<proveedor>` | Una incidencia de proveedor con borrador | `CASE-BT-2025-0293358-API-2025-7506669`: Plásticos Express S.L.U., 36.948,26 EUR, borrador `D-000105` |

| Paso | Qué | Enlace (añade `?…` a la dirección de Vite) |
| --- | --- | --- |
| 1 | `<auto>` de los movimientos cerrados sin intervención; `<decisiones>` **decisiones**, `<por revisar>` por revisar y `<cobros>` de cobros; `<llamadas>` llamadas a modelo | `/` |
| 2 | Aviso de remesa de `<cliente-aviso>` | `/conciliacion?ver=<id-aviso>` |
| 3 | Pregunta con dos opciones y regla propuesta | `/bandeja?ver=<id-pregunta>` |
| 4 | `<cliente>`, facturas vencidas por `<importe-correo>` y borrador con adjuntos | `/cobros?ver=<id-cliente>` |
| 5 | `<proveedor>`: factura pagada en parte y borrador | `/proveedores?ver=<id-proveedor>` |

Ábrelos uno a uno en el navegador con la ejecución servida. Dos cosas que se ven en pantalla:

- **Paso 4:** el panel del cliente dice `<importe-panel>` vencidos y su correo `<importe-correo>`. No es un error: el correo reclama solo lo vencido hace más de 15 días. Di la cifra del correo o no digas ninguna.
- **Paso 5:** conviene enseñar el correo más que las partidas de ese proveedor.

**Comprobaciones previas** (todas con la ejecución que se va a enseñar):

- La última ejecución de LIVE tiene preguntas y borradores (`questions.jsonl` y `drafts.jsonl` con filas). Sin ellos, los pasos 3 y 4 no se pueden grabar.
- Hay al menos una pregunta con `rulePreview` y un caso `overdue_customer` con borrador. Si no hay `overdue_customer`, se graba la variante B del paso 4.
- Se conoce un movimiento con un aviso de remesa en su evidencia: apúntate su id para el paso 2.
- No se dice una cifra que no esté en pantalla. No queda ningún `<…>` en esta página al grabar.
- Nunca se enseña el token ni la terminal desde la que se envía a la clasificación.

| # | Tiempo | Pantalla | Qué se hace | Qué se dice |
| --- | --- | --- | --- | --- |
| 1 | 0:00–0:40 | **Resumen** `/` | Se abre con LIVE cargada. Se pasa por la franja de cifras y se señala el gráfico por día | «Un grupo de 17 sociedades, 18 con la filial que entra en 2026, 12 divisas y 203.083 movimientos en seis meses. El sistema ha cerrado solo el `<auto>` de los movimientos, y lo que queda se separa: `<decisiones>` decisiones, `<por revisar>` casos por revisar y `<cobros>` de cobros. Todo determinista: los parsers leen los documentos y las reglas deciden; el modelo queda como residuo opcional, hoy sin usar» |
| 2 | 0:40–1:40 | **Conciliación** `/conciliacion` | Se abre el movimiento del aviso de `<cliente-aviso>` y se ve el panel: partidas, regla, evidencia con el aviso abierto en línea, tercero, línea del banco | «Cada fila de la entrega dice qué regla la produjo y en qué se apoya. Aquí está el aviso que llegó, y qué factura liquida cada línea. Si no hay evidencia, no se fuerza: sale como no identificado» |
| 3 | 1:40–2:40 | **Te necesitan** `/bandeja` | Se abre una pregunta, se elige una opción, se marca «Guardar como regla» y se responde | «Dos facturas iguales y un pagador desconocido: en lugar de adivinar, pregunta. La respuesta se convierte en memoria, y la próxima ejecución ya no preguntará» |
| 4 | 2:40–3:20 | **Cobros** `/cobros` | Se abre `<cliente>`, se edita una línea del correo y se envía | «La misma bandeja lleva el cobro: tramos de vencimiento, disputas y un correo preparado con las facturas vencidas y sus PDF adjuntos. Una persona lo revisa. En esta demo se registra: no sale ningún correo» |
| 5 | 3:20–3:40 | **Proveedores** `/proveedores` | Se abre la incidencia de `<proveedor>` y se enseña el correo al proveedor | «Facturas de proveedor pagadas por otro importe o dos veces, cada una con su correo. Lo que no hay en los datos, pedidos de compra, no lo fingimos» |
| 6 | 3:40–4:00 | **Memoria y reglas** `/memoria` | Se enseña la regla recién guardada | «Aquí está lo que el sistema ha aprendido, quién lo enseñó y de qué caso salió» |
| 7 | 4:00–4:25 | **Cuentas** `/cuentas` y **Explorador** `/explorador` | Una cuenta con cambio de formato; una pestaña del Explorador con un documento abierto | «Los datos del paquete, a escala real: un banco que cambia de formato en octubre sin tocar código» |
| 8 | 4:25–5:00 | **Ejecuciones** `/ejecuciones` | Historial, comparar dos ejecuciones por segmento, consola FINAL | «Cada ejecución queda medida. La consola deja lista la fase FINAL en un solo paso, en poco más de 2 minutos sobre LIVE. El envío lo hace una persona: aquí no hay botón» |

## Variante B del paso 4 (40 s, sin `overdue_customer`)

Se decide a las 09:15 con la ejecución que haya. Si ningún cliente tiene caso de cobro, Cobros no tiene correo que preparar: se enseña el aging y las disputas, y el correo se enseña en el paso 5.

| # | Tiempo | Pantalla | Qué se hace | Qué se dice |
| --- | --- | --- | --- | --- |
| 4B | 2:40–3:20 | **Cobros** `/cobros` | Se señala el reparto por tramos, se abre el cliente con más saldo vencido y se bajan sus partidas y disputas | «La misma plataforma lleva el cobro: quién debe qué, desde cuándo y qué tiene en disputa, con el riesgo calculado a la vista. El correo es el mismo que vais a ver con el proveedor» |

En ese caso el paso 5 sube a 40 s: se edita una línea del correo al proveedor, se envía y se dice «Una persona lo revisa. En esta demo se registra: no sale ningún correo».

## Si algo falla al grabar

- **La API no responde:** la barra lateral dice «Sin conexión con la API». Arranca `just be-serve` otra vez.
- **Una pantalla va lenta la primera vez:** `serve` no acepta conexiones hasta acabar la precarga, así que no debería pasar. Si pasa, ábrela antes de grabar.
- **El vídeo se queda en el esqueleto de carga con la página ya cargada:** es la captura, no la plataforma: el screencast de Chrome deja de entregar fotogramas con la página quieta. El arreglo está sin aplicar, en el commit `928ea6e` (rama local `KPI-7_fe-integration-local`; `586fee9` en la rama remota `KPI-7_fe-second-design-pass`): añade a `record.mjs` un elemento de 1 px en movimiento. Recupéralo con `git cherry-pick` antes de grabar y comprueba los fotogramas de Memoria y Ejecuciones, porque nunca se ha probado en una toma.
- **Sin preguntas o borradores en la ejecución:** la bandeja sigue funcionando con «Marcar gestionado», pero los pasos 3 y 4 pierden su sentido: pide una ejecución que los genere antes de grabar.
