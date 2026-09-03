# Working in this repository

## Prose

Comments, docstrings, commit messages and documentation follow ASD-STE100.

- One idea per sentence. Under 20 words.
- Active voice. Present tense.
- No em dashes. A qualifier goes in brackets: `GitHub (2026-08-30 15:32)`.
- A standalone `—` is allowed as an empty-cell marker. It is a placeholder,
  not a separator.

Three of these are checked, by `just prose` and by a pre-commit hook:
sentence length, dashes, and the length of one comment paragraph. The
rest is judgement.

A comment says **why**, never what the line already says.

- Do not narrate the edit that produced the code.
- Do not restate the field or function name.
- Do not describe a state the code no longer has.

Delete a comment when the reason it recorded stops being true.

## Documentation

- No sample output. It goes stale and nobody re-runs it.
- No section nobody asked for.
- A README describes the repository as it is now, not as it changed.

## Engineering

Read the whole file before changing anything shared: a README, a settings
block, a schema, an API.

Say so before acting when a request exposes a deeper problem. A narrow
change that leaves the system worse is not the job.

**One definition, many readers.** A filter, a threshold or a set of rules
lives in one place. Restating it somewhere else is how two answers to the
same question drift apart. The admin dashboard once counted pollers the
scheduler never runs, because it restated the scheduler's filter.

**A leading underscore means private.** Reserve it for a method nothing
outside the class calls and no subclass overrides. Anything a subclass is
meant to replace is public, and its docstring says what an override owes
the caller. `RSSAdapter.get_feed` is public because four adapters
redirect the URL before calling it.

**Verify the rendered result.** An edit that ran without error is not an
edit that worked. Open the page. Read the value back.

**Prefer the framework's own configuration** over a stylesheet or a
template that overrides it. An override patches one instance of a
problem; the setting fixes the class.

## Settings

The split is by who named the setting.

- Django or a package named it (`DEBUG`, `SECRET_KEY`, `ALLOWED_HOSTS`,
  `DATABASES`, `REST_FRAMEWORK`, `UNFOLD`, `CELERY_*`) → `api/settings.py`
- We named it (`POLL_*`, `DEFAULT_PAGE_SIZE`, `SYSTEM_EMAIL`,
  `MAGIC_LINK_TTL`, `APP_URL`, `ENVIRONMENT`) → `api/defaults.py`

You can apply that by reading a name, which is the point. `defaults.py`
loads `.env.local`, so nothing reads a variable before the file that
supplies it.

## Deployment

- One image per component, built from that component's own directory.
  `api/Dockerfile` builds the API, and the client app will have its own.
  Nothing outside a component is in its build context.
- One image, four processes. The argument picks which: `migrate`, `api`,
  `worker`, `beat`. See `api/entrypoint.sh`.
- Python 3.14 is a requirement. Keys default to `uuid.uuid7`, which does
  not exist earlier.
- A check that gates a release runs in `docker-compose.test.yml`, not on
  the runner. What CI proves is then what ships. A stdlib-only script is
  the exception, because a container costs more than it saves.
- The stack lives in the `deploy-pipeline` repository, under
  `app-statusboard/`. Nothing here describes how the server runs it.
- Add an environment variable to that folder's `.env.example` in the
  same change. It is the contract with the deployment, which holds the
  values. A setting missing from it is found on the server.

## Tests

Every behaviour change carries a test. The suite runs with no network:
adapters are tested against recorded fixtures.

A test's comment says what would break if the assertion failed.

```sh
just test        # the suite
just test-cov    # with the coverage gate
just lint        # ruff check and format
```

## Database

Primary keys are UUIDv7 (`uuid.uuid7`, standard library). They sort by
creation, so nothing needs a second column to order by.

An invariant the code depends on belongs in a database constraint, not
only in the writer that maintains it.

`just reset` drops the local database and builds it back: admin, a small
catalog, one tracked service.

## Admin

The landing page answers one question: is polling healthy? Anything that
does not help answer it does not belong there.

One theme, dark. `UNFOLD["THEME"]` forces it, so a class with no `dark:`
variant still lands on the right ground.

## Commits

A lowercase conventional prefix, then a declarative clause.

```text
fix: debug allows local hosts, not any host
```

The body says why the change was needed and what it prevents. It does not
list the files.
