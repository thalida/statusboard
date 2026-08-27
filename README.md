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

Each worktree gets its own ports, database and admin account. Ports are
saved to `.local/worktree-ports.json`. Run `just info` to see them.

`just init` copies `.env` from the main checkout when there is one.
Otherwise it asks for the admin credentials.

Run tests with `just test`, not `pytest` — the database port is
per-worktree, and only the `just` recipes know it.
