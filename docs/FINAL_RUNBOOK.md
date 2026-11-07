# FINAL: guion de la hora (18:00–19:30)

Escrito a las 15:05 del 7 nov 2026. Una sola persona ejecuta; la orquestadora acompaña. FINAL se publica a las 18:00, hay **un solo envío**, cuenta el primer fichero válido, y un fichero con errores de formato no lo gasta. Reglas congeladas a las 17:00 (tag `freeze-final`).

Todos los comandos se lanzan **desde `backend/`, en la misma terminal**, salvo el primero (desde la raíz del repo).

## Antes de las 18:00 (17:00–17:55)

1. En el commit congelado, desde la raíz. Nada más entra en main.
   ```
   git checkout main && git pull && git tag freeze-final && cd backend
   ```
2. Ensayo de LIVE con el código congelado (llena la caché de PDFs de fases anteriores, ~3 min) y validación:
   ```
   ../scripts/run_slot.sh uv run closebooks run --phase live --out ../runs/live-freeze
   ```
   ```
   uv run closebooks validate --phase live ../runs/live-freeze/submission.csv.gz
   ```
   Si el tiempo lo permite, enviar a LIVE para confirmar la nota del código congelado (necesita `HK_TOKEN`, paso 5; gasta un envío de LIVE):
   ```
   uv run --with requests ../scripts/submit.py LIVE ../runs/live-freeze/submission.csv.gz
   ```
3. Todo verde (es la base con la que se comparará FINAL):
   ```
   uv run python ../scripts/final_check.py ../runs/live-freeze --ref ../runs/live-fraction-g
   ```
4. Parar todo lo demás: ninguna ejecución, pytest ni agente en la máquina desde las 17:55. Comprobar que no hay slots ni turnos (solo se lista `tickets`, y vacío) y que hay ≥ 12 GB libres:
   ```
   ls /tmp/closebooks-slots /tmp/closebooks-slots/tickets
   ```
   ```
   vm_stat | awk '/Pages free|Pages inactive|Pages speculative/{s+=$3} END{printf "%d GB libres\n", s*16384/1073741824}'
   ```
5. Tener a mano `HK_TOKEN` exportado en esta terminal y `db/final/` vacío:
   ```
   read -rs HK_TOKEN && export HK_TOKEN
   ```
   ```
   mkdir -p ../db/final && ls -A ../db/final
   ```

## A las 18:00 (descarga, ejecución y envío, ~10 min)

Terminal en `backend/`, con el checkout en `freeze-final` y `HK_TOKEN` exportado (§Antes). Con el paquete de FINAL descargado en `db/final/` (misma estructura que `db/live/`: bank, items, `masters_final/`, documentos), son cinco comandos, en orden, copiables uno a uno.

1. Aplanar y comprobar. El paquete de TRAIN venía anidado (`train/train/`), y entonces la fase no se encuentra; esto lo aplana si hace falta y no hace nada si no. Tienen que listarse los dos, sin error (si no trae `masters_final/`, usa los maestros del paquete: avisar a la orquestadora):
   ```
   if [ -d ../db/final/final ]; then mv ../db/final/final/* ../db/final/ && rmdir ../db/final/final; fi; ls ../db/final/bank_transactions.csv.gz ../db/final/masters_final
   ```
2. Ejecutar **una sola vez**, en primer plano, con tiempo y memoria medidos:
   ```
   ../scripts/run_slot.sh /usr/bin/time -l uv run closebooks run --phase final --out ../runs/final-a
   ```
   Esperado: 3–4 min, pico < 8 GB. `run_slot` espera si hay un slot ocupado o menos de 8 GB libres. Avisos esperables por stderr: `no FX rate for <divisa>` (ver abajo), banco nuevo fuera de la tabla de categorías (esperado). El aviso `masters_final/<fichero> has N rows` no es esperable: ver §Decisiones.
3. Validar con los límites oficiales:
   ```
   uv run closebooks validate --phase final ../runs/final-a/submission.csv.gz
   ```
   Tiene que dar `"ok": true`, `txnsCovered == txnsTotal`, y < 60 MB sin comprimir.
4. Comprobación sin golden:
   ```
   uv run python ../scripts/final_check.py ../runs/final-a --ref ../runs/live-freeze
   ```
   La referencia es la LIVE del código congelado. Si `runs/live-freeze` no existe, poner en `--ref` la última LIVE enviada, la carpeta que da `ls -t ../runs/*/live_result.json | head -1`. Leer la tabla: verde = seguir. Ámbar «banco nuevo» = esperado. Rojo: ver §Decisiones.
5. Enviar, **una sola vez**, si §Decisiones lo permite. La respuesta queda en `runs/final-a/final_result.json`. Anotar la hora. No volver a pedir URL de subida.
   ```
   uv run --with requests ../scripts/submit.py FINAL ../runs/final-a/submission.csv.gz | tee ../runs/final-a/final_result.json
   ```

Lo más probable, porque FINAL trae una divisa, un banco y una sociedad nuevos. Cualquier otro síntoma: §Decisiones.

| Síntoma en `final_check` | Acción |
| --- | --- |
| Rojo «toda divisa tiene tipo en FX» | Enviar igual: el CSV va en la divisa de la partida |
| «banco nuevo», ámbar o rojo, o rojo «todo banco con filas fuera de FALLBACK» solo en ese banco | Enviar igual: como mucho se pierden categorías de ese banco |
| Rojo o aviso de `FALLBACK` en una sola sociedad, la nueva | Enviar igual: `FALLBACK-UNIDENTIFIED` alto ahí no es fallo por sí solo, porque tiene clientes nunca vistos y no tiene historial. Mirar que el resto de sociedades estén en su línea. Si son varias familias de reglas, avisar antes de enviar |

## Decisiones si algo sale mal

| Síntoma | Qué significa | Qué hacer |
| --- | --- | --- |
| La ejecución cae con error | Un fichero o formato no previsto | Leer la traza: si es un parser de documento (`documents/`), mover la carpeta de ese formato (`pdfs` o `remittance_advices`) con `mkdir -p ../db/final-aside && mv ../db/final/pdfs ../db/final-aside/` y relanzar con `--out ../runs/final-b`: las reglas de partidas no dependen de él (no hay interruptor por variable de entorno). Si es `load`, es grave: avisar a la orquestadora, 15 min de margen |
| `validate` falla por filas o tamaño | Ningún movimiento sin fila, o CSV > 60 MB | No ocurre con 200 k movimientos; si ocurre, es un bug de duplicación: comparar `rows` con `txns` y avisar |
| Rojo «ningún masters_final más corto…» (masters parcial) | `masters_final/` trae un fichero con menos filas que el del paquete y lo pisa: faltan clientes, proveedores o tipos | Una persona lo completa y relanza **antes de enviar**: ver §Completar un maestro corto |
| Rojo «divisa sin tipo» | La divisa nueva no está en FX: importes en euros ×1 | No afecta al CSV (los importes van en la divisa de la partida); afecta solo a límites de comisiones y prioridad de casos. Enviar igual |
| Rojo «banco nuevo 100 % BANK_FEES» | El arreglo del banco nuevo no actúa | Los cargos sin partida de ese banco salen como comisiones: pérdida acotada (categorías de un banco), enviar igual |
| Rojo en reparto de reglas (> 3 puntos frente a LIVE) en una sola sociedad | Formato de avisos o extracto nuevo | Mirar `byRule` de esa sociedad; si es FALLBACK masivo, aceptar: FINAL trae sociedad nueva sin historial. Enviar igual |
| Rojo generalizado (varias familias de reglas desaparecen) | Bug serio | Avisar a la orquestadora antes de enviar; margen hasta las 19:20 para un segundo run con una regla desactivada |

Regla de oro: **se envía el primer fichero que valide**, salvo rojo generalizado o masters parcial. Un fichero válido mediocre puntúa; ninguno no.

### Completar un maestro corto

Un fichero con menos filas no se sobrescribe con el del paquete (se perderían los clientes nuevos): se completa con las filas de `db/bankrec-docs-and-masters/masters/` que no estén, conservando las de `masters_final/`. Un fichero que falte no da rojo: la carga ya lo lee de `masters/`, y copiarlo es opcional.

Poner en `F` el fichero del rojo y en `K` su clave: `customers` `customer_id`, `suppliers` `supplier_id`, `bank_accounts` `account_id`, `entities` `entity`, `categories` `category`, `payment_terms` `code`, `fx_rates` `date,currency`.

```
export F=customers K=customer_id
```
```
mkdir -p ../db/final-aside && cp ../db/final/masters_final/$F.csv ../db/final-aside/ && uv run python -c '
import os, polars as pl
F, K = os.environ["F"], os.environ["K"].split(",")
path = f"../db/final/masters_final/{F}.csv"
final = pl.read_csv(path, infer_schema_length=0)
base = pl.read_csv(f"../db/bankrec-docs-and-masters/masters/{F}.csv", infer_schema_length=0)
merged = pl.concat([final, base.join(final, on=K, how="anti")], how="diagonal")
merged.write_csv(path)
print(F, final.height, "->", merged.height)'
```

Repetir por cada fichero en rojo, relanzar con `--out ../runs/final-b` y repetir la validación, la comprobación y el envío sobre `final-b`.

## Después (19:00–19:45)

Entrega del proyecto: repo en main con `freeze-final`, vídeo y descripción (`docs/SUBMISSION.md`), con las cifras del ensayo de LIVE congelado.


## Cambio de método (17:05): sin congelación, dos candidatos

No hay congelación de reglas. En su lugar:

1. **Candidato A (seguro).** A las 18:00, con el main que haya (tag `final-candidate-a`), se ejecuta FINAL inmediatamente (`runs/final-a`), se valida y se pasa `final_check`. Es el fichero que se envía si nada mejor llega a tiempo.
2. **Mejoras después de las 18:00.** Las PR siguen entrando en main solo con la puerta completa en holdout y drift (FINAL no tiene golden: nada se mide sobre FINAL). Cada entrada relevante produce un **candidato B** (`runs/final-b`, tag `final-candidate-b`) con la misma secuencia: run, validate, `final_check --ref ../runs/final-a` además de `--ref ../runs/live-freeze`.
3. **Decisión de envío (19:00 como muy tarde, para enviar antes de las 19:20):** se envía B solo si (a) validate ok, (b) `final_check` frente a A muestra solo los cambios esperados (las reglas nuevas suben, nada baja, ninguna sociedad cambia de reparto fuera de esas reglas) y (c) todas las PR entre A y B pasaron holdout **y** drift. Si falta cualquiera, se envía A. Nunca se envían los dos: FINAL admite un solo envío.
4. **Máquina:** desde las 17:55 un slot queda reservado para FINAL (candidatos A y B); las mediciones de reglas usan el otro.
