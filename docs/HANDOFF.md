# HANDOFF.md: la plataforma el día del evento

Cómo arrancar la plataforma, qué mirar antes de grabar y qué hacer si algo falla. Solo la parte de `app/` y su API. Medido en este portátil la mañana del 7 nov 2026, con `live-kpi6-api3` (203.083 movimientos, 642.362 filas).

## Arrancar

**Arranca `serve` 2 minutos antes de usarlo:** tarda unos 53 s en aceptar conexiones, porque no abre hasta precargar la ejecución, y ocupa unos 3,7 GB. Después responde en menos de 250 ms.

```bash
just be-serve runs/<la ejecución a enseñar>
```

```bash
just fe-install
```

```bash
just fe-dev
```

Abre la dirección que imprime Vite, normalmente <http://localhost:5173>.

| Qué | Dónde |
| --- | --- |
| API | `http://localhost:8000` |
| App | Puerto de Vite. `/api` va a :8000; con `API_URL` a otro servidor |
| Servidor de prueba, sin datos reales | `npm --prefix app run mock`, en :8000, con `app/fixtures/run-sample/` |

La app abre la ejecución con la que arrancó `serve`. Otra se abre con `?run=<id>` o desde Ejecuciones. **`runs/` es compartida y trae carpetas de agentes con código a medias:** usa solo las rutas que se hayan dado por buenas.

## Qué mirar antes de grabar

1. La barra lateral enseña la ejecución correcta y no dice «Sin conexión con la API».
2. El titular del Resumen da cifras razonables. Sácalas con `node app/mock/figures.mjs` para rellenar `docs/DEMO.md` y `docs/SUBMISSION.md`.
3. Bandeja: hay preguntas (`wc -l runs/<id>/questions.jsonl`) y borradores (`drafts.jsonl`). Sin ellos no se pueden grabar los pasos 3 y 4 de [DEMO.md](DEMO.md).
4. Cobros: algún cliente tiene caso de cobro. Si no, se graba la variante B de DEMO.md.
5. Consola limpia: `Cmd+Opt+J` en Chrome. «Preparar correo» da un error 501 hasta que exista el generador de borradores, y eso se ve en consola; no lo pulses en el vídeo si no hay generador.
6. **Grabar escribe en `runs/<id>/human/`:** responder, enviar y marcar gestionado se quedan. Para ensayar, usa una copia de la carpeta.
7. **El correo no sale:** queda en `human/outbox.jsonl`. El vídeo debe decirlo.

## Comprobar las tres interacciones

Guion que pulsa los tres recorridos en un navegador real y comprueba lo que queda en `human/`. Necesita Playwright instalado fuera del repo y **una copia de la carpeta**, porque escribe de verdad:

```bash
cp -R runs/<id> runs/<id>-ensayo
```

```bash
just be-serve runs/<id>-ensayo
```

```bash
PLAYWRIGHT=<dir>/node_modules/playwright/index.mjs node app/mock/interactions.mjs http://localhost:5173 --run <id>-ensayo --human runs/<id>-ensayo/human
```

Al terminar, borra la copia para que no salga en el historial de Ejecuciones.

## Capturas finales

Con `serve` y la app arrancados, las nueve pantallas y sus paneles en los dos temas:

```bash
PLAYWRIGHT=<dir>/node_modules/playwright/index.mjs node app/mock/capture.mjs http://localhost:5173 docs/screenshots/final
```

## Si algo falla

| Qué pasa | Qué hacer |
| --- | --- |
| «Sin conexión con la API» | `serve` no está arrancado o sigue precargando: espera un minuto y recarga |
| «No existe la ejecución» | Quita `?run=` de la URL |
| Pantalla vacía tras cambiar de rama | Vite se quedó con dependencias viejas: `just fe-install`, reinicia `just fe-dev` y recarga |
| La máquina se queda sin memoria | Una sola carga pesada a la vez: `serve` ocupa cerca de 4 GB y el Mac ya se reinició dos veces por memoria |

## Qué no está probado

- Pregunta y correo con datos reales: solo con el servidor de prueba, hasta que haya una ejecución con preguntas y borradores.
- Una regla aplicada en una ejecución posterior (`--memory`).
- Consola FINAL: subir un zip real, una ejecución fallida y una validación con errores.
- Lector de pantalla real.
