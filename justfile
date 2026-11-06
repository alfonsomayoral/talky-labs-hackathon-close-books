# Comandos del repo. `just --list` para verlos.

# Servidor de desarrollo del frontend
fe-dev:
    npm --prefix app run dev

# Typecheck, lint, test y build del frontend
fe-check:
    npm --prefix app run typecheck
    npm --prefix app run lint
    npm --prefix app run test
    npm --prefix app run build

# Instala las dependencias del frontend
fe-install:
    npm --prefix app ci

# Lint (ruff) del backend
be-check:
    cd backend && uv run ruff check .

# Tests del backend
be-test:
    cd backend && uv run pytest

# Ejecuta el backend sobre una fase: just be-run sample
be-run phase:
    cd backend && uv run closebooks run --phase {{phase}}

# Puntúa una ejecución con el evaluador oficial: just be-score <run> [--compare <run>]
be-score run *args:
    cd backend && uv run closebooks score {{run}} {{args}}

# Lista los fallos de una ejecución por segmento y causa: just be-diff <run> [--segment S]
be-diff run *args:
    cd backend && uv run closebooks diff {{run}} {{args}}

# API de CONTRACT.md §5 en localhost:8000 sobre una ejecución: just be-serve <run>
be-serve run="":
    cd backend && uv run closebooks serve {{run}}

# Construye db/holdout/ y db/holdout-drift/ desde TRAIN
holdout:
    cd backend && uv run closebooks holdout build
    cd backend && uv run closebooks holdout build --drift
