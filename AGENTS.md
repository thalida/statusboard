# Working in this repository

## Prose

Comments, docstrings, commit messages and documentation follow ASD-STE100.

- One idea per sentence. 20 words or fewer.
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
- A spec describes the system, so it moves with the code. A plan
  records what somebody intended, so it stays as written. That includes
  the places where the plan turned out to be wrong.

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

## Layout

Which file a piece of code goes in, by what it is.

- An app keeps one `views.py` until it serves more than one resource.
  Then it becomes `views/`, one module per resource or per long-lived
  operation. `catalog` serves three resources, and `imports.py` is an
  operation on `Service`. A sub-resource stays with its parent, so an
  event's update log is not a second module.
- A **queryset method** is chainable vocabulary. It lives on the
  queryset in `models.py`, because a caller chains it onto a query.
- A **bare expression** is handed to `annotate()`. It lives in
  `queries.py`, because nothing chains it.
- `queries.py` is row-scoped and `aggregates.py` is collection-scoped.
  One lands in a serialized row. The other lands in the `aggregates`
  key beside `results`.
- `common` holds no expression that describes an app. `common/ordering.py`
  records this as a scar. The domain subqueries lived there, and the base
  layer imported the app it describes. Naming an app's choices to publish
  them is another thing, and it is fine: `/meta/` lists every enum, and
  one place has to.

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
- The stack lives in a separate private repository. Nothing here
  describes how the server runs it, or names where it sits.
- Add an environment variable to that repository's `.env.example` in the
  same change. It is the contract with the deployment, which holds the
  values. A setting missing from it is found on the server.

## Tests

Every behaviour change carries a test. The suite runs with no network:
adapters are tested against recorded fixtures.

A test's comment says what would break if the assertion failed.
If the answer is "nothing", the test does not earn its place.

**Assert on behaviour, not arrangement.** Field order, section titles and
`list_display` contents change for cosmetic reasons. A test that pins
them fails on a harmless edit and catches no defect. One pinned the four
component fieldsets in order. Moving two lines then cost a test edit, and
it had never caught a bug.

**A test fails only when something is broken.** A reasonable refactor
breaks a wrong test and nothing else.

**Never restate the implementation.** A test that computes its expected
value the way the code does passes while both are wrong. Write the
expected value out.

**No test-only production code.** No argument, method, flag or branch
exists so that a test can reach something. A path no caller reaches is a
path the test should not reach either.

**Enter through the front door.** Use the API client, the admin client or
the management command. Call an internal directly only when no pathway
reaches it.

**Every assertion can fail.** Watch it fail once, before the code exists.
`assert fieldsets[3] is not None` held on every possible input.

**Test what this project decided.** Django and DRF are already tested.
That a `CharField` stores a string is theirs. That a poller claims an
incident inside the window is ours.

**In the admin, test the logic, not the form.** Worth pinning: a
read-only field the model maintains, a queryset the page filters, what
`list_editable` writes, which user `created_by` records. Not which
fields appear, or in what order.

```sh
just test        # the suite, host and bin/ scripts together
just lint        # ruff check and format
just check       # every check CI runs, coverage gate included
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

**The change view holds every field.** A model field missing from every
fieldset is invisible and unreachable, and a changelist column with no
place on the form makes opening a row answer less than the list did.
`Service.source` recorded how a service arrived and reached no form at
all. A value computed from related rows lands as a readonly field, not
nowhere. So does provenance: a field recording how a row arrived is
shown and never typed, because an editable one can be made to lie.

**A column header is the name of its field.** The list and the form show
the same data, so they use the same word. A column headed `State` over
`is_archived` sent a reader looking for a field of that name. When the
two disagree the header gives way: the field name is what the model, the
API, the filters and every query already say.

**A column that only redraws a field is the field.** Put the field name
in `list_display`. Django draws a boolean as a tick, takes the header
from the model and sorts the column, none of it asked for. Hand-rolling
those three is where the header `State` came from. Keep a method only
where it does what a field cannot: composing several, following a
relation, or building a link.

**A column the list shows, the list filters.** If it is worth a column,
it is worth narrowing by. The converse does not hold: a filter may
narrow by something no column shows.

## Commits

A lowercase conventional prefix, then a declarative clause.

```text
fix: debug allows local hosts, not any host
```

The body says why the change was needed and what it prevents. It does not
list the files.
