# Langfuse CLI Reference

Documentation: https://langfuse.com/docs/api-and-data-platform/features/cli

## Run and discover commands

```bash
npx @langfuse/cli api help
npx @langfuse/cli api help <resource>
npx @langfuse/cli api help <resource> <action>
npx @langfuse/cli api schema --json
```

The CLI reads `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_BASE_URL` from its environment. If this repository's ignored `.env` holds the keys, pass them into the process environment without printing them. The CLI does not load `.env` automatically.

## Match a self-hosted server

Use `--api-version auto` to select a bundled API snapshot from the server's health endpoint. Set `--host` to the server URL when needed. For example:

```bash
npx @langfuse/cli --api-version auto --host http://localhost:3000 api observations list --limit 1 --fields core,basic --json
```

The example queries observation metadata without input/output content. Use `api versions list` to inspect bundled snapshots if auto-detection fails. Check the server version at `/api/public/health` before choosing a historical snapshot manually.

## Output and filtering

- Use `--json` for a stable envelope with `status`, `headers`, and `body` fields.
- Inspect `api help <resource> <action>` for filters and pagination. Filter and limit results before bringing trace content into the conversation.
- Use `--curl` to preview a request without executing it.
