# FINAL: guion de la hora (18:00–19:30)

Escrito a las 15:05 del 7 nov 2026. Una sola persona ejecuta; la orquestadora acompaña. FINAL se publica a las 18:00, hay **un solo envío**, cuenta el primer fichero válido, y un fichero con errores de formato no lo gasta. Reglas congeladas a las 17:00 (tag `freeze-final`).

## Antes de las 18:00 (17:00–17:55)

1. `git checkout main && git pull` y `git tag freeze-final` en el commit congelado. Nada más entra en main.
2. Ensayo de LIVE con el código congelado: `scripts/run_slot.sh just be-run live` con `--out runs/live-freeze` (llena la caché de PDFs de fases anteriores, ~3 min). Validar y, si el tiempo lo permite, enviar a LIVE para confirmar la nota del código congelado.
3. `python scripts/final_check.py runs/live-freeze --base runs/live-fraction-g` → todo verde (es la base con la que se comparará FINAL).
4. Parar todo lo demás: ninguna ejecución, pytest ni agente en la máquina desde las 17:55. Comprobar `ls /tmp/closebooks-slots` vacío y ≥ 12 GB libres.
5. Tener a mano: `HK_TOKEN` exportado en la terminal (`read -rs HK_TOKEN && export HK_TOKEN`), `db/final/` vacío y listo.

## A las 18:00 (descarga y ejecución, ~10 min)

1. Descargar el paquete de FINAL a `db/final/` con la misma estructura que `db/live/` (bank, items, masters o `masters_final/`, documentos). Comprobar `ls db/final` y que `masters_final/` existe si lo trae.
2. Ejecutar **una sola vez**, en primer plano, con tiempo y memoria medidos:
   ```
   cd backend && /usr/bin/time -l uv run closebooks run --phase final --out ../runs/final-a
   ```
   Esperado: 3–4 min, pico < 8 GB. Avisos esperables por stderr: `no FX rate for <divisa>` (ver abajo), banco nuevo fuera de la tabla de categorías (esperado).
3. Validar con los límites oficiales:
   ```
   uv run closebooks validate --phase final ../runs/final-a/submission.csv.gz
   ```
   Tiene que dar `"ok": true`, `txnsCovered == txnsTotal`, y < 60 MB sin comprimir.
4. Comprobación sin golden:
   ```
   python scripts/final_check.py runs/final-a --base runs/live-fraction-g
   ```
   Leer la tabla: verde = seguir. Ámbar «banco nuevo» = esperado. Rojo: ver §Decisiones.

## Decisiones si algo sale mal

| Síntoma | Qué significa | Qué hacer |
| --- | --- | --- |
| La ejecución cae con error | Un fichero o formato no previsto | Leer la traza: si es un parser de documento (`documents/`), mover la carpeta de ese formato fuera de `db/final/documents` (a `db/final-aside/`) y relanzar: las reglas de partidas no dependen de él (no hay interruptor por variable de entorno). Si es `load`, es grave: avisar a la orquestadora, 15 min de margen |
| `validate` falla por filas o tamaño | Ningún movimiento sin fila, o CSV > 60 MB | No ocurre con 200 k movimientos; si ocurre, es un bug de duplicación: comparar `rows` con `txns` y avisar |
| Rojo «divisa sin tipo» | La divisa nueva no está en FX: importes en euros ×1 | No afecta al CSV (los importes van en la divisa de la partida); afecta solo a límites de comisiones y prioridad de casos. Enviar igual |
| Rojo «banco nuevo 100 % BANK_FEES» | El arreglo del banco nuevo no actúa | Los cargos sin partida de ese banco salen como comisiones: pérdida acotada (categorías de un banco), enviar igual |
| Rojo en reparto de reglas (> 3 puntos frente a LIVE) en una sola sociedad | Formato de avisos o extracto nuevo | Mirar `byRule` de esa sociedad; si es FALLBACK masivo, aceptar: FINAL trae sociedad nueva sin historial. Enviar igual |
| Rojo generalizado (varias familias de reglas desaparecen) | Bug serio | Avisar a la orquestadora antes de enviar; margen hasta las 19:20 para un segundo run con una regla desactivada |

Regla de oro: **se envía el primer fichero que valide**, salvo rojo generalizado. Un fichero válido mediocre puntúa; ninguno no.

## Envío (una sola vez)

```
uv run --with requests scripts/submit.py FINAL runs/final-a/submission.csv.gz
```

Guardar la respuesta en `runs/final-a/final_result.json`. Anotar la hora. No volver a pedir URL de subida.

## Después (19:00–19:45)

Entrega del proyecto: repo en main con `freeze-final`, vídeo y descripción (`docs/SUBMISSION.md`), con las cifras del ensayo de LIVE congelado.
