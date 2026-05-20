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

## Commit Messages

All commits must follow Conventional Commits format:

```
<type>(<scope>): <subject>

[optional body] - explain why, not what

[optional footer(s)] - breaking changes, closes #issue
```

### Types

- `feat`: new feature
- `fix`: bug fix
- `docs`: documentation
- `style`: formatting, no code change
- `refactor`: code refactoring
- `test`: adding/updating tests
- `chore`: maintenance tasks
- `perf`: performance improvement
- `ci`: CI/CD changes
- `revert`: revert previous commit

### Example

Clear, specific, explains why:

```sh
git commit \
  -m "fix(api): retry requests on 503 Service Unavailable" \
  -m "The external API occasionally returns 503 errors during peak hours.
Added exponential backoff retry logic with max 3 attempts." \
  -m "Closes #123"
```
