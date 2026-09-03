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

Everything CI runs, in the image CI runs it in. `just test` is the fast
loop on the host; this is the one that proves the image.

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

`api.statusboard.dev` is one stack behind Traefik: the API, the poller,
its scheduler, Postgres and Redis. The first four are this image with a
different argument. The stack lives in the `deploy-pipeline` repository,
under `app-statusboard/`.

```bash
just release v0.1.0    # tag, build, sign, deploy
just deploy            # redeploy the current image
```

Releasing needs `FORGEJO_HOST`, `FORGEJO_REPO` and `FORGEJO_TOKEN` as
GitHub secrets. Without them the deploy step says so and the release
still succeeds. `just deploy` reads the same names from
`api/.env.local`.
