# STATUS.md — estado de la noche del 6 al 7 de noviembre

Lo mantiene la sesión orquestadora cada hora. Léelo al despertar.

| Hora | main · TRAIN | main · holdout | Backend | Frontend | PRs fusionadas | Bloqueos / decisiones tomadas |
| --- | --- | --- | --- | --- | --- | --- |
| 00:30 | 11,68 (starter) | — | sin arrancar | sin arrancar | — | Plan aprobado; contrato v2 y briefs en `main` |
| 00:10 | 2,26 (todo FALLBACK, rama be-core; main sin backend) | 2,29 | P0 escrito, PR 9 devuelta por CI (2 tests sin db/); empieza P1 (R1, R6) | P0 fusionado, Resumen fusionado, 4 agentes en Conciliación, Bandeja, Cuentas+Explorador, Ejecuciones; Vite en :5190 | 4, 5, 6, 7, 8 | Contrato v2.1 (§5.1 formas, filtros con coma, csvBytes). Límites del evaluador relajados solo al puntuar. Fórmula de open_items confinada al holdout con test de reproducción. Primera ejecución LIVE: runs/live-20261106-235516 (todo FALLBACK) |
| 00:15 | 28,54 en rama be (R1 remesas de pago; main sin reglas aún) | 2,29 | PR 9 fusionada; R1 en curso (FILE-PAYMENT-RUN ya casa 1,04 M filas); R6 pendiente | En main: Resumen, Conciliación, Cuentas, Explorador, Memoria. Bandeja y Ejecuciones terminadas pero sin PR (agentes sin permiso de push/PR: necesita al usuario). PR 13 Cobros y PR 17 Proveedores apiladas sobre la Bandeja | 9, 10, 11, 12, 14, 15, 16 | Contrato: importes de caso en magnitud, sort compuesto, statementFormat, affectedTxns. Impeccable: crítica completa en la pasada global de P4. Ramas remotas obsoletas KPI-7_fe-data/-inbox/-overview: borrar por el usuario |
