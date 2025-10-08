# Repository Guidelines

## Rules
- `context7-mcp/` Always use context7 when I need code generation, setup or configuration steps, or
library/API documentation. This means you should automatically use the Context7 MCP
tools to resolve library id and get library docs without me having to explicitly ask.

## Project Structure & Module Organization
- `domain/` holds immutable business rules (use `@dataclass(frozen=True)`), no framework imports.
- `services/` orchestrates domain flows and talks to adapters defined via domain interfaces.
- `infra/` implements DB, queue, and external service adapters; configuration comes from env vars.
- `api/` exposes FastAPI routers, including `/api/treatment/migrate` and `/api/treatment/plans`; defer logic to services.
- `ui/` bundles the static frontend; capture before/after screenshots whenever UI behavior shifts.
- `app/` and `shared/` provide cross-cutting helpers (auth, logging, utilities) reused across layers.
- `tests/` mirrors the tree with pytest suites; shared fixtures live beside `conftest.py`.
- `scripts/` hosts CLI utilities; document new scripts under `docs/`.

## Build, Test, and Development Commands
- `uvicorn api.app:create_app --reload` spins up the API for local iteration.
- `pytest` runs unit and integration suites; reproduce filter scenarios against mocked views.
- `ruff check .` and `ruff format .` enforce linting/formatting; run before committing.
- `mypy .` validates typing across API, services, and infra modules.
- Install dev deps (`pip install -e .[dev]`) and hooks (`pre-commit install`) to mirror CI.

## Coding Style & Naming Conventions
- Follow PEP 8 with 4-space indentation and expressive English identifiers; UI strings may stay in PT-BR.
- Fully type public functions, service facades, and module constants.
- Group imports by stdlib / third-party / project with blank lines; keep docstrings concise and task-focused.

## Testing Guidelines
- Name tests by behavior (`test_service_returns_error_on_missing_case`).
- Cover async success/failure paths, especially plan migration and filter combinations.
- Keep fixtures deterministic; refresh snapshots intentionally.

## Commit & Pull Request Guidelines
- Use imperative commit titles, scoped to a single logical change.
- Rebase onto `main`, resolve conflicts locally, and run `ruff`, `mypy`, and `pytest` before pushing.
- PRs should capture rollout notes, contract changes, required screenshots, and the status of the Treatment KPIs.

## Security & Feature Notes
- Never hard-code secrets; load env-driven config in `infra/`.
- Plan migration currently imports all `P_RESCISAO` entries via `app.vw_planos_busca`; ask product before altering scope.
- Execute migrations synchronously, avoid duplicate inserts silently, refresh the Treatment table and KPIs (Status, Last updated, Duration) after success, and render `"Pág. 1 de 1"` when pagination metadata is missing.
- Implement filters server-side with parameterized SQL using `app.vw_planos_busca` (situations, delay buckets, saldo ranges, date windows) before applying keyset pagination, and surface active selections as UI chips.
