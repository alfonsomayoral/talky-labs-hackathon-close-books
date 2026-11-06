# CLAUDE.md

Cómo se trabaja en este repo. Es el agente de cierre contable de **Close the Books**, el reto del Claude Code Hackathon (Madrid, 7 nov 2026): convertir los datos de un grupo multi-sociedad en un cierre seguro, trazable y listo para auditoría.

**Lee antes de tocar nada:** [PROBLEM.md](PROBLEM.md) (qué se resuelve y cómo se evalúa) y [ARCHITECTURE.md](ARCHITECTURE.md) (cómo está construido). Si contradicen al paquete oficial de los organizadores, manda el paquete.

**Compromiso:** estas reglas priman la prudencia sobre la velocidad. En tareas triviales, usa el sentido común.

## 1. Piensa antes de programar

**No asumas. No escondas la duda. Enseña los compromisos.**

- Di tus suposiciones explícitamente. Si dudas, pregunta.
- Si caben varias lecturas que llevan a cambios distintos, preséntalas. No elijas en silencio.
- Si hay un camino más simple, dilo antes de implementar. Discrepa cuando toque.
- Si algo no está claro, para, nombra qué te confunde y pregunta.
- Separa lo que dicen los datos, lo que dice una regla y lo que infieres tú. Una inferencia nunca se presenta como un hecho del dataset.

## 2. Simplicidad primero

**El mínimo código que resuelve el problema. Nada especulativo.**

- Antes de escribir, busca si ya existe: componentes en `app/src/components/`, formato en `app/src/lib/`, tipos en `app/src/domain/`.
- Ninguna funcionalidad, parámetro ni abstracción más allá de lo pedido.
- Ninguna abstracción para un solo uso. Ninguna «flexibilidad» que nadie haya pedido.
- Ningún manejo de errores para escenarios que no ocurren.
- Si escribes 200 líneas y caben en 50, reescríbelo.

**Simple no es frágil.** Lo que el caso real ya trae hay que aguantarlo: volumen del libro mayor, datos sucios, varias monedas. Recortar eso es un bug, no simplicidad.

## 3. Cambios quirúrgicos

**Toca solo lo necesario. Limpia solo lo tuyo.**

- Cada línea del diff se rastrea hasta lo pedido.
- Resuelve cada cosa como ya la resuelven los ficheros vecinos, aunque tú lo harías de otra manera.
- No «mejores» código, comentarios ni formato que tu cambio no toque.
- Quita lo que **tu** cambio deje huérfano. El código muerto ajeno se menciona, no se borra.

## 4. Ejecución dirigida por un objetivo verificable

**Define qué significa «terminado» antes de empezar. Itera hasta cumplirlo.**

Convierte cada tarea en un criterio comprobable y, si tiene varios pasos, escribe el plan:

```
1. [paso] -> compruebo: [cómo]
2. [paso] -> compruebo: [cómo]
```

- **Lógica (`backend/`, `app/src/data/`, `app/src/domain/`):** TDD. Primero el test, y lo ves fallar por la razón correcta; luego el mínimo código que lo pone en verde; luego refactor sin salir del verde. «Detecta duplicados» se convierte en «test con una factura duplicada que falla; luego hazlo pasar».
- **Pantallas:** se miran en el navegador con los datos cargados, con cero errores en consola.
- **Cada test tiene que poder pillar un bug.** Si rompes la lógica y el test sigue en verde, sobra. Un test por comportamiento, más los bordes que romperían con datos reales (duplicados, varias monedas, datos sucios).
- Nada de smoke tests («renderiza», «no lanza», «el módulo existe»), snapshots, tests que repiten la implementación ni tests que solo comprueban que se llamó a un mock.
- Antes de dar algo por hecho, `just fe-check` (o `just be-check` y `just be-test`) en verde, con la salida pegada. Si algo falla o no lo has comprobado, dilo.

## 5. Reglas del dominio

- **El backend decide; el frontend enseña.** El frontend nunca calcula una casación, una alerta ni un asiento: los lee del `Run` (ver `CONTRACT.md`).
- **Cada decisión del agente lleva su evidencia:** la regla que la produjo y los objetos de origen (factura, línea bancaria, pedido, contrato, evento del ERP). Sin evidencia no hay decisión automática; va a revisión humana.
- **Importes en céntimos enteros, siempre con su moneda.** Nunca se suman monedas distintas.
- **Todo objeto lleva `entityId`.** Ninguna vista ni regla mezcla sociedades sin decirlo.
- **Nunca se modifican los datos de entrada** para que una regla funcione.
- **El paquete del cliente vive en `data/` y nunca se commitea.** Tampoco salidas ni ejecuciones con datos reales.

## 6. Reglas del frontend (`app/`)

- La marca es la de Talky ([usetalky.com](https://usetalky.com)): naranja `#F3572F` para el dato principal, la selección y el foco; marino `#16224F` para la única acción primaria; tinta `#101938`; Newsreader para titulares, Geist para el texto y Chivo Mono para ids (al estilo de rex.inc). Está en `src/design/tokens.css` (ver ARCHITECTURE.md §5.4 y §5.5).
- Cada vista va dentro de la hoja blanca del shell; su contenido son tarjetas con borde de 1 px y la sombra suave de `--shadow-card`, que crece al pasar el ratón. Lo que abre otra cosa es una tarjeta. La barra lateral es un rail que se despliega al pasar el ratón y empuja la vista.
- Solo los tokens de `src/design/tokens.css`: ningún color, sombra ni radio fuera de ellos. Estilos con CSS Modules, un fichero por componente.
- Importes con `<Amount>`, ids y códigos con `<Mono>`, fechas y porcentajes con `@/lib/format`. Nunca se formatean a mano.
- Las vistas importan de `@/data`, `@/domain`, `@/components` y `@/lib`. Nunca de `data/sources`, `data/parsers` ni `data/registry` por dentro.
- Un tipo de dato nuevo es un spec en `src/data/registry/`, no una página nueva.
- Interfaz en español; código, identificadores y commits en inglés.

## 7. Comandos

| Comando | Para qué |
| --- | --- |
| `just fe-dev` | Servidor de desarrollo del frontend |
| `just fe-check` | Typecheck, lint, test y build del frontend |
| `just be-check` · `just be-test` | Lint y tests del backend (cuando exista `backend/`) |

## 8. Git

- Nunca se trabaja en `main`. Cada cambio va en una rama `KPI-<n>_<descripcion>`.
- Un commit por cambio lógico, con asunto `[KPI-<n>] type: subject` (`feat`, `fix`, `docs`, `refactor`, `test`, `chore`). Sin ámbito entre paréntesis.
- Sin `Co-Authored-By`, atribución a IA ni emojis, ni en commits ni en PR. El cuerpo de la PR es solo un resumen.
- `git push` y abrir PR, solo cuando se pida.

## 9. Al terminar

Di qué cambió, qué comprobaste (con la salida) y qué queda sin verificar. Si ves algo mejorable fuera del alcance, dilo en una línea al final.

---

**Esto funciona si:** los diffs no traen nada fuera de lo pedido, no hay que reescribir por haberlo complicado, cada cambio se parece al código que lo rodea y las dudas llegan antes de implementar, no después del error.
