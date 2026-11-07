# SUBMISSION.md: borrador de la descripción para el jurado

> Borrador. Cifras de `live-kpi6-cases2`. `<S>` y `<F>` se rellenan con la clasificación. Ninguna cifra se da por buena hasta que esté medida.

## Ideas clave

Para cada movimiento bancario de un grupo de 17 sociedades y 12 divisas, decimos qué facturas y abonos liquida y por qué importe, o qué es si no liquida ninguno.

- **Las reglas deciden; el modelo solo lee.** Un pipeline determinista concilia en pasadas por certeza: ficheros de remesa, avisos, números en el texto, tercero e importe, categorías. Los parsers leen los documentos. Un modelo podría extraer hechos de los que no lean, con caché, pero nunca elegiría una casación; hoy no ha hecho falta.
- **No se fuerza nada.** Sin evidencia, el movimiento sale como no identificado, y la duda se convierte en una pregunta a una persona.
- **Cada fila se explica.** La entrega lleva su regla y sus fuentes: aviso, fichero, PDF o maestro.
- **Caso, decisión, memoria.** La plataforma enseña lo que el sistema cerró solo (86,8 % de los movimientos de LIVE) y lo que necesita a alguien: preguntas, correos a clientes y proveedores que una persona revisa, y reglas que la siguiente ejecución aplica. Los correos se registran; no sale ninguno.

Resultado: `<S>` puntos en LIVE y `<F>` en FINAL. En LIVE, 203.083 movimientos en 2 minutos, 33.920 casos para una persona, con 0 llamadas a modelo y 0 dólares: todo determinista, con el modelo como residuo opcional, hoy sin usar.

## Stack y modelos

Python 3.12, Polars, DuckDB y FastAPI en el pipeline. React 19, Vite, TypeScript y TanStack Query y Virtual en la plataforma. `claude-haiku-5-5` previsto para documentos residuales, con corte duro por ejecución; en la ejecución de LIVE no se usó. Construido con Claude Code: tres sesiones en bucle (backend, frontend y una orquestadora) con un contrato escrito entre ellas, medido siempre con el evaluador oficial.

## Qué haríamos después

- Conectar el «enviar» a un servidor de correo real y seguir las promesas de pago.
- Medir cuánto suben las reglas de memoria con decisiones de personas de verdad.
- Leer el saldo y el libro mayor del ERP para cerrar el ciclo contable.

## Equipo

- 
- 
- 
