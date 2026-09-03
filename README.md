# Statusboard

## Requirements

- Docker
- [`just`](https://just.systems)
- [`uv`](https://docs.astral.sh/uv/)

## Development

### Running locally

```bash
just init
just dev
```

`just init` starts the services, installs dependencies, applies migrations,
seeds the dev admin, and installs the pre-commit hooks.

`just dev` runs the server and the poller together, and prints the URL.
Nothing refreshes without the poller, so they are one command.

Run `just` on its own to list every recipe.

### Worktree isolation

Each worktree gets its own ports, database and admin account. Ports are
saved to `.local/worktree-ports.json`. Run `just info` to see them.

`just init` copies `.env.local` from the main checkout when there is one.
Otherwise it asks for the admin credentials.

Run tests with `just test`, not `pytest` — the database port is
per-worktree, and only the `just` recipes know it.

### Before a pull request

```bash
just check
```

It builds the deployment image and runs every check CI runs, inside it:
the suite against a real Postgres, lint, the docs cross-check, the prose
rules and a missing-migration check.

`just test` is the fast loop and runs on the host. `just check` is the one
that proves the image.

### Checking the status pages we can read

Status pages are somebody else's software. They get rebuilt, moved to
another platform, or retired, and the first sign is a service that quietly
stops updating.

```bash
just check-pages
```

It probes every page in `api/polling/data/status_pages.json` and fails if
one stopped working or changed platform. A page that started working is
reported and is never a failure. `just check-pages --update` records what
they serve today.

It reaches the live internet, so it is a command rather than a test — the
suite blocks sockets on purpose.

## Deployment

`api.statusboard.dev` runs as one stack behind Traefik: the API, the
poller, its scheduler, Postgres and Redis. Four of those are this one
image, told apart by the argument. See `api/entrypoint.sh`.

The stack itself lives in the `deploy-pipeline` repository, under
`app-statusboard/`. Its `compose.yml` says how the services fit
together, and `.env.example` lists the settings they need.

### Releasing

A `v*` tag builds the image, signs it, smoke tests it against a real
Postgres, and asks the deploy pipeline to bring the stack up.

```bash
git tag v0.1.0 && git push origin v0.1.0
```

GitHub needs three secrets and one variable.

| Name | Kind | Value |
| --- | --- | --- |
| `FORGEJO_HOST` | secret | The Forgejo base URL. |
| `FORGEJO_REPO` | secret | The `owner/repo` holding `deploy.yml`. |
| `FORGEJO_TOKEN` | secret | A token that may dispatch workflows. |
| `FORGEJO_DEPLOY_APP` | variable | Optional. Defaults to `app-statusboard`. |

Without them the deploy step reports that it is not configured, and the
release still succeeds. That is what lets a fork cut one.

Adding a setting means adding it to `app-statusboard/.env.example` in
the same change. That file is how the deploy repository learns a value
is now needed.
