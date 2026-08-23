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
- `DashboardItem` — dashboard, service, nullable component

  No `position`: nothing in the design lets you hand-order a board. Rows are sorted by severity or
  name, server-side. If manual ordering is ever wanted it arrives with the UI that needs it.

A null component means the whole service. Unique on `(dashboard, service, component)`.

### status

- `ComponentStatus` — current state, one row per component, updated in place. Dashboard reads hit
  only this table.
- `StatusEvent` — append-only, written **only when a status changes**. Full history at a fraction
  of the rows a per-poll snapshot would cost, and the trigger source for notifications later.
- `Incident` — upstream id, title, phase, started/resolved; `IncidentUpdate` child for the log
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

`GET /api/catalog/services/resolve/` sniffs a pasted URL and picks an adapter.

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

## 5. API surface

**The contract is [`docs/api/openapi.yaml`](../api/openapi.yaml)** — 19 operations, 14 schemas,
with every parameter and response shape. It is the single source of truth; drf-spectacular will
generate it from the code, and it is served through Scalar at `/admin/api-docs/` like your other
projects. This section records only the decisions behind it, so the two cannot drift.

### Identifiers

**UUID is the identity for every model**, from `common.BaseModel`. Path parameters are UUIDs
everywhere except one: `Service` also carries a stable `slug`, used on public catalog routes,
because those URLs get shared during an outage and a UUID would be hostile there. Anything the
user owns stays UUID, so nothing personal is enumerable. Writes always address the UUID.

`resolve/` derives a slug from the host and de-duplicates on collision (`linear`, `linear-2`).
Renaming keeps the old slug as a redirect rather than breaking shared links.

### Severity is filtered as a number

`severity_lte=3` is everything needing attention; `severity=4` is maintenance. There is no named
band parameter — the Outages chip is just `severity_lte=3`, and a client can compose any threshold
without waiting for a new enum value. `counts.by_severity` returns the raw histogram for the same
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
and the Components tab pages through `/components/`. Its `counts` gives the tab labels. A
component is a group when `child_count > 0`; there is no separate flag.

### Filtering, sorting and pagination are server-side, without exception

There is no cap on board size — one service can contribute 109 components — so the API never
assumes the board fits in one response. `counts` aggregates the whole collection rather than the
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

### Public access

Catalog and incident endpoints are readable without a token; that data is not personal. `tracked`
comes back `null` rather than absent, so the client renders `＋` without a second code path.
Adding, refreshing, `/me/` and `/dashboards/` require auth, and public endpoints carry their own
caching and rate limits.

### Screen-to-endpoint map

| Screen | Calls |
| --- | --- |
| Home · All / Outages / Maintenance | `GET /dashboards/{uuid}/?severity_lte=&sort=` |
| Home, signed out | `GET /catalog/services/?severity_lte=` |
| Header refresh | `POST /refresh/` |
| Row ⋮ → Refresh now | `POST /refresh/{service_id}/` |
| Row ⋮ → Stop tracking | `DELETE /dashboards/items/{uuid}/` |
| Discover, suggested | `GET /catalog/services/` |
| Discover, typing / no results | `GET /catalog/services/?q=` |
| Add by URL | `POST /catalog/resolve/` |
| Service · Components + filter | `GET /catalog/services/{slug}/components/?tracked=` |
| Service · Incidents | `GET /catalog/services/{slug}/incidents/?state=` |
| Service · About | `GET /catalog/services/{slug}/` |
| Service · Add all / Remove all | `POST` / `DELETE /dashboards/{uuid}/items/bulk/` |
| ＋ on any row | `POST /dashboards/{uuid}/items/` |
| Sign in | `magic-link` → `verify` |
| Settings | `GET` / `PATCH` / `DELETE /me/` |

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

Sort is **Smart** by default: tracked first, then severity ascending (worst first), then name.

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
