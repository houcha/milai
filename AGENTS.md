# Repository Guidelines

## Project Structure & Module Organization

`src/milai/` contains the Python language tutor: `cli.py` and `web.py` provide entry points, `tutor.py` orchestrates conversations, `tools.py` exposes learning operations, and `store.py` persists session data in SQLite. Prompt templates live in `src/milai/prompts/`; browser assets live in `src/milai/web/`. Tests are in `tests/`, with shared mocks in `tests/helpers.py`. Consult `docs/architecture.md`, `docs/product.md`, and `docs/decisions.md` before changing behavior.

## Build, Test, and Development Commands

Use Python 3.12+ and uv.

- `uv sync`: install Python dependencies and development tools.
- `uv run milai chat`: start terminal chat.
- `uv run milai web`: serve the local UI at `http://127.0.0.1:8765`.
- `uv run pytest`: run the Python test suite.
- `just qa`: format Python, apply Ruff lint fixes, type-check with ty, and run pytest. This command modifies files.
- `npm ci && npm run build:web`: install frontend dependencies and rebuild the checked-in `markdown.bundle.js` after renderer changes.
- `npm run test:web`: run Markdown renderer tests with Node’s test runner; this is separate from `just qa`.
- `uv build`: build Python distribution artifacts.

## Coding Style & Naming Conventions

Use four-space Python indentation, snake_case for functions and modules, PascalCase for classes, and UPPER_CASE for constants. Follow existing type annotations and module boundaries. Ruff handles formatting, import ordering, and linting; ty checks types. Run `uv run ruff check .` for lint validation without automatic fixes. Git hooks are configured in `prek.toml`, including Ruff, YAML checks, and zizmor. Edit renderer source and regenerate its bundle instead of hand-editing generated JavaScript.

## Testing Guidelines

Name Python test files `tests/test_*.py` and test functions `test_*`. Use pytest fixtures, temporary databases, and existing model/retrieval mocks. Add regression coverage for changed behavior, especially session isolation and persistence. No numeric coverage threshold is configured. `uv run milai probe` and `uv run python -m milai.acceptance` exercise live services and require credentials.

## Interpreting Product Feedback

Treat concrete learner interactions, languages, songs, and other material mentioned
in feedback as examples of the desired behavior. Generalize the teaching principle
in production prompts and code; do not hard-code those examples into prompts unless
the user explicitly asks for that. Use concrete cases in evaluation scenarios to
check whether the general behavior works. Do not assume the example's medium or
setting applies to other learner requests.

## Commit & Pull Request Guidelines

Follow the history’s Conventional Commit pattern, such as `feat: ...`, `fix(llm): ...`, or `refactor(state): ...`. Keep changes focused. In PR descriptions, explain behavior changes, link relevant issues, and report validation commands and results. Include screenshots for visible UI changes and update affected documentation.

## Security & Configuration

Configure credentials through `.env`, using `.env.example`. Keep secrets and personal SQLite data under `.milai/` out of commits. Enable `MILAI_TRACE_CONTENT=true` only for synthetic or consented transcripts.
