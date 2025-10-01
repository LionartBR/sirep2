# Repository Guidelines

## Project Structure & Module Organization
- `domain/`: immutable business models and rules; framework‑free; prefer `@dataclass(frozen=True)`.
- `services/`: orchestrate domain logic; depend on domain interfaces; no infra details.
- `infra/`: adapters for DB/queues/external services; env‑driven config.
- `api/`: FastAPI app factory, routers, and dependencies; delegate to services.
- `ui/`: static web app; capture before/after screenshots when UI changes.
- `tests/`: pytest suites mirroring source; shared fixtures in `conftest.py`.
- `scripts/`: auxiliary CLIs; document in `docs/` when added.

## Build, Test, and Development Commands
- Start API: `uvicorn api.app:create_app --reload`
- Run tests: `pytest`
- Lint: `ruff check .` | Format: `ruff format .`
- Type check: `mypy .`
Run all from repo root.

## Coding Style & Naming Conventions
- PEP 8, 4‑space indentation, descriptive English identifiers (UI strings may be Portuguese).
- Full type hints for public APIs and module state.
- Domain models: `@dataclass(frozen=True)` or tuples.
- Imports grouped: stdlib, third‑party, project (blank lines between).
- Docstring public modules/classes/functions with purpose and contracts.

## Testing Guidelines
- Name by behavior, e.g., `test_service_returns_error_on_missing_case`.
- Cover success and failure paths, including async branches.
- Keep data deterministic; refresh snapshots/golden files deliberately.

## Commit & Pull Request Guidelines
- Commits: imperative mood summarizing the primary change; avoid mixing refactors with new behavior unless justified.
- Keep branches current with `main`; resolve conflicts locally.
- Before pushing: `ruff check .`, `ruff format .`, `mypy .`, `pytest`; note status in PR description.
- Use `make_pr` to generate titles/bodies; document contract changes, rollout steps, and required screenshots.

## Security & Configuration
- Never commit secrets. Load credentials via environment variables in `infra/`.
- Put defaults in `.env.example` or docs; do not hard‑code config.

## Agent‑Specific Notes
- Scope: this file applies repo‑wide; nested `AGENTS.md` takes precedence.
- Keep changes minimal and focused; follow the structure above and update tests/docs with behavior changes.

