# Statusboard client design

**Status:** approved design, ready for an implementation plan
**Date:** 2026-09-03

This covers the client app, the API changes the approved designs need, and the deploy
pipeline for both images.

Designs, approved 2026-08-23 and amended through 2026-08-28:

- Mobile: <https://claude.ai/code/artifact/7900360b-d3bc-44ec-986b-d2152741c138>
- Desktop: <https://claude.ai/code/artifact/f947e3ad-fcfc-4945-9bd5-38ca9284455c>

## 1. What this supersedes

`docs/specs/2026-08-23-statusboard-design.md` sections 5, 6 and 7 predate the decks.
They describe a cream palette. They name the Home tabs All, Incidents and Maintenance.
They put a status dot on every row, and four tabs on a service. None of that is current.

Sections 5, 6 and 7 are deleted, and a pointer to this document replaces them. Rewriting
them would leave two documents describing one API. That is the drift this change exists to
end.

Sections 1 to 4 stay. Scope, architecture, the data model and the adapters are unchanged.
The columns in section 6 below are the exception.

## 2. Work order

1. Refresh sections 5 to 7 of the v1 spec from the decks and from this document.
2. Change the API and the models. The contract, `docs/check_docs.py` and
   `api/tests/test_contract.py` move in the same commit.
3. Scaffold `app/`, with CI and deploy.

The scaffold does not depend on steps 1 and 2. Its generated client does, so codegen
runs after step 2 lands.

## 3. Stack

| Concern | Choice |
| --- | --- |
| Build | Vite, React, TypeScript |
| Routing | TanStack Router |
| Server state | TanStack Query |
| API client | Orval, generated from `docs/api/openapi.yaml` |
| Styling | Tailwind v4 |
| Behaviour | Radix Primitives |
| Icons | Lucide, and only Lucide |
| Install | `vite-plugin-pwa` |
| Tests | Vitest, Testing Library, Orval's MSW handlers |
| Lint and format | Biome |

**A Vite SPA, not SSR.** There is no offline mode, so a service worker only makes the app
installable. It caches no API response. SSR would buy link previews for shared outage
URLs. That is solvable later with a prerender, without restructuring the app.

**Routing carries the filters.** Every filter is server-side, so every filter is a search
parameter. TanStack Router validates them against an enum in one schema. React Router
would need hand-written coercion for each one.

**Orval generates hooks, Zod schemas and MSW handlers.** The generated client is
committed. CI regenerates it and fails on a diff. That is `makemigrations --check` for the
client: a contract change shows what it did.

**Radix supplies behaviour only.** The decks define 26 tokens, a row anatomy and a card
catalogue. Nothing is missing but menu, tabs, popover and dialog. Those are styled from
the tokens. A component library would add a second set of colour names beside the 26.

**There is almost no client state.** Server state is Query. Filter state is the URL. What
is left is the theme, the hidden state of Suggested, and the install banner's visit count.
All three live in local storage. No store library ships until something needs one.

### Tokens

The 26 tokens are one file, and nothing else writes a hex. Both decks carry an identical
`:root` core block. It is the source.

- Neutrals `--u-0` to `--u-950`, one ultramarine ramp.
- Status, four hues with three each: raw for a fill, `-ink` for type on light, `-lift` for
  type on dark.
- Semantic tokens are built from the core. Rules are built from those.

### Auth

The access token lives in memory. The refresh token lives in local storage. An Orval
mutator refreshes once on a 401 and retries. `POST /auth/refresh/` stays the activity
heartbeat the backend stamps `last_active_at` from.

A strict CSP is set by the client image, because local storage is readable by script.

**The magic link is single use.** `VerifyView` stamps `used_at` on the first success. So
the client posts that token exactly once: a mutation, `retry: false`, fired once. A query burns
the token on a StrictMode double invoke. It then tells somebody who just signed in that
their link is dead.

The page load itself spends nothing. Only the POST does. That is what makes an email
client's prefetch safe.

## 4. Routes

Nine. Tabs are a search parameter, not a path. A tabbed screen is one page: the header is
shared and the body swaps, which is the decks' own rule.

| Route | `tab` | Other search parameters |
| --- | --- | --- |
| `/` | `board`, `updates` | board: `severity`, `sort`. updates: `service`, `component`, `kind`, `phase`, `sort` |
| `/discover` | none | `q`, `severity`, `sort` |
| `/discover/add` | none | none |
| `/services/$slug` | `components`, `updates`, `about` | components: `severity`, `tracking`, `sort`. updates: `component`, `kind`, `phase`, `sort` |
| `/components/$id` | `components`, `updates` | as above, without `component` |
| `/events/$id` | `timeline`, `affects`, `about` | none |
| `/signin` | none | none |
| `/verify` | none | `token` |
| `/settings` | none | none |

The first `tab` listed is the default. `cursor` is a search parameter on every list,
because pagination is infinite scroll.

Components keep UUID identity. Only `Service` carries a slug.

### A row's destination is a rule

```
is_overall  ->  /services/{service.slug}
otherwise   ->  /components/{id}
```

One function, used by every row on every screen. A component payload already carries
`is_overall` and its service, so nothing new is needed.

### Screen to endpoint

| Screen | Call |
| --- | --- |
| Home, board, signed in | `GET /dashboards/{uuid}/components/` |
| Home, board, signed out | `GET /catalog/components/?is_overall=true` |
| Home, updates | `GET /events/?dashboard={uuid}` |
| Discover | `GET /catalog/components/` |
| Add by URL, detected | `POST /catalog/import/` |
| Add by URL, not found | `POST /catalog/requests/` |
| Service, header and About | `GET /catalog/services/{slug}/` |
| Service, components | `GET /catalog/components/?service={slug}&is_overall=false` |
| Service, updates | `GET /events/?service={slug}` |
| Component, header | `GET /catalog/components/{uuid}/` |
| Component, components | `GET /catalog/components/?ancestor={uuid}` |
| Component, updates | `GET /events/?component={uuid}` |
| Event, header and About | `GET /events/{uuid}/` |
| Event, timeline | `GET /events/{uuid}/updates/` |
| Event, affects | `GET /catalog/components/?event={uuid}` |
| Event, affects, empty | the tab reads `Affects 0` and shows an empty state |
| Row plus | `POST /dashboards/{uuid}/components/` |
| Row menu, stop tracking | `DELETE /dashboards/{uuid}/components/{component_id}/` |
| Sign in | `POST /auth/magic-link/` |
| Verify | `POST /auth/verify/` |
| Settings | `GET /me/`, `DELETE /me/`, `POST /auth/logout/` |
| App start | `GET /meta/` |

## 5. API surface

15 operations become 18.

### Removed

| Operation | Why |
| --- | --- |
| `GET /catalog/services/` | Discover searches components. Signed-out Home lists overall components. |
| `GET /catalog/services/{slug}/components/` | `GET /catalog/components/?service=` serves it, and three other screens. |
| `GET /catalog/services/{slug}/events/` | `GET /events/?service=` serves it, and three other screens. |

`GET /catalog/services/{slug}/` stays. The service page reads it.

### Added

| Operation | Parameters |
| --- | --- |
| `GET /catalog/components/` | `q`, `service`, `ancestor`, `event`, `is_overall`, `is_tracked`, `status__severity` with `lte` and `in`, `ordering` |
| `GET /catalog/components/{uuid}/` | none |
| `GET /events/` | `dashboard`, `service`, `component`, `kind`, `phase`, `ordering` |
| `GET /events/{uuid}/` | none |
| `GET /events/{uuid}/updates/` | none |
| `POST /catalog/requests/` | body `{url}` |

`fields`, `cursor` and `page_size` stay on every operation.

### Changed

`GET /dashboards/{uuid}/components/` loses `event`. That parameter named the Home
Incidents and Maintenance tabs, which no longer exist. It gains
`status__severity__in`, because the Severity filter offers all six values.

`aggregates.by_event_kind` goes, for the same reason.

### One collection per model

`/events/` returns `ServiceEvent`. `/events/{uuid}/updates/` returns `EventUpdate`. The
screens call the first one Updates and the second one Timeline. The API names the model
and `/meta/` publishes the labels.

### Phase is a declared filter

`phase` accepts `open` and `closed`. It draws `CLOSED_PHASES` from `status/choices.py`, so
the client never restates which phases are terminal.

### A tab badge is the collection's total

`Updates 6` is `aggregates.total` of the same `/events/` query the tab renders. No stored
count, so a badge cannot disagree with the list under it. `Components 42` and
`Components 0` stay annotations, `component_count` and `descendant_count`. A component is
a group when `descendant_count` is above zero, so no flag records it.

### Discover is one list

Every trackable thing is a `ServiceComponent`. A service's rollup is one of them. So
Discover searches components only, and tracking a whole service is the plus on the row
named after it. There are no tabs and no service search.

Discover searches every component, rollups included. Only signed-out Home narrows to
`is_overall=true`, because a board is one row per service.

`Service.component_count` excludes the overall component, and a service's Components tab
passes `is_overall=false`. The header's plus tracks the whole service, so the rollup is
reachable without being a row on its own page.

**A component list is the whole subtree, never one level.** A service's tab lists every
component it has. A component's tab lists every descendant. The two screens are the same
screen at a different root, so they cannot count differently.

That is why the parameter is `ancestor` and not `parent`. A self-FK lookup returns one
level, and `parent` would name a query this does not run.

### Ordering

| List | Default |
| --- | --- |
| `GET /catalog/components/` with no `q` | `suggested` |
| `GET /catalog/components/?service=` | `status_page_order` |
| `GET /catalog/components/` with `q` | `SearchRank` |
| `GET /events/` | `-starts_at` |

Every one of them is labelled Smart in the interface.

`suggested` is `(-is_featured, severity_now, -watcher_count, name)`. Severity sits ahead of
popularity, the same as the service sort it replaces. A middling component that is broken
now beats a popular one that is fine.

There is one sort control and one label, **Smart**, on every list. With a `q` it ranks by
`SearchRank`. Without one it is `suggested`. A separate "Best match" would name a ranking
that does not exist until you type.

## 6. Model changes

### New models

`catalog.ServiceRequest`, for "Send this URL to us".

| Field | Note |
| --- | --- |
| `url` | normalised, unique. The thing an admin triages. |
| `request_count` | incremented on every post |
| `last_requested_at` | |

`BaseModel` carries the rest. `created_at` is the first request. `created_by` is the first
requester, null when signed out. There is no `requested_by`: that is what `created_by` is.

The endpoint upserts and increments, and always answers `202`. Asking twice cannot reveal
whether we hold a URL. It is throttled per IP, so one person cannot inflate the count.

There is no `state`. Nothing closes a request yet, so the column would have no writer. It
arrives with the workflow that moves it.

One row per URL, not one per request. A row per request would answer one question twice
once a URL was triaged.

`request_count` is not the denormalisation the v1 spec bans. `Poller.last_error` was banned
for copying `PollRun.error`, which can disagree with its source. Here there is no source.
The counter is the record.

`catalog.ComponentAncestor`, the component tree flattened.

| Field | Note |
| --- | --- |
| `ancestor` | FK to `ServiceComponent`, the one above |
| `descendant` | FK to `ServiceComponent`, the one below. Unique with `ancestor`. |
| `depth` | the steps down from `ancestor` to `descendant`. A parent is 1. |

One row per pair, written by reconcile. `parent` answers one level. This answers any depth
in one indexed join, which is what `?ancestor=` and every `descendant_count` ask for. A
breadcrumb reads the same rows the other way round, root first by `-depth`.

**Both columns are foreign keys, and that is the point.** An array of ancestor ids buys the
same indexed test and holds no reference. `parent` is `SET_NULL`, so nothing cleans an array
when a component goes, and every descendant keeps naming a row that is gone. Only a poll of
that service repairs it, and an untracked service is never polled again. A foreign key
cascades in the same statement as the delete.

It is not a `BaseModel`. Reconcile derives every row from `parent`, so an author and an edit
time record nothing anybody reads. The UUIDv7 key stays.

No row says a component is its own ancestor. Every reader counts other components, so a
depth-zero row would add one to every answer. Two check constraints hold that: one forbids
the row, one forbids the distance that would describe it.

### New columns

| Column | Type | Written by |
| --- | --- | --- |
| `ServiceComponent.is_featured` | bool | admin |
| `ServiceComponent.search_document` | `SearchVectorField`, GIN index | reconcile |
| `ServiceEvent.detected_by` | `provider` or `system` | set when the event opens, never changed |
| `EventUpdate.source` | `provider` or `system` | the adapter, or reconcile |

### Removed columns

`Service.is_featured`. It was the first key of the service suggestion sort, and that list
is gone. `ServiceFilter` goes with it.

`Service.description`. The About tab shows Website, Status page and Provider. Nothing
renders the description. So the column goes, with the adapter return value that filled it.
The v1 spec's sentence about refreshing it goes too.

`catalog.queries.WATCHER_COUNT` goes too. It annotated a service, and only the service
sort read it.

**A component's watcher count is an annotation, not a column.** `Service.watcher_count`
was a column a signal kept true, and four write paths never reached the signal. Migration
`catalog/0002` dropped it for that reason. A component repeats neither the column nor the
signal.

`COMPONENT_WATCHER_COUNT` is `Count("boards__owner", distinct=True)`, in
`catalog/queries.py`. `DashboardItem` points straight at a component, so it is one join.
The service version needed three.

### Changed

| What | From | To |
| --- | --- | --- |
| `ServiceEvent.external_id` | required, unique with `service` | nullable. The unique constraint becomes partial, `WHERE external_id IS NOT NULL`. |
| `ServiceEvent.title` | always the provider's | generated when we open the event, replaced when a provider claims it |
| `EventUpdate.body` | always the provider's | generated for a `system` update |
| `Service.component_count` | every component | every component except the overall one |
| `ServiceComponent.child_count` | direct children | renamed `descendant_count`, the whole subtree |

### Admin

`ServiceComponent.is_featured` is how a service is featured, ticked on its overall
component. So the component admin gains that column, a list filter and a bulk action. The
service admin edits its overall component's flag inline, because "feature this service" is
the question an admin actually has.

`ServiceComponent.watcher_count` joins the same list, read-only.

`catalog.ServiceRequest` is registered, ordered by `request_count`. That list is the demand
signal for what the catalog is missing.

### Choices

`IncidentPhase` gains `DETECTED = "detected", "Detected"` as its first value. It is open,
so `CLOSED_PHASES` is unchanged. `/meta/` publishes the label, so the client renders it
with no new code.

`EventUpdateSource` is new: `provider`, `system`.

### Unchanged

`User`, `Dashboard`, `DashboardItem`, `StatusPage`, `Poller`, `PollRun`,
`ComponentStatus`, and every other field on `Service`.

`Service.slug`, `logo` and `homepage_url` stay. Routes, the row's mark and the About tab
read them.

## 7. A status change is an event

The Updates feed is one table. When a provider explains an outage we store their event.
When they do not, we write our own. The client never learns there were two cases.

**Opening.** A component drops below operational and no provider event covers it. Reconcile
opens a `ServiceEvent` with `detected_by = system`, `kind = incident`, `phase = detected`,
and no `external_id`. It writes one `EventUpdate` with `source = system`.

**While open.** Every severity transition of an affected component writes another
`EventUpdate` with `source = system`. A `ComponentStatus` transition and a provider's post
are different facts, so both appearing near one moment is correct.

**Claiming.** A provider event claims an open unclaimed one rather than making a second.
`external_id` is filled in, the title becomes theirs, and their updates append with
`source = provider`. One outage is one card, with more updates on it.

A candidate must be open, on the same service, with intersecting components. Its
`starts_at` must be no earlier than the system event's, less `EVENT_CLAIM_WINDOW`. The
nearest `starts_at` wins when several match.

`EVENT_CLAIM_WINDOW` defaults to one hour, in `defaults.py`. Providers backdate `starts_at`
to when the incident really began, which is before our poll saw it. The default interval is
300s, so a short window would miss a backdated post. A system event stays open only while
the component is down. The far end is already bounded by the outage itself.

`detected_by` is never rewritten by a claim. That is why it exists as a column.
`external_id IS NULL` cannot answer "did we find this first", because a claim fills it in.

| `detected_by` | `external_id` | Means |
| --- | --- | --- |
| `system` | null | we found it and nobody explained it |
| `system` | set | we found it first and the provider caught up |
| `provider` | set | they posted before our poll saw the change |

**Closing.** The component returns to operational. Reconcile writes the closing
`EventUpdate`, sets `ends_at`, and moves `phase` to `resolved`.

A provider may post their own resolution near the same moment. Both are true, so both
appear. A timeline is ordered by `posted_at` and nothing prefers an author. The card shows
whichever landed last.

**Archiving also closes.** Reconcile sets `archived_at` when a provider stops publishing a
component. We can no longer see it recover, so an open system event on it could never
close. Archiving writes the closing update, sets `ends_at` to `archived_at`, and resolves
the phase. The update says the component is no longer published.

An event that cannot close leaves a permanently red row on somebody's board.

Claiming is safer than deleting. Nothing is destroyed, so a wrong match leaves an event
with one stray first update rather than losing data.

`ComponentStatus` stays the truth. A system event is a projection of it, written by one
writer and rebuildable from nothing. That is what keeps it from being a second answer to
the same question.

## 8. Search

`q` matches a component's full path. Searching `twilio` finds `SMS`, because Twilio is in
its path. Searching `twilio sms` finds it too.

`ServiceComponent.search_document` is a `SearchVectorField` with a GIN index, written in
the reconcile pass that already sets names and parents. A path built by walking `parent` at
query time cannot use an index.

| Weight | Source |
| --- | --- |
| `A` | the component's own name |
| `B` | its ancestors' names, walked from `parent` in that pass |
| `C` | its service's name |

So `twilio` ranks the Twilio rollup first, then top-level components, then leaves. The
ranking solves most of the flooding a popular service would cause. `q` becomes a
`SearchQuery` in websearch mode, so several words are an AND, ordered by `SearchRank`.

**Renaming or reparenting rewrites a whole subtree.** `ComponentAncestor` and
`search_document` both carry ancestry, so both change. Providers do move components, so that
rewrite belongs inside the reconcile pass. This is the one place the design fans out.

Both read one walk of `parent`, over the rows the pass already holds. A deep tree costs no
extra query. The ancestry rebuild then writes only the links that moved, because almost no
poll moves a component.

The service `search_fields` go with the service list.

## 9. Settings

The Refresh row is removed. It rendered `meta.poll_interval_seconds` read-only, and it
read as a control over something a user cannot set. Settings holds Theme, Suggested
services and Account.

`/meta/` stays. It publishes the severity labels and every other enum.

## 10. Build and test

`app/` builds its own image from its own directory, matching `api/`.

CI builds that image, then runs Biome, `tsc`, Vitest and the Orval drift check inside it.
What CI proves is what ships, which is the rule the API already follows.

Tests use Orval's generated MSW handlers, so a fixture cannot describe a response the
contract does not.

**Configuration is read at runtime, not baked in.** A Vite build inlines `VITE_` values,
which would make the image environment-specific. The container entrypoint writes
`config.js` from the environment at start, the way `api/entrypoint.sh` picks its process.
One image, any environment.

## 11. Deploy

`release.yml` gains an `app` job beside `api`: same tags, same cosign signing. The deploy
job waits on both.

A push to `main` that passes CI pushes `edge` and `sha-<sha>` for both images.

In the deployment repository:

- the four API services take `${API_TAG:-latest}`
- a new `app` service takes `${APP_TAG:-latest}`, routed by Traefik on `statusboard.dev`
- `API_TAG` and `APP_TAG` join `.env.example`

A deploy during development is then `APP_TAG=edge` on the server and `just deploy`. Unset
it to return to tag-gated releases. `just release` is unchanged.

`just` gains a recipe for the client's dev server. `just dev` runs the API, the poller and
the client together. `just check` gains the client image's checks.

## 12. Local development

`bin/worktree-env.py` already reserves `CLIENT_PORT` and points `CORS_ALLOWED_ORIGINS` and
`CSRF_TRUSTED_ORIGINS` at `<slug>.localhost:<client port>`. Vite binds that port, and the
API already trusts that origin. That file needs no change.

`APP_URL` and `APP_MAGIC_LINK_PATH` in `api/.env.local` gain values, so a sign-in link
reaches a page that serves it.
