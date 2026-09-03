# Statusboard

## Requirements

- [Docker](https://docs.docker.com/get-docker/)
- [`just`](https://just.systems)
- [`uv`](https://docs.astral.sh/uv/)

## Commands

| | |
| --- | --- |
| `just init` | services, dependencies, migrations, admin, hooks |
| `just dev` | server and poller together |
| `just test` | the suite, on the host |
| `just check` | everything CI runs, in the image CI runs it in |
| `just lint` | fix and format |
| `just info` | this worktree's ports and database |
| `just reset` | drop the database and build it again |
| `just check-pages` | probe every recorded status page |
| `just release v0.1.0` | tag, build, sign, deploy |
| `just deploy` | redeploy the current image |

`just` on its own lists the rest.

Each worktree gets its own ports and database.
