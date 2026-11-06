# Close the Books

Agente de cierre contable y conciliación bancaria para el **Claude Code Hackathon — Close the Books** (Madrid, 7 nov 2026). Reto y datos de Talky.

| Documento | Qué tiene |
| --- | --- |
| [PROBLEM.md](PROBLEM.md) | El reto: qué entra, qué se evalúa y qué falta por saber |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Cómo está construido el repo y por qué |
| [CONTRACT.md](CONTRACT.md) | El `Run`: lo que el backend entrega al frontend |
| [CLAUDE.md](CLAUDE.md) | Cómo se trabaja en el repo |

## Estado

**Fase 0:** el frontend (`app/`) con datos de muestra de un grupo de cuatro sociedades y una ejecución de muestra con las anomalías del reto. Importa el zip del cliente en el navegador. El backend (`backend/`) se monta el día del evento.

## Puesta en marcha

Requiere Node 22 y [`just`](https://github.com/casey/just).

```bash
just fe-install
just fe-dev
```

`just fe-check` pasa typecheck, lint, tests y build.
