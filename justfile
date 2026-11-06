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
