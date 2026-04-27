## Toolchain

Use `uv` for all Python commands. Never invoke `python`, `pip`, or `pip install` directly.

| Task | Command |
|------|---------|
| Full QA (format + lint + type-check + test) | `just qa` |
| Type-check | `just type-check` |
| Type-check (concise) | `just type-check-concise` |
| Run tests | `uv run pytest` |
| Pre-commit | `prek run` |
| Add dependency | `uv add <package>` |
| Add dev dependency | `uv add --dev <package>` |

Pre-commit hooks must always pass. Never use `--no-verify`. Fix the root cause when a hook fails.

## Git Workflow

All commits must follow Conventional Commits format: `<type>(<scope>): <description>`

Types: `feat`, `fix`, `test`, `docs`, `refactor`, `chore`, `perf`, `ops`

- One logical change per commit; unrelated changes go in separate commits and branches
- **IMPORTANT**: Commit messages must communicate **why the change was made** and its **intent and impact**, not a mechanical summary of the diff.
    - Subject: concise outcome-focused summary.
    - Body: explain the WHY when context is needed, using a second `-m`.
    - YES: `git commit -m "docs(agents): help agents write outcome-focused commits" -m "Agents tend to produce generic descriptions that don't explain why a change was made. This commit clarifies that commit messages should communicate intent and impact instead of summarizing the diff."`
    - NO: `git commit -m "docs(agents): clarify commit message intent"`
