# Statusboard

## Requirements

- [Docker](https://docs.docker.com/get-docker/)
- [`just`](https://just.systems)
- [`uv`](https://docs.astral.sh/uv/)

## Running locally

```bash
just init
just dev
```

Each worktree gets its own ports and database.

## Commands

| | |
| --- | --- |
| `just init` | services, dependencies, migrations, admin, hooks |
| `just dev` | postgres, redis, migrations, then the server and poller |
| `just test` | the suite, on the host |
| `just check` | everything CI runs, in the image CI runs it in |
| `just lint` | fix and format |
| `just info` | this worktree's ports and database |
| `just reset` | drop the database and build it again |
| `just clean` | stop this checkout's containers |
| `just probe-pages` | probe every recorded status page |
| `just release v0.1.0` | tag, build, sign, deploy |
| `just deploy` | redeploy the current image |

`just` on its own lists the rest.
