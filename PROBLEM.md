# PROBLEM.md

El problema que resolvemos en **Close the Books**, el reto del Claude Code Hackathon. Es la fuente de verdad del equipo y de los agentes: léelo antes de construir nada.

> **Alcance.** Describe el problema: qué entra, qué se evalúa y qué no sabemos todavía. No describe nuestra solución; eso está en [ARCHITECTURE.md](ARCHITECTURE.md).
>
> **Fuentes.** [Página del evento](https://spainhackathons.com/events/claude-code-hackathon-close-the-books) y [registro en Luma](https://luma.com/claude-kggz), leídas el 6 nov 2026. Las citas son literales.
>
> **Estado.** v0, solo con la información pública. Se completa con el paquete oficial el día del evento; **si este documento contradice al paquete, manda el paquete.** Lo marcado **[Inferencia]** no lo dice ninguna fuente: es una hipótesis nuestra y se tiene que confirmar o descartar.

## 1. En una frase

Construir un agente que cierre la contabilidad de una empresa sintética multi-entidad, a partir de sus facturas, pedidos, banco, contratos, proveedores, libro mayor e historial del ERP, con el mínimo de intervención humana y dejando cada decisión trazable para auditoría.

## 2. El evento

| | |
| --- | --- |
| Nombre | Claude Code Hackathon — Close the Books |
| Formato | «Jornada de un día de Claude Code (Claude Code Build Day) dedicada a construir una oficina financiera autónoma» |
| Fecha | Sábado 7 nov 2026, de 09:00 a 21:00 |
| Lugar | La Nave, C. Cifuentes 5, Villaverde, Madrid. Presencial, unas 70 plazas |
| Diseño del reto | Talky («IA para contabilidad») con UCppM, la asociación de programación competitiva de la UCM |
| Organiza | Claude Community Events |
| Equipos | Asignados por la organización: «La revisión de solicitudes se hace de forma personal, no por equipos» |

## 3. El reto

> «El reto: construir un equipo financiero de IA y dejar que cierre los libros.»

La página tiene dos categorías:

**Cierre contable autónomo.** «Convertir los datos sintéticos de una empresa multi-entidad (facturas, órdenes de compra, transacciones bancarias, contratos, datos de proveedores, libro mayor e historial del ERP) en un cierre seguro, trazable y listo para auditoría con la mínima intervención humana.»

**Precisión contable y conciliación.** «Puntuado en la clasificación en vivo, junto con la detección de fraude, la autonomía segura y la auditabilidad; se incluyen duplicados, errores fiscales y cambios bancarios sospechosos.»

«Cada equipo recibe la misma empresa sintética multi-entidad.»

## 4. Entradas

### 4.1 Lo que dice la fuente

Siete tipos de dato, de una sola empresa **multi-entidad**:

| Tipo | Qué esperamos que contenga **[Inferencia]** | Para qué sirve en el cierre **[Inferencia]** |
| --- | --- | --- |
| Facturas | Recibidas y quizá emitidas: emisor, receptor, número, fecha, base, impuestos, total, moneda | Contabilizar, casar con pedidos y con pagos; detectar duplicados y errores fiscales |
| Órdenes de compra | Proveedor, líneas, cantidades, precios, sociedad compradora | Casar pedido con factura (y con recepción, si la hay) |
| Transacciones bancarias | Extracto por cuenta: fecha, importe, concepto, contraparte, IBAN | Conciliación bancaria contra el libro mayor y las facturas |
| Contratos | Partes, vigencia, importes o tarifas, condiciones de pago | Validar que lo facturado cumple lo pactado; periodificaciones |
| Datos de proveedores | Maestro: identificador fiscal, IBAN, condiciones | Validar facturas y pagos; detectar cambios de cuenta sospechosos |
| Libro mayor | Asientos por sociedad, cuenta, fecha e importe | Punto de partida del cierre y destino de los ajustes |
| Historial del ERP | Registro de cambios: qué objeto, qué campo, valor anterior y nuevo, quién y cuándo | Auditoría; detectar cambios de IBAN u otros cambios de maestro sospechosos |

### 4.2 Lo que no dice

Formato de los ficheros, cómo se entregan, número de sociedades, países, monedas, periodo que se cierra, volumen y si hay datos de referencia para comprobar el resultado. **[Inferencia]** Por el reto anterior de Talky (Kalmora), esperamos un paquete comprimido con ficheros JSONL, CSV y documentos, y quizá un periodo de desarrollo con solución y otro de evaluación sin ella.

## 5. Problemas sembrados en los datos

La fuente nombra tres: «Se incluyen duplicados, errores fiscales y cambios bancarios sospechosos.»

| Problema | Cómo puede aparecer **[Inferencia]** | Respuesta segura **[Inferencia]** |
| --- | --- | --- |
| Duplicados | La misma factura dos veces, con número reformateado, por otro canal o con importe idéntico en fechas cercanas | No contabilizar ni pagar la segunda; enseñar la pareja |
| Errores fiscales | Tipo de impuesto que no corresponde, base × tipo ≠ cuota, total que no cuadra, identificador fiscal inválido | Retener y explicar el cálculo correcto |
| Cambios bancarios sospechosos | IBAN de la factura o del pago distinto al del maestro, o cambio de IBAN en el historial del ERP poco antes de un pago | Retener el pago y pedir verificación fuera del sistema |

Puede haber más tipos de anomalía que la fuente no nombra.

## 6. Evaluación

> «Una clasificación en vivo puntúa la precisión contable, la conciliación, la detección de fraude, la autonomía segura y la auditabilidad, y un benchmark oculto decide la final.»

| Criterio | Nuestra lectura **[Inferencia]** |
| --- | --- |
| Precisión contable | Los asientos y saldos que deja el agente coinciden con los correctos |
| Conciliación | Cada movimiento bancario queda casado con lo que le corresponde en el libro, o explicado si no casa |
| Detección de fraude | Se detectan los duplicados, errores fiscales y cambios bancarios sembrados, sin falsos positivos que bloqueen lo legítimo |
| Autonomía segura | El agente resuelve solo lo que es seguro y para lo dudoso o arriesgado para que lo revise una persona. Ni lo para todo ni lo aprueba todo |
| Auditabilidad | Cada decisión se puede reconstruir: qué regla, qué datos de origen, qué se cambió y quién lo aprobó |

**No se publican pesos, formato de entrega ni scorer.**

**[Inferencia]** Implicaciones:
- Hay dos evaluaciones: el leaderboard sirve para iterar y el benchmark oculto decide. Sobreajustar al leaderboard es un riesgo: las reglas tienen que salir de principios contables y de los datos, no de lo que suba la nota.
- «Autonomía segura» castiga los dos extremos: escalar todo a una persona y aprobar a ciegas.

## 7. Qué hay que averiguar en la primera hora

- [ ] Formato y estructura del paquete de datos; número de sociedades, países y monedas.
- [ ] Periodo que se cierra y si hay periodos con solución para desarrollar.
- [ ] Formato exacto de la entrega y cómo se envía al leaderboard. ¿Hay límite de envíos?
- [ ] Pesos de cada criterio y cómo se mide cada uno, sobre todo autonomía segura y auditabilidad.
- [ ] Qué se entrega además del resultado: repo, demo, presentación, documentación.
- [ ] Reglas: modelos y herramientas permitidos, datos externos, coste o tiempo que hay que declarar.
- [ ] Si existe una política contable oficial (como `POLITICAS_CONTABLES.md` en Kalmora) que manda sobre las decisiones.

## 8. Glosario

| Término | Significado |
| --- | --- |
| Cierre | Dejar los libros de un periodo completos y correctos: todo contabilizado, conciliado y ajustado |
| Multi-entidad | Varias sociedades del mismo grupo, cada una con sus libros; puede haber operaciones entre ellas (intragrupo) |
| Conciliación bancaria | Casar cada línea del extracto con su apunte en el libro mayor (1:1, 1:N o N:M) y explicar las diferencias |
| Casación a tres bandas (3-way match) | Comprobar que pedido, recepción y factura coinciden en cantidades y precios antes de pagar |
| Libro mayor | Registro de todos los asientos, por cuenta y sociedad |
| Maestro de proveedores | Ficha de cada proveedor: identificador fiscal, cuenta bancaria, condiciones de pago |
| Historial del ERP | Registro de cambios sobre los datos del sistema contable |
| Revisión humana | Partida que el agente no cierra solo y deja a una persona, con su motivo y su evidencia |

## 9. Terminado (provisional)

Se ajusta cuando se conozca el formato de entrega:

- [ ] El agente carga el paquete completo sin modificarlo.
- [ ] Produce la entrega en el formato oficial y la envía al leaderboard.
- [ ] Cada decisión automática tiene su regla y sus datos de origen.
- [ ] Los tres tipos de anomalía de la §5 se detectan y se retienen, con su motivo.
- [ ] Lo que no es seguro resolver solo queda en revisión humana, con prioridad e importe.
- [ ] La interfaz enseña el cierre, las alertas y la evidencia de cada decisión.
