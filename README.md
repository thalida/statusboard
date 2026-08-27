# Statusboard

## Requirements

- Docker
- [`just`](https://just.systems)
- [`uv`](https://docs.astral.sh/uv/)

## Development

### Running locally

```bash
just init
just serve
```

`just init` starts the services, installs dependencies, applies migrations,
seeds the dev admin, and installs the pre-commit hooks.

`just serve` prints the URL.

Run `just` on its own to list every recipe.

### Worktree isolation

Each worktree gets its own ports and its own database. Ports are saved to
`.local/worktree-ports.json`. Run `just info` to see this worktree's values.

A new worktree starts with an empty database, so it needs its own admin.
`just init` asks for one. It reuses the main checkout's `.env` if there is
one, so the credentials are entered once.

Run tests with `just test`, not `pytest` — the database port is
per-worktree, and only the `just` recipes know it.
