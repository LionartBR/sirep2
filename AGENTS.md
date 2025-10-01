# Repository Guidelines

## Project Structure & Module Organization
- `domain/` hosts immutable business models and rules; keep them framework-free.
- `services/` orchestrates domain logic and talks to infrastructure via domain-defined interfaces.
- `infra/` contains adapters for databases, queues, and external services; prefer environment-driven config.
- `api/` exposes FastAPI routers and dependencies; delegate logic to services.
- `ui/` serves the static web app; capture before/after screenshots when UI changes.
- `tests/` mirrors the source layout with pytest suites and shared fixtures in `conftest.py`.

## Build, Test, and Development Commands
- `uvicorn api.app:create_app --reload` spins up the local FastAPI server with auto-reload.
- `pytest` runs the unit and integration test suite.
- `ruff check .` and `ruff format .` enforce linting and formatting.
- `mypy .` validates typing across the project.
- `scripts/` holds auxiliary CLIs; document any new script in `docs/`.

## Coding Style & Naming Conventions
- Follow PEP 8 with 4-space indentation and descriptive English identifiers (UI strings may stay in Portuguese).
- Apply complete type hints to public functions, methods, and module-level state.
- Prefer `@dataclass(frozen=True)` or tuples for domain models to keep immutability explicit.
- Group imports by stdlib, third-party, and project modules, separated by blank lines.
- Document public modules, classes, and functions with concise docstrings describing purpose and contracts.

## Testing Guidelines
- Name tests after the behavior under test (e.g., `test_service_returns_error_on_missing_case`).
- Cover both success and failure branches for asynchronous paths.
- Refresh golden files or snapshots deliberately; keep deterministic data.
- Target meaningful coverage and ensure new behaviors ship with focused tests.

## Commit & Pull Request Guidelines
- Write imperative commit messages summarizing the primary change; avoid mixing refactors with new behavior unless justified.
- Keep branches current with `main` and resolve conflicts locally before opening a PR.
- Run linting, typing, and test commands before pushing; note their status in the PR description.
- Use the `make_pr` helper to generate PR titles/bodies, and document contract changes, rollout steps, and any required screenshots.

## Security & Configuration Notes
- Never commit secrets; load credentials through environment variables consumed in `infra/` components.
- Store configuration defaults in `.env.example` or documentation rather than source code.
