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

Hoy solo hay frontend: arranca solo, sin backend ni ficheros de datos, con los **datos de muestra** que genera el propio código (`app/src/data/fixtures/sample.ts`).

**Necesitas:** acceso al repo (es privado: pide que te añadan como colaborador), Git y Node 22. [`just`](https://github.com/casey/just) es opcional.

```bash
git clone https://github.com/alfonsomayoral/talky-labs-hackathon-close-books.git
```

```bash
cd talky-labs-hackathon-close-books
```

Mientras no se fusione en `main`, el trabajo está en la rama `KPI-1_phase-0-frontend`:

```bash
git switch KPI-1_phase-0-frontend
```

Instala y arranca (con `just`, o con `npm` desde `app/`):

```bash
just fe-install && just fe-dev
```

```bash
cd app && npm ci && npm run dev
```

Abre la dirección que imprime Vite, normalmente <http://localhost:5173>. Verás el «Grupo Aurelia (muestra)» con sus alertas.

### Con los datos reales

- **El zip del cliente:** en la app, «Importar datos» (abajo en la barra lateral) y arrástralo. Se lee en el navegador; nada se sube a ningún servidor. Recargar la página vuelve a los datos de muestra.
- **Si no reconoce algún fichero:** aparece en «Ficheros sin reconocer». Se adapta en `app/src/data/registry/mappings.ts` (ver [ARCHITECTURE.md](ARCHITECTURE.md) §4.2).
- **Dónde guardarlo:** en `data/`, que git ignora. Los datos del cliente nunca se commitean; compártelos por otro canal.

### Comprobaciones

```bash
just fe-check
```

Pasa typecheck, lint, tests y build. Sin `just`, desde `app/`: `npm run typecheck`, `npm run lint`, `npm run test` y `npm run build`.

### Backend

`backend/` está vacío: se monta el día del evento y entregará al frontend el formato de [CONTRACT.md](CONTRACT.md).
