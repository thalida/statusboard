# Statusboard Client Second Half Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the Statusboard client screens, account settings, and installable PWA.

**Architecture:** Keep API state in TanStack Query and filters in each route's validated search parameters. Share small list, filter, and error-state components across the screen folders. Keep installation state local and cache no API response.

**Tech Stack:** React, TypeScript, TanStack Router, TanStack Query, Orval, Tailwind v4, Lucide, Radix, Vitest, Testing Library, MSW, vite-plugin-pwa.

**Spec:** `docs/specs/2026-09-03-statusboard-client-design.md`

## Global Constraints

- A tab is a path. A filter is a search parameter, and each route validates only its own filters.
- There is no dark theme and no Theme row in Settings.
- Every screen is a folder under `app/src/routes/`. Only `/` keeps a flat `index.tsx`.
- Nothing outside `app/src/styles/tokens.css` writes a hex color.
- Every list uses server filtering, `cursor` pagination, and the shared `Row`.
- `/meta/` supplies severity and enum labels.
- No offline mode. The service worker makes the app installable and caches no API response.
- Comments follow ASD-STE100. Each sentence has one idea, uses active voice, and has under 20 words.
- Tests use `renderRoute(path)`, async queries, fake timers for durations, and explicit MSW handlers for asserted values.
- Commit messages use a lowercase conventional prefix and declarative clause. The body says why.

## Review Focus

- A search containing multiple words matches the API's per-word behavior and preserves the URL.
- A signed-out visitor can request an unknown URL without learning whether it exists.
- Mutations invalidate every visible list that can contain the changed component.
- Empty, failed, and loading responses remain distinguishable on every screen.
- Install prompts stay dismissible and never imply offline support.

---

## File Structure

**Create** `app/src/components/ComponentList.tsx`, `Filters.tsx`, `LoadState.tsx`, and `InstallPrompt.tsx` for shared list behavior, URL filters, request states, and install UX. Create focused tests beside each component.

**Modify** the screen folders under `app/src/routes/` to replace stubs with API-backed views. Add focused route tests beside each screen or screen family.

**Modify** `app/src/lib/search.ts` only when a route needs a missing URL filter. Keep tab paths in `app/src/lib/tabs.ts` and use generated types and hooks from `app/src/api/`.

**Modify** `app/package.json`, `app/vite.config.ts`, `app/index.html`, and `app/src/main.tsx` to install and register the PWA. Keep runtime API configuration unchanged.

### Task 1: Shared filters, list states, and component actions

**Files:** Create shared components and tests. Modify `app/src/components/Row.tsx` only if shared tracking actions require it.

**Interfaces:** `ComponentList` consumes `Component[]` and list-state props, and renders `Row`. Filters update the current route search object. Tracking actions use the generated dashboard mutations and the authenticated dashboard id.

- [x] Write tests for filter URL updates, loading/error/empty/list rendering, and track/untrack actions.
- [ ] Run the focused tests and confirm the stub or missing component fails each behavior test.
- [x] Implement `ComponentList`, `Filters`, and `LoadState` using the generated model types.
- [x] Run focused tests and `pnpm --dir app typecheck`.
- [x] Commit the shared list foundation and this plan.

### Task 2: Discover and Add by URL

**Files:** Modify `app/src/routes/discover/index.tsx`, `app/src/routes/discover/add.tsx`, and `app/src/lib/search.ts`. Add route tests.

**Interfaces:** Discover calls `GET /catalog/components/` with `q`, severity, ordering, and cursor. Add by URL posts to `/catalog/import/`, then `/catalog/requests/` when not found. Both request outcomes return a neutral confirmation.

- [x] Write route tests for search, severity, result rows, empty results, detected import, and neutral request confirmation.
- [ ] Run the focused tests and confirm they fail on the stubs.
- [x] Implement Discover with URL-backed filters, `Smart` ordering, cursor pagination, and shared list states.
- [x] Implement Add by URL with URL validation, import handling, and the always-neutral request response.
- [x] Run focused tests and `pnpm --dir app typecheck`.
- [x] Commit Discover and Add by URL.

### Task 3: Service and Component screens

**Files:** Modify `app/src/routes/services/$slug/` and `app/src/routes/components/$id/`. Add route tests.

**Interfaces:** Service header/About uses `GET /catalog/services/{slug}/`; its Components list uses `service` and `is_overall=false`; its Updates tab uses `/events/?service=`. Component header uses `/catalog/components/{uuid}/`; Components uses `ancestor`; Updates uses `/events/?component=`.

- [x] Write tests for service and component details, descendant/component lists, updates, filters, and empty/error states.
- [ ] Run focused tests and confirm they fail on the stubs.
- [x] Implement service tabs, the rollup tracking action, About metadata, and component filters.
- [x] Implement component tabs, breadcrumb context, descendant list, and updates.
- [x] Run focused tests and `pnpm --dir app typecheck`.
- [x] Commit Service and Component screens.

### Task 4: Event screens and Home Updates

**Files:** Modify `app/src/routes/events/$id/`, `app/src/routes/updates/index.tsx`, and Home's `app/src/routes/index.tsx`. Add route tests.

**Interfaces:** Event header/About uses `/events/{uuid}/`; Timeline uses `/events/{uuid}/updates/`; Affects uses `/catalog/components/?event=`. The Home Updates and Service/Component Updates tabs call `/events/` with their own query filters.

- [x] Write tests for event details, timeline order, affected rows, zero affected count, feed filters, and empty/error states.
- [ ] Run focused tests and confirm they fail on the stubs.
- [x] Implement event tabs and feed rows with phases, timestamps, component links, and service links.
- [x] Implement Home Updates and confirm each updates route validates only its tab's filters.
- [x] Run focused tests and `pnpm --dir app typecheck`.
- [x] Commit event and updates screens.

### Task 5: Settings

**Files:** Modify `app/src/routes/settings/index.tsx`. Add route tests.

**Interfaces:** `GET /me/` supplies account data. Suggested services state lives in local storage. Account deletion uses `DELETE /me/`; sign out uses `POST /auth/logout/` and clears the local session. Settings has no Theme or Refresh row.

- [x] Write tests for Suggested persistence, sign out, and account deletion confirmation and outcomes.
- [ ] Run focused tests and confirm they fail on the stub.
- [x] Implement Suggested services and Account actions with explicit confirmation for deletion.
- [x] Run focused tests and `pnpm --dir app typecheck`.
- [x] Commit Settings.

### Task 6: Installable PWA

**Files:** Modify `app/package.json`, `app/vite.config.ts`, `app/index.html`, `app/src/main.tsx`, and `app/src/components/Nav.tsx`. Create icons/assets and `InstallPrompt` with tests.

**Interfaces:** Use `vite-plugin-pwa` to generate a manifest and service worker. The worker precaches static assets only. The install prompt tracks visits in local storage, supports dismissal, and uses `beforeinstallprompt` when available.

- [x] Write tests for visit-count display, dismissal persistence, and browsers without an install prompt.
- [ ] Run focused tests and confirm they fail before implementation.
- [x] Configure manifest and installability without adding API caching or offline UI.
- [x] Build the app and inspect the generated manifest and service worker contents.
- [x] Run focused tests and `pnpm --dir app typecheck`.
- [x] Commit the PWA.

### Task 7: Final gate and visual QA status

**Files:** Modify this plan's checkboxes as each step completes.

- [x] Run `just check` and resolve all failures.
- [x] Run `git diff --check` and inspect the final diff for hex colors, dark theme references, and route structure violations.
- [x] Use browser control to inspect the phone layout at 390px and the Row at 232px.
- [x] Commit the completed plan checkboxes with the final code changes.

## Self-Review

- Spec coverage: routes and endpoints map to Tasks 2–5; local settings map to Task 5; installability and no API caching map to Task 6; app quality gates map to Task 7.
- Input review: blank and multiword search, malformed URLs, no session, empty collections, API failures, zero affected components, and missing browser install support have explicit owners.
- Current decisions: no dark theme, route-folder layout, and path tabs remain authoritative.
