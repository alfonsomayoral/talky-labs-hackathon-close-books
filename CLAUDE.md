# CLAUDE.md

Cómo se trabaja en este repo. Es el conciliador bancario de **Close the Books**, el reto del Claude Code Hackathon (Madrid, 7 nov 2026): decir, para cada movimiento bancario de un grupo de 17 sociedades, qué facturas y abonos liquida y por qué importe, o qué es si no liquida ninguno, en un CSV que se puntúa contra un golden oculto.

**Lee antes de tocar nada:** [PROBLEM.md](PROBLEM.md) (qué se resuelve y cómo se evalúa), [ARCHITECTURE.md](ARCHITECTURE.md) (cómo está construido), [CONTRACT.md](CONTRACT.md) (la carpeta de ejecución y la API) y [docs/PLAN.md](docs/PLAN.md) (el plan, las fases y el método de tres sesiones). Si contradicen al paquete oficial (`db/bankrec-docs-and-masters/`), manda el paquete, y en el etiquetado manda `POLICIES.md`.

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

- Antes de escribir, busca si ya existe: en el backend, normalizadores en `normalize.py`, reglas en `rules/` e importe y excepción en `policy.py` (ARCHITECTURE.md §7.2); en el frontend, componentes en `app/src/components/`, formato en `app/src/lib/` y tipos en `app/src/domain/`.
- Ninguna funcionalidad, parámetro ni abstracción más allá de lo pedido.
- Ninguna abstracción para un solo uso. Ninguna «flexibilidad» que nadie haya pedido.
- Ningún manejo de errores para escenarios que no ocurren.
- Si escribes 200 líneas y caben en 50, reescríbelo.

**Simple no es frágil.** Lo que el caso real ya trae hay que aguantarlo: ~200 k movimientos y ~1 M de partidas por fase (5,6 M en TRAIN), referencias sucias, varias divisas y drift entre fases. Recortar eso es un bug, no simplicidad.

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

- **Lógica (`backend/`, `app/src/data/`, `app/src/domain/`):** TDD. Primero el test, y lo ves fallar por la razón correcta; luego el mínimo código que lo pone en verde; luego refactor sin salir del verde. «Detecta pagos duplicados» se convierte en «test con un movimiento real de TRAIN que paga otra vez una factura ya liquidada, que falla; luego hazlo pasar».
- **Reglas de casación:** además del test, la puntuación local con el evaluador oficial sobre holdout (y drift si hay slot), antes y después. **Decide la nota total:** una regla que sube la nota entra aunque baje la precisión de pares o de un segmento; la tabla por segmento sirve para diagnosticar, no para vetar. Una regla que baja la nota total no está terminada.
- **Pantallas:** se miran en el navegador con los datos cargados, con cero errores en consola.
- **Cada test tiene que poder pillar un bug.** Si rompes la lógica y el test sigue en verde, sobra. Un test por comportamiento, más los bordes que romperían con datos reales (referencias cortadas o con erratas, varias divisas, pagos duplicados, devoluciones).
- Nada de smoke tests («renderiza», «no lanza», «el módulo existe»), snapshots, tests que repiten la implementación ni tests que solo comprueban que se llamó a un mock.
- Antes de dar algo por hecho, `just be-check` y `just be-test` (o `just fe-check`) en verde, con la salida pegada, y la puntuación local si tocaste una regla. Si algo falla o no lo has comprobado, dilo.

## 5. Reglas del dominio

- **Las reglas deciden; los modelos solo extraen.** Un modelo convierte PDFs y avisos de remesa en hechos, con caché; nunca elige una casación.
- **Cada fila de la entrega lleva su evidencia:** la regla que la produjo y sus fuentes (aviso de remesa, fichero de remesa o liquidación, PDF, maestro, otro movimiento), como dice `CONTRACT.md`.
- **Sin evidencia se puede proponer, si suma.** Esto no es una aplicación crítica: un cobro sin identificar puntúa cero en pares y como `UNIDENTIFIED`, así que una regla que adivina (el cliente nombrado, las facturas vencidas más antiguas) entra si la nota total sube en holdout o en LIVE, aunque falle una parte. La fila lleva confianza baja, caso «por revisar» y su `why` dice que es una inferencia. Lo que sigue prohibido es aprender del golden: ninguna constante, lista ni umbral sacado de él. Sin regla que sume, la fila sale de `FALLBACK-*`.
- **Las PR de los compañeros se fusionan y se confían.** Una PR de otro miembro del equipo que pasa el CI se fusiona sin exigirle la medición de las sesiones; se mide después, en la LIVE siguiente, y nunca se revierte ni se propone revertirla por la precisión de un segmento. Si la LIVE baja, se avisa a Alfonso con la cifra y decide él.
- **Ningún movimiento sin fila.** Un movimiento que falta es un fallo seguro en la puntuación.
- **Importes en céntimos enteros, siempre con su moneda.** Nunca se suman monedas distintas. El `amount` del CSV va en la divisa de la partida, con dos decimales, y solo se formatea al escribirlo.
- **Todo objeto lleva su sociedad.** Ninguna regla mezcla sociedades sin decirlo; los cruces legítimos (la fábrica de pagos de ES00, la matriz que paga por sus filiales) se nombran en la regla.
- **Nunca se modifican los datos de entrada** para que una regla funcione.
- **El paquete oficial vive en `db/` y las ejecuciones en `runs/`; nada de eso se commitea.** La caché de extracción con modelo sí se versiona, en `backend/cache/` (por fase y hash del fichero).
- **El evaluador oficial no se copia ni se modifica**: se importa de `db/bankrec-docs-and-masters/starter/bankrec_score.py` y solo se relaja `MAX_UNCOMPRESSED` en local, porque el golden de TRAIN pesa 325 MB.
- **Ninguna lista fija de sociedades, cuentas, divisas ni formatos**: se leen de los maestros de la fase (`masters_final/` si existe) y de los datos. FINAL trae una sociedad, un banco y una divisa nuevos.
- **El golden solo existe para TRAIN.** No se intenta obtener el de LIVE ni el de FINAL.
- **Nada se envía a la clasificación sin que lo pida una persona del equipo.** LIVE tiene 20 envíos al día y FINAL uno solo. El token del equipo va en una variable de entorno, nunca en el código ni en un commit.

## 6. Reglas del frontend (`app/`)

El frontend se **descongeló** el 7 nov 2026 (docs/PLAN.md §2.3): se reescribe como plataforma operativa sobre la carpeta de ejecución y la API de CONTRACT.md §5, conservando el shell, los tokens, los componentes y el registro de vistas. Las pantallas se miran con una ejecución real de LIVE cargada, no con fixtures.

- La marca es la de Talky ([usetalky.com](https://usetalky.com)) en dos temas, claro y oscuro, que se cambian desde la barra lateral: verde bosque para el dato principal, la selección y el foco; una sola acción primaria por vista; Newsreader para titulares, Geist para el texto y Chivo Mono para ids. Los valores viven en `src/design/tokens.css` (ARCHITECTURE.md §5.4 y §5.5).
- Cada vista va dentro de la hoja del shell; su contenido son tarjetas con borde de 1 px y la sombra suave de `--shadow-card`, que crece al pasar el ratón. Lo que abre otra cosa es una tarjeta. La barra lateral es un rail que se despliega al pasar el ratón y empuja la vista.
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
| `just be-check` · `just be-test` | Lint (ruff) y tests (pytest) del backend |
| `just be-run <fase>` · `just be-score <run>` · `just be-diff <run>` | Ejecutar el backend sobre una fase; puntuarla en local con el evaluador oficial (límite de 60 MB relajado solo en local) por segmento y con la matriz de excepciones; listar los fallos por causa |
| `just be-serve <run>` | API de CONTRACT.md §5 en `localhost:8000` |
| `just holdout` | Construir `db/holdout/` y `db/holdout-drift/` desde TRAIN (docs/PLAN.md §4) |

## 8. Git

- Nunca se trabaja en `main`. Cada cambio va en una rama `KPI-<n>_<descripcion>`.
- Un commit por cambio lógico, con asunto `[KPI-<n>] type: subject` (`feat`, `fix`, `docs`, `refactor`, `test`, `chore`). Sin ámbito entre paréntesis.
- Sin `Co-Authored-By`, atribución a IA ni emojis, ni en commits ni en PR. El cuerpo de la PR es solo un resumen.
- `git push` y abrir PR, solo cuando se pida.

## 9. Al terminar

Di qué cambió, qué comprobaste (con la salida) y qué queda sin verificar. Si ves algo mejorable fuera del alcance, dilo en una línea al final.

---

**Esto funciona si:** los diffs no traen nada fuera de lo pedido, no hay que reescribir por haberlo complicado, cada cambio se parece al código que lo rodea y las dudas llegan antes de implementar, no después del error.
