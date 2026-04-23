# Show available commands
list:
    @just --list

# Type check the project with ty
type-check:
    uv run ty check .

# Type check with concise output (one diagnostic per line)
type-check-concise:
    uv run ty check --output-format=concise .

# Run all the formatting, linting, and testing commands
qa:
    uv run ruff format .
    uv run ruff check . --fix
    uv run ty check --output-format=concise .
    uv run pytest

