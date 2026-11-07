# HANDOFF.md: la plataforma el día del evento

Cómo arrancar la plataforma, qué mirar antes de grabar y qué hacer si algo falla. Solo la parte de `app/` y su API. Medido en este portátil la mañana del 7 nov 2026, con `live-kpi6-cases2` (203.083 movimientos, 692.609 filas).

## Arrancar

**Arranca `serve` 2 minutos antes de usarlo:** tarda unos 64 s en aceptar conexiones, porque no abre hasta precargar la ejecución, y ocupa unos 4 GB. Después, las nueve pantallas abren en menos de 1,1 s.

```bash
just be-serve runs/<la ejecución a enseñar>
```

```bash
just fe-install
```

```bash
just fe-dev
```

Abre la dirección que imprime Vite, normalmente <http://localhost:5173>. Si el 5173 está ocupado, Vite elige otro.

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

- Una regla aplicada en una ejecución posterior (`--memory`).
- Lector de pantalla real.

## Qué está probado con datos reales

- Las tres interacciones contra `serve` de `main`, con una copia de `live-kpi6-cases2`, 14 de 14 con `interactions.mjs`: pregunta con regla, correo editado y «enviado», marcar gestionado. Lo escrito en `human/` se comprobó línea a línea.
- Las nueve pantallas, build de producción: menos de 1,1 s justo tras arrancar `serve` y después, cero errores de consola.
- «Preparar correo» y «Lo llevo yo» también con una copia de `live-kpi6-cases2`. «Lo llevo yo» registra el borrador como `manual` y cierra el caso.
- Consola FINAL, ejecución fallida y validación con errores: enseñan el mensaje y dejan empezar otra. La fallida, también con un fallo real: un zip con datos rotos. Se enseña la causa, no el traceback. Un zip sin `bank_transactions.csv.gz` se rechaza al subir; ese 422 sale en la consola del navegador. La validación con errores, solo forzando la respuesta.
- Consola FINAL con un zip: el contenido de `sample` en un zip, subido, ejecutado en 3,8 s y validado (8.499 de 8.499 movimientos, 1,1 MB de 60 MB). Sale el nombre del zip como fase. Lo escrito en `db/<zip>/` y `runs/<zip>-…/` se queda: hay que borrarlo a mano tras ensayar.
- `Draft.to` es `null` porque el maestro no trae correos: «Para» enseña el nombre y avisa. No se puede corregir la dirección: `PUT …/drafts` solo guarda asunto y cuerpo.

## Backend

Todo se ejecuta desde `backend/` con `uv`. Código en `backend/src/closebooks/`; `backend/README.md` tiene los comandos y la nota de memoria.

### Una sola medición pesada a la vez

La noche del 6 al 7 hubo dos pánicos de kernel con la memoria agotada por procesos Python, sin identificar cuál. Por eso:

- No lances dos ejecuciones a la vez, ni TRAIN con `serve` y el navegador arriba.
- Lo largo, con `nohup` y salida a fichero: una sesión cortada no lo pierde.
- Mide el pico con `/usr/bin/time -l`; `run.json` trae además `peakRssMb` por etapa.

### Ejecutar y medir

```bash
uv run closebooks run --phase live --out ../runs/live-envio
```

```bash
uv run closebooks validate ../runs/live-envio/submission.csv.gz --phase live
```

```bash
uv run closebooks score ../runs/holdout-a --compare ../runs/holdout-b
```

```bash
uv run closebooks diff ../runs/holdout-a --segment ar_ref_noise
```

```bash
uv run closebooks serve ../runs/live-envio
```

`validate` aplica los límites oficiales (60 MB); `score` los relaja para poder puntuar TRAIN. Usa siempre `--out`: `runs/` es compartida y lo más reciente puede ser de otra ejecución.

### El día de FINAL

1. Descomprime en `db/final/`, con `masters_final/` dentro. `load` lo prefiere sobre los maestros del paquete y lee `db/train` y `db/live` como fases anteriores.
2. Sube a mano los ficheros si `db/final` no tiene la forma esperada: `phase_dir` busca `bank_transactions.csv.gz`.
3. `run --phase final --out ../runs/final-1`, y compara `byRule` con LIVE en `run.json`: ZA01 no puede salir todo `UNIDENTIFIED`.
4. `validate`, y que el envío lo haga **una persona**. Ninguna herramienta del repo envía nada.

### Dónde está cada cosa

| Pieza | Fichero |
| --- | --- |
| Reglas con fichero | `rules/payment_runs.py`, `dd_batches.py`, `card_settlements.py`, `cheque_deposits.py`, `advices.py` |
| Motor por fecha (tercero, saldo, números) | `rules/party_amount.py`, `rules/parties.py` |
| Categorías | `rules/categories.py`, `data/category_codes.csv` |
| Importe y excepción | `policy.py` |
| Hechos de documentos | `documents/advices.py`, `documents/pdfs.py` (parsers, sin modelo) |
| Casos, preguntas, borradores | `cases.py`, `drafts.py` |
| API | `api/` |

### Lo que no hay

- `memory.py` no existe: `--memory` no está en `closebooks run`, así que las reglas guardadas en `human/` **no se aplican todavía** en la ejecución siguiente.
- El proveedor de modelo y su caché no están hechos: toda la extracción es por parsers. No hay ninguna llamada a modelo.
- `facts/parties.parquet` va vacío.
- El holdout mutado no incluye el drift (d), avisos reescritos al xlsx nuevo, y ZA01 conserva la numeración original en avisos y PDFs.
