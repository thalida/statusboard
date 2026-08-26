# Statusboard v1 — design spec

**Status:** approved design, ready for an implementation plan
**Date:** 2026-08-23

Statusboard is one place to see whether the services you depend on are working. You track
services from a catalog; the app refreshes them on a schedule and shows what is broken.

Designs, approved 2026-08-23:

- Mobile — <https://claude.ai/code/artifact/7900360b-d3bc-44ec-986b-d2152741c138> (Revision 51)
- Desktop — <https://claude.ai/code/artifact/f947e3ad-fcfc-4945-9bd5-38ca9284455c> (Draft 21)

---

## 1. Scope

### In v1

A personal status aggregator: sign in, track services or individual components, see their
current state, read the provider's incident log, and browse a public view without an account.

### Explicitly not in v1

| Deferred | Why |
| --- | --- |
| Shared dashboards, invites | Sub-project #2. The `Dashboard` model exists with one row per user so sharing needs no migration. |
| Community issue reporting, comments | Sub-project #3. The Figma set already contains `status dot - user reported`, a split-circle variant, so the dot component should accept a shape from day one. |
| Notifications | Sub-project #2. The Figma set contains a `Toggle Notifications` button; nothing in v1 uses it. |
| Uptime history charts | `StatusEvent` accumulates from first poll, so any chart is empty on day one. Ships when there is data. |
| Service categories | Cut deliberately. `is_featured` plus `watcher_count` orders the suggested list instead. |

### Non-goals

Statusboard does not measure uptime itself. It reads what providers publish. Every number it
shows is theirs, not ours.

---

## 2. Architecture

Monorepo, matching caracara and codecity:

```
statusboard/
├─ api/                    Django 5 + DRF
│  ├─ api/                 settings, celery.py, urls
│  ├─ common/              BaseModel, pagination, schema, mixins
│  ├─ docs/                drf-spectacular + Scalar, served inside Unfold admin
│  ├─ authentication/      User, magic link
│  ├─ catalog/             Service, ServiceComponent
│  ├─ dashboards/          Dashboard, DashboardItem
│  └─ status/              ComponentStatus, StatusEvent, Incident, PollRun, adapters/, tasks.py
├─ app/                    React + TS + Vite + Tailwind + TanStack Query + vite-plugin-pwa
├─ justfile                infisical run --env=dev wrapping everything
└─ docker-compose.yml      postgres 17, redis 7
```

Dependency direction: `status` never imports users, `catalog` never imports dashboards. That is
what makes sharing a change to `dashboards` alone.

### House conventions to follow

- `uv`, `ruff` (`extend-select = ["I","F"]`), pre-commit with markdownlint and whitespace hooks
- `django-unfold`, with per-environment static dirs and `ENVIRONMENT` callbacks
- `drf-spectacular` + Scalar at `/admin/api-docs/` via `UnfoldModelAdminViewMixin`, with tag-group,
  logo and schema-name postprocessing hooks and a markdown introduction
- `dj-database-url`, `python-dotenv`, `psycopg2-binary`, `django-cors-headers`, `django-filter`
- `django-simple-history` on `catalog` models only
- `django-celery-beat` with `DatabaseScheduler`, so poll schedules are editable rows in admin
- Redis as the Celery broker (caracara uses RabbitMQ; Redis is already needed for throttling)
- Skip social/OAuth entirely

---

## 3. Data model

Every model extends `common.BaseModel`: UUID primary key, `created_at`, `updated_at`,
`created_by`, `updated_by`, `ordering = ["-created_at"]`. `auth.Permission` and `ContentType`
keep integer keys — that is Django, not a choice.

### authentication

`User(BaseModel, AbstractUser)` with a UUID pk and email as the login field. Django's stock
`auth.Group`, unregistered and re-registered with Unfold's admin. No custom Group: it is not
swappable, and the thing worth extending later is `DashboardMembership` in `dashboards`, which
is a different concept from a permission role.

### catalog

- `Service` — slug, name, logo, homepage URL, status page URL, `adapter`, `api_url`,
  `is_curated`, `added_by` (null for catalog entries), `is_featured`, `watcher_count`
- `ServiceComponent` — `service`, `upstream_id`, `name`, self-FK `parent`, `provider_order`,
  `archived_at`

  There is no `is_group` flag: a component is a group when it has children, so the flag would be a
  second copy of a fact the tree already holds. `provider_order` preserves the order the provider
  publishes, which is the order the component tab shows by default.

Custom URLs dedupe into the catalog on a normalised URL, so two users pasting the same status
page share one `Service` and one poll. A popular custom entry becomes curated by flipping a flag
in admin.

**Suggestion ordering** is `(-is_featured, -watcher_count, name)`.

`is_featured` is a boolean you tick in admin for services worth surfacing regardless of usage.

**`watcher_count` is distinct users, not items.** Someone tracking five Twilio components is one
watcher, not five:

```sql
SELECT COUNT(DISTINCT d.owner_id)
FROM   dashboards_dashboarditem i
JOIN   dashboards_dashboard d ON d.id = i.dashboard_id
WHERE  i.service_id = %s
```

It is recomputed for the one affected service on `DashboardItem` create and delete — a single
indexed aggregate, not a scan — so it is exact rather than drifting the way naive
increment/decrement would when someone adds a second component for a service they already track.
Deleting an account removes its items, which fires the same path.

A nightly reconciliation task recomputes every service as a safety net. It orders a suggestion
list, so a few hours of staleness costs nothing if a signal is ever missed.

On day one every `watcher_count` is zero, so the list is your featured picks followed by
everything else alphabetically. As real usage arrives the tail self-orders and you stop curating.
Nothing about the API changes at that point — it is the same query.

An earlier draft used a manual integer `featured_rank`. That is worse: it needs renumbering every
time something is promoted, and a value of 37 carries no meaning to whoever inherits it.

### dashboards

- `Dashboard` — owner, name, position. Exactly one per user in v1.
- `DashboardItem` — dashboard, **component**

  Every row is a component. There is no nullable service field and no "is this a service or a
  component" discriminator, because a service's overall status is itself a component — see below.

  No `position`: nothing in the design lets you hand-order a board. Rows are sorted by severity or
  name, server-side. If manual ordering is ever wanted it arrives with the UI that needs it.

Unique on `(dashboard, component)`.

### Every service has an overall component

Statusboard creates one component per service, `is_overall = true`, `parent = null`, named
"All services". It carries **the provider's own top-level indicator** — not an aggregate of its
siblings, because a worst-of rollup leaves Cloudflare permanently orange when one of 109
components is always degraded.

This is why the board model is as simple as it is. "Track Twilio" and "track Twilio SMS" are the
same operation with a different id, so:

- A tracked row points at one thing, not one-of-two
- Every board endpoint is `/dashboards/{uuid}/components/`, because every row *is* a component
- A board row has no `kind` to branch on, and the client never picks an endpoint by row type

An earlier draft had items point at *either* a service or a component. That forced a
discriminator on every row, an either/or request body, and a client that had to decide which shape
to send. The overall component removes all three.

**There are no bulk endpoints and no aliases.** One `POST` creates one item; one `DELETE` removes
one. "Add all" and "Remove all" are the client repeating those calls, so there is never a decision
about which endpoint to use. The cost is honest: removing a service with 42 tracked components is
42 requests. They are small, they parallelise, and it is a rare action — cheaper than an API
where every add has two possible shapes.

### status

- `ComponentStatus` — current state, one row per component, updated in place. Dashboard reads hit
  only this table.
- `StatusEvent` — append-only, written **only when a status changes**. Full history at a fraction
  of the rows a per-poll snapshot would cost, and the trigger source for notifications later.
- `Incident` — upstream id, title, phase, started/resolved; `IncidentUpdate` child for the log
- `MaintenanceWindow` — **hangs off a component, not a service**, and there can be several.
  Providers schedule maintenance per component, and a service with three components under
  maintenance has three windows with three different times. A service-level field would have to
  pick one and lie about the rest, so the API exposes `Component.maintenance_windows[]` and
  derives `Service.next_maintenance_window` as the soonest across them.
- `PollRun` — per-attempt success/error, so "everything is fine" is distinguishable from
  "we have not successfully checked in six hours"

### Status and incidents are different things

They are not derived from each other and neither is computed from the other.

A **status** is the current state of a service or component, as the provider reports it —
`operational`, `degraded`, and so on.

An **incident** is the provider's narrative record: a title, a start time, affected components,
and a running log of updates. Its `phase` is workflow — `investigating`, `identified`,
`monitoring`, `resolved`.

They move independently. A provider can be `monitoring` a fix while every component already reads
`operational`, and can report `degraded` with no incident open at all. Statusboard shows both and
never infers one from the other — which is why the service screen has separate Components and
Incidents tabs rather than one merged list.

### Normalised status

| Status | Severity | Colour |
| --- | --- | --- |
| `major_outage` | 0 | `#E51F00` |
| `partial_outage` | 1 | `#E58900` |
| `degraded` | 2 | `#E58900` |
| `unknown` | 3 | `#808080` |
| `maintenance` | 4 | `#00A0E5` |
| `operational` | 5 | `#00E54D` |

**Lower is worse**, matching the SEV0/SEV1 convention people arrive with. Sorting worst-first is
`ORDER BY severity ASC`, and the Outages filter is `severity <= 3` — which is also why `unknown`
sits at 3 rather than beside `operational`: a service we cannot reach belongs with the problems,
not with the healthy ones.

**An "All services" row uses the provider's own top-level indicator, never the worst of its
components.** A worst-of-components rollup leaves Cloudflare permanently orange, because something among
109 components almost always is.

---

## 4. Provider adapters and polling

### Adapters

One class per provider, same interface: given a URL, return normalised components and incidents.

- `StatuspageAdapter` — Atlassian's `/api/v2/summary.json` and `/api/v2/incidents.json`. Covers
  most of the industry.
- `InstatusAdapter`, `BetterStackAdapter`
- `RSSAdapter` — fallback. **Returns incidents but not component status**, which should shape
  which providers v1 claims to support.

Each exposes `fetch_status()` and `fetch_incidents()`. Adding provider #5 is one new class.

`POST /api/catalog/imports/` detects the provider from a pasted URL and creates the service.

### Keeping names and component trees current

Providers rename services, add components and retire them. A poll is therefore a reconciliation,
not just a status read.

Each successful poll:

1. **Upserts components by `upstream_id`.** New ones are created, renames are applied, and the
   parent/child structure and `provider_order` are refreshed.
2. **Marks vanished components `archived_at`** rather than deleting them. Someone may be tracking
   one, and deleting the row would silently remove it from their board. An archived component
   still renders, reads `unknown`, and says the provider no longer publishes it.
3. **Refreshes the service's own metadata** — name, description, logo — for curated and custom
   entries alike, so a rename upstream does not leave a stale name on someone's board.

Component identity is the provider's `upstream_id`, never the display name. Names change; ids do
not, and matching on names would orphan a tracked row the first time a provider edits its wording.

### Polling

**There is one global schedule, not a schedule per user or per dashboard.** A service is polled
because *someone* tracks it, not because a particular board is open. Two hundred users tracking
Twilio produce one poll every five minutes, not two hundred.

`django-celery-beat` on `DatabaseScheduler`. Rules:

- Poll only services with at least one watcher
- Five-minute default interval, with jitter so we do not stampede
- Honour `ETag` / `If-Modified-Since`
- Exponential backoff on failure
- **A hard per-service cooldown, global across all users**, which the manual refresh also obeys

A failed fetch sets `unknown` and **never clobbers the last known value**. The UI shows the grey
state plus how long it has been stale.

The manual refresh path, and why the cooldown lives on the service rather than the dashboard or
the user, is specified in §5 under **Refresh**.

A poll also captures the service's **logo** from its own page. A favicon belonging to the parent
company rather than the product — Google's mark for Google Slides — is discarded rather than
stored: a wrong logo misidentifies the row, while a missing one falls back to an initial and
merely looks incomplete.

## 5. API surface

**The contract is [`docs/api/openapi.yaml`](../api/openapi.yaml)** — 17 operations, 14 schemas,
with every parameter and response shape. It is the single source of truth; drf-spectacular will
generate it from the code, and it is served through Scalar at `/admin/api-docs/` like your other
projects. This section records only the decisions behind it, so the two cannot drift.

### Identifiers

`GET /me/` returns your `default_dashboard_id`. There is no alias endpoint for "my board" — the
dashboard is a resource and it is addressed like one, which is also the URL sharing will use
unchanged. The name says *default* rather than *the* because v1 having one per user is a product
decision, not a schema one.

**UUID is the identity for every model**, from `common.BaseModel`. Path parameters are UUIDs
everywhere except one: `Service` also carries a stable `slug`, used on public catalog routes,
because those URLs get shared during an outage and a UUID would be hostile there. Anything the
user owns stays UUID, so nothing personal is enumerable. Writes always address the UUID.

An import derives the slug from the host and de-duplicates on collision (`linear`, `linear-2`).

**An import is a resource, not an action on the service collection.** It records one attempt to
turn a URL into a service. That keeps `POST /catalog/services/` free for a future admin create,
which takes a service body rather than a URL — the two must not share an endpoint, or the request
body becomes an either/or again.

It also leaves room for the import to become asynchronous. A slow detection can return `202` and
let the client poll the import, without changing what the endpoint means.
Renaming keeps the old slug as a redirect rather than breaking shared links.

### Severity is the state, and there is no status string beside it

An earlier draft carried both a `severity` integer and a `status` string on every row. Two fields
for one fact can disagree, and one of them is always the redundant copy. Only the integer is
transported; `/meta/` publishes the 0–5 label map once and the client renders from it, so a label
change ships without touching a serializer.

`status__severity__lte=3` is everything needing attention; `status__severity=4` is maintenance.
There is no named band parameter — the Outages chip is just a threshold, and a client can compose
any other one without waiting for a new enum value. `aggregates.by_severity` returns the raw histogram for the same
reason.

### One list, several screens

Discover, the suggested lists and the public "down right now" view are the same catalog query with
different parameters. Suggestions are not a separate concept: they are the list with no `q`, sorted
`(-is_featured, severity, -watcher_count, name)`.

Severity sits ahead of popularity deliberately — a mid-popularity service that is currently broken
is more worth surfacing than a more popular one that is fine, which is the whole premise of the
public view.

### Components are their own collection

Cloudflare publishes 109 and nothing caps that, so the service detail reports `component_count`
and the Components tab pages through `/components/`. Its `aggregates` gives the tab labels. A
component is a group when `child_count > 0`; there is no separate flag.

### Filtering, sorting and pagination are server-side, without exception

There is no cap on board size — one service can contribute 109 components — so the API never
assumes the board fits in one response. `aggregates` covers the whole collection rather than the
page, so a chip is correct on page four.

There is no client-side fallback. One rule, one implementation.

### Refresh is one call

`POST /refresh/` nudges every service the caller tracks, skipping any inside its global
per-service cooldown, waits up to three seconds, then returns the board exactly as the `GET`
would. One press, one request, and the screen either changed or it did not. POST-then-GET forces
the client to guess a wait, and it guesses too early.

**The cooldown is on the service, globally.** The thing needing protection is somebody else's
status page. A per-user or per-board limit would guard our endpoint while leaving theirs exposed,
and would poll one service twice for two boards that both track it. A per-user rate limit sits on
top only to stop one client hammering us.

Signed out, the button routes to sign-in: an unauthenticated nudge is a way for strangers to spend
our request budget on other people's servers.

### One envelope, and aggregates that grow without changing it

Every list returns `{ aggregates, next, results }`. `aggregates` is the one place for anything
computed over the **whole collection** rather than the page.

An earlier draft had `counts` and `oldest_refreshed_at` sitting side by side at the top level,
which is two aggregations at two different depths. The next figure worth showing would have been a
third key, and a client could not read them generically.

```jsonc
{
  "aggregates": { "total": 42, "by_severity": {"0": 1, "5": 38}, "oldest_refreshed_at": "…" },
  "next": "cursor…",
  "results": [ … ]
}
```

`Aggregates` defines the floor — `total`, present everywhere, so it can be read without knowing
which endpoint produced it. An endpoint extends rather than replaces: `StatusAggregates` adds the
severity histogram, the tracked count and `oldest_refreshed_at`; `IncidentAggregates` adds a phase
histogram. A new list endpoint declares its own subclass and the envelope never changes shape.

In DRF this is one pagination class emitting the three keys, with each viewset supplying
`get_aggregates(queryset)` — so adopting the shape is a method, not a new response schema.

The rule that makes it worth having: **nothing collection-wide is ever added at the top level.**
A figure that describes the whole collection goes in `aggregates` or it does not ship.

### One schema, one model

Serializers are `ModelSerializer`s, so the API shape has to be something a `ModelSerializer` can
actually produce. Every schema therefore maps to a single model, and **related models nest under a
key rather than flattening into the parent**.

`status` is the case that forced the rule. Severity, `started_at` and `last_refreshed_at` live on
`ComponentStatus`, a separate table from `Component` and further still from `Service`. An earlier
draft merged them into the parent object, which reads fine as JSON but is a hand-assembled
serializer with `source=` on every field and no model behind it. Nested, it is one
`StatusSerializer` over one model, reused on both parents — and a `Service` reaches its status through
the overall component, which is the job that component was introduced for.

The rule applies transitively, which is easy to miss. A `Service` has no status of its own — its
status *is* its overall component's. An intermediate draft gave `Service` a `status` key with
`source="overall.status"`, reaching through a relation to hoist fields onto the parent: the same
mistake one level up. It also carried `overall` as a bare id and `is_tracked` as a third field
describing that same component. All three collapse into one nested object:

```jsonc
"overall": { "id": "…", "status": { "severity": 1, … }, "is_tracked": true },
"tracked_component_count": 3
```

One FK, one nested serializer. The response path and the filter path become identical —
`overall.status.severity` is read at `?overall__status__severity__lte=3`.

**Tracking is two questions, not one.** Whether the *overall* component is tracked is what the ＋
on a service row toggles; whether *anything* from the service is tracked decides if it appears on
your board. You can track Twilio SMS without tracking Twilio as a whole. The first is
`overall.is_tracked`; the second is `tracked_component_count > 0`, so no second boolean is carried
for something the count already answers — and the same count renders the "3 tracked" label.

The count **includes the overall component**, because overall is a component like any other.
Excluding it would reintroduce the service-versus-component split this design exists to remove.

`allOf` survives in only one role: a serializer subclassing another **over the same model**.
`ServiceDetail` extends `Service`; `TrackedComponent` extends `Component`. It never merges two
models into one flat object.

Query parameters use the ORM path, and the nesting is visible in the URL on purpose.

```python
filterset_fields = {"status__severity": ["exact", "lte"]}   # ?status__severity__lte=3
ordering_fields  = ["status__severity", "name", "updated_at"]
```

That is django-filter's zero-config behaviour. Renaming them to `severity_lte` buys a shorter URL
and costs a declared `NumberFilter` per field per viewset — a `FilterSet` class to write and keep
in sync every time a field is added. The ORM path also means a client can read a response body and
derive the filter for anything in it, including fields that do not exist yet.

Three parameters cannot follow the rule and are declared: `tracked_component_count__gt` and
`overall__is_tracked` are per-user annotations with no ORM path behind them, and
`ordering=suggested` is a multi-key sort. Everything else is generated.

Because these paths are public, **model field names are chosen to read well in a URL.** The FK from
`Service` to its overall component is `overall`, not `overall_component`, so the catalog filter is
`overall__status__severity__lte`. Naming is an API decision now, not just an internal one.

### What belongs to the user, the device, and the deployment

Three things were sitting on `/me/` that are not user data, and each moved:

- **Theme is per device.** Someone runs dark on their phone at night and light on a desktop in a
  bright office; syncing it as an account preference makes one of those wrong. It lives in that
  browser's local storage and never reaches the server.
- **Poll interval is deployment-wide**, not a preference. A user cannot make us hit somebody
  else's status page more often, so it was never theirs to set.
- **The severity label map, page sizes and refresh cooldown** are the same for everyone.

Those now come from `GET /meta/`, fetched once at app start and cacheable. It also means the 0–5
labels have exactly one home. What is left on `/me/` is genuinely personal and small: id, email,
`default_dashboard_id`. Nothing on it was patchable once theme left, so `PATCH /me/` is gone —
`GET` and `DELETE` are the whole resource.

### Public access

Catalog and incident endpoints are readable without a token; that data is not personal.
`is_tracked` comes back `null` rather than absent, so the client renders `＋` without a second code path.
Adding, refreshing, `/me/` and `/dashboards/` require auth, and public endpoints carry their own
caching and rate limits.

### Screen-to-endpoint map

| Screen | Calls |
| --- | --- |
| Home · All / Outages / Maintenance | `GET /dashboards/{uuid}/components/?status__severity__lte=` |
| Home, signed out | `GET /catalog/services/?overall__status__severity__lte=` |
| Header refresh | `POST /refresh/` |
| Row ⋮ → Refresh now | `POST /refresh/` with `{component_id}` |
| Row ⋮ → Stop tracking | `DELETE /dashboards/{uuid}/components/{component_id}/` |
| Discover, suggested | `GET /catalog/services/` |
| Discover, Tracked filter | `GET /catalog/services/?tracked_component_count__gt=0` |
| Discover, typing / no results | `GET /catalog/services/?q=` |
| Add by URL | `POST /catalog/imports/` |
| Service · Components + filter | `GET /catalog/services/{slug}/components/?is_tracked=` |
| Service · Incidents | `GET /catalog/services/{slug}/incidents/?resolved_at__isnull=true` |
| Service · About | `GET /catalog/services/{slug}/` |
| Service · Add all / Remove all | the same `POST` / `DELETE`, repeated per component |
| ＋ on any row | `POST /dashboards/{uuid}/components/` |
| Sign in | `magic-link` → `verify` |
| App start | `GET /meta/` |
| Settings | `GET /me/`, `GET /meta/`, `DELETE /me/`; theme is device-local |

### The row is one component, used everywhere

Home, Discover and the service screen render the same card. Line one is the mark and the name;
line two is the status and its duration; line three is context. Nothing shares a line, because a
232px phone row cannot hold two things that must not truncate.

**Line three is the only variable, and what it holds follows from what the row is.**

| the row is | line three |
| --- | --- |
| a service you track nothing of | `7 components` — what is on offer |
| a service you track part of | `Tracking [overall] [3 of 42]` |
| a component on your board | its parent breadcrumb, `Twilio › Programmable Messaging` |

A board row never shows a tracking count. The count answers *how much of this service am I
watching*, which is a question about a **service**; a board row is already one tracked component,
so the answer would always be "this one".

Tracking state renders as **one token per subscription** rather than a sentence — `overall` for the
summary row, `3 of 42` for components, both when you take both. That maps one-to-one onto
`overall.is_tracked` and `tracked_component_count`, so the client assembles no strings, and "all"
is simply `118 of 118` with no extra vocabulary.

**The duration is always shown**, including on operational rows, where it reads as time since the
service last left operational — the same `status.started_at` every other state uses. Maintenance is
the one case that would state its timing twice, so its window renders in that slot rather than
below, and always relatively: `in 4 hrs` before it starts, `ends in 40 min` while it runs.

**The overall component is titled by where you are standing.** On a service screen the header
already says Twilio, so the row is `Overall status` with `All services` beneath. On your board
nothing else names the service, so it is `Twilio` with `Overall status` beneath. Same component,
same `is_overall` flag, different useful title.

**Marks appear only where rows come from different services** — Home and Discover. On a service
screen every row belongs to the same service, so forty-two identical marks are noise and the slot
is dropped. Where a service has no usable logo the row falls back to its initial in the same
circle, so a list with patchy coverage keeps one left edge.

## 6. Frontend

React + TS + Vite + Tailwind + TanStack Query + `vite-plugin-pwa`.

### Navigation

Three destinations: **Home**, **Discover**, and a third slot that is **Sign in** when logged out
and **Settings** when logged in. Signed out and signed in are the same screens; only the buttons
differ.

- Mobile: bottom pill, inset to the content width, fully rounded
- Desktop: top bar; Sign in sits right as a primary button

### Screens

| Screen | States |
| --- | --- |
| Home | All · Outages · Maintenance; empty, unreachable, row menu |
| Discover | suggested, typing, no results |
| Add by URL | detected, not found |
| Service | Components · Incidents · About; not tracked, outage, unknown |
| Sign in | request, check your email, verify |
| Settings | preferences, account, install |

### Chips and filters

`All` · `Outages` · `Maintenance`. Outages means major, partial, degraded and unknown —
**not** maintenance, which is planned work and has its own chip. Counts describe whatever the tab
shows: the catalog when signed out, your tracked set when signed in. Signed out shows no counts,
because nothing is yours.

Sort is **Smart** by default (`ordering=suggested`): tracked first, then severity ascending
(worst first), then name.

### No offline mode

Statusboard reports on remote services. With no network there is nothing true to report — a cached
board would show yesterday's answer to today's question, which is worse than saying nothing.

So there is no stale-cache mode, no offline banner and no dimmed rows. A failed request shows a
plain "can't reach statusboard" state with a retry. The service worker exists only to make the app
installable; it does not cache API responses.

The `unknown` status is a different thing and stays: that is *our* server failing to reach a
provider, which we can report accurately because we are online and they are not.

### Install

No prompt on first visit. A dismissible banner on the third visit, plus a row in Settings.
**iOS has no programmatic install prompt**, so Safari gets "tap Share, then Add to Home Screen"
while Android and desktop Chrome get a real button.

---

## 7. Design system

### Vocabulary

**You track. The app refreshes. The catalog gets no verb.**

- `＋` starts tracking; `⋮` opens the menu that stops it. No tick, no lock icon.
- Signed out, `＋` is still `＋` and opens Sign in.
- "Refreshed every 5 min", never "updated" — the Incidents tab already uses *updates* for
  provider posts — and never "monitored".
- "In catalog since", never "tracking since".

### Row anatomy

Identical on both platforms; desktop only changes the container.

```
[logo]  Twilio                        ●
        Major outage · 38 min
        42 components                 ⋮
```

- **Logo** top-left, neutral disc with an initial. Only where rows come from different services —
  on a service screen every row is the same service, so the slot is dropped. No provider publishes
  per-component icons.
- **Status** in words, in its severity colour, with duration in mono beside it
- **Meta** last: `42 components` for a service, the breadcrumb for a component,
  `Overall status` for the rollup row. **On the Maintenance tab every row shows its window
  instead**, in local time.
- **Dot** 15px, top-right. **Action** bottom-right.

The subtitle says what the row *is*, never what you have done with it.

### Colour

| Token | Value |
| --- | --- |
| Ground | `#F5EDD6` |
| Card | `#FFFFFF` |
| Nav / ink | `#29140A` / `#0D0D0D` |
| Accent | `#32CDB3` (notifications toggle only) |

Status dots use the palette above at **80% fill opacity**, as Figma sets them.

**Status text uses darkened variants** — `#1C7A3E`, `#A35F00`, `#B3180B`, `#0B6EA0` — because
`#00E54D` on white is about 1.8:1 and unreadable at 11px. Dots keep the exact Figma colours.

Rules:

- Status colour is visible wherever services are listed, including the catalog
- Green means operational and nothing else — buttons use brand dark
- Count pills are grey: a count is a quantity, not a severity
- Secondary buttons are transparent with a `#D6CCB8` border; primary is dark fill

### The mark

The statusboard logo carries the status dot wherever it appears — brand row, tab bar, favicon,
app icon. **One dot, the lower-left counter**, coloured by the worst status you track. It is the
position your artwork already varies (red and grey); the upper-right is green in every variant.
Scheduled maintenance keeps it green — planned work does not need you.

Signed out, nothing is tracked, so the counter stays hollow.

### Icons

Home and Discover use the Figma marks. Settings and Sign in use Lucide (`settings`, `log-in`),
and the back arrow is Lucide `chevron-left`. The Figma tab-bar exports embed their labels as
vector paths — extract the glyph only.

Open: the Figma marks are filled and Lucide is stroked, so the nav mixes two weights. Either draw
filled versions of those two or move Discover to Lucide, leaving Home as the only filled mark.

### Desktop differences

Only three, each forced by width:

1. Top nav instead of a bottom pill
2. Rows flow into `repeat(auto-fill, minmax(212px, 1fr))`
3. A field that filters a list spans the list; a form that *is* the task gets a column —
   360px form card, 560px for Add-by-URL

Plus one intentional divergence: the service title keeps its status label, which mobile drops for
width.

---

## 8. Testing, infra, deploy

### Testing

pytest + pytest-django + factory_boy + xdist + randomly, with codecity's coverage gate. TDD.

**Adapters are the risky surface**, so they are tested against recorded fixtures — real captured
JSON from Twilio, GitHub, Cloudflare — with **zero network in the test suite**. Frontend: vitest +
testing-library + MSW.

### Infra

docker-compose runs postgres and redis; Django runs on the host via `runserver`, matching
reactionchat-api. `just init` → `uv sync --locked` → `pre-commit install` → `migrate` →
`loaddata local_dev` → `collectstatic`.

### Email

Magic link needs a real provider (Resend or Postmark) before anyone but you can sign in. Local dev
uses Django's console backend, so it blocks nothing during development, but it is a deploy-day
prerequisite.

### Operational honesty

We are the thing that tells you when services break, so we cannot quietly break ourselves.
`PollRun` errors surface in admin, and a service failing N consecutive polls is visibly flagged
rather than silently showing stale green.

---

## Open questions

1. **Icon weight** — filled Figma marks beside stroked Lucide icons in the same nav.
2. **Suggestion quality** — featured plus watcher count is a starting point, not a ranking
   algorithm. Worth revisiting once there is enough usage for the tail to be meaningful.
3. **Corner-notch card treatment** — explored and set aside; revisit against the real `.row`
   component rather than a copy.
