# Statusboard Client Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A deployed client you can sign into, that shows your board.

**Architecture:** A Vite SPA on its own origin, generated from `docs/api/openapi.yaml` so the
contract has one definition. Tabs and filters live in validated search parameters, so a URL is
the whole of a screen's state. One image, configured at runtime, deployed beside the API.

**Tech Stack:** pnpm, Vite, React, TypeScript, TanStack Router, TanStack Query, Orval, Tailwind
v4, Radix Primitives, Lucide, Biome, Vitest, MSW.

**Spec:** `docs/specs/2026-09-03-statusboard-client-design.md`

**Second half:** Discover, Add by URL, Service, Component, Event, Settings and the PWA are a
following plan. They are written against the components this one creates.

## Global Constraints

- The API is live at 18 operations. `docs/api/openapi.yaml` is the contract, and
  `api/tests/test_contract.py` holds it to the code. The client never hand-writes a type.
- Node 22 or later. pnpm, with a committed lockfile.
- Comments follow ASD-STE100: one idea per sentence, under 20 words, active voice, present
  tense, no em dashes. A comment says why, never what the line already says.
- A test's comment says what would break if the assertion failed.
- Nothing writes a hex outside `src/styles/tokens.css`. Every rule reads a token.
- No offline mode. The service worker makes the app installable and caches no API response.
- One image per component, built from that component's own directory. Nothing outside `app/`
  is in its build context.
- Configuration is read at runtime. A `VITE_` value baked at build time makes the image
  environment-specific.
- `bin/tests/test_merge_gate.py` fails when `just check` runs a check CI does not. Both move
  together.
- Commits use a lowercase conventional prefix, then a declarative clause. The body says why.

---

## File Structure

**Created**

| File | Responsibility |
| --- | --- |
| `app/package.json`, `pnpm-lock.yaml`, `tsconfig.json`, `vite.config.ts` | the build |
| `app/biome.json` | lint and format |
| `app/orval.config.ts` | generation from the contract |
| `app/index.html` | the single page |
| `app/src/main.tsx` | mounts the router and the query client |
| `app/src/styles/tokens.css` | the 26 tokens, and nothing else writes a hex |
| `app/src/styles/app.css` | Tailwind, and the token layer |
| `app/src/lib/config.ts` | reads what the entrypoint wrote |
| `app/src/lib/auth.ts` | the token pair, and the refresh |
| `app/src/lib/fetcher.ts` | Orval's mutator |
| `app/src/lib/search.ts` | the search-parameter schemas every route shares |
| `app/src/api/` | generated. Committed, and CI fails on a diff. |
| `app/src/routes/` | TanStack Router file routes |
| `app/src/components/Row.tsx` | the deck's card, used by every list |
| `app/src/components/Nav.tsx` | bottom pill on mobile, top bar on desktop |
| `app/src/components/Header.tsx` | brand, the refresh stamp, the page title |
| `app/Dockerfile`, `app/nginx.conf`, `app/entrypoint.sh` | the image |
| `app/.dockerignore` | |

**Modified**

| File | Change |
| --- | --- |
| `justfile` | client recipes, and `check` gains the client's gate |
| `.github/workflows/ci.yml` | a client job |
| `.github/workflows/release.yml` | an `app` job beside `api` |
| `.gitignore` | `node_modules/`, `app/dist/` |
| `api/.env.local` | `APP_URL` and `APP_MAGIC_LINK_PATH` gain values |

---

## Task 1: The app builds, lints and tests

**Files:**
- Create: `app/package.json`, `app/tsconfig.json`, `app/vite.config.ts`, `app/biome.json`,
  `app/index.html`, `app/src/main.tsx`, `app/src/App.tsx`, `app/.dockerignore`
- Create: `app/src/App.test.tsx`
- Modify: `justfile`, `.gitignore`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `pnpm --dir app dev`, `build`, `test`, `lint`, `typecheck`
  - `just app` runs the dev server on this worktree's `CLIENT_PORT`

- [ ] **Step 1: Create the package**

`app/package.json`:

```json
{
  "name": "statusboard-app",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "lint": "biome check --write .",
    "lint:ci": "biome ci .",
    "typecheck": "tsc -b --noEmit",
    "codegen": "orval --config orval.config.ts"
  }
}
```

Then install. Pinning exact versions rather than ranges keeps the lockfile the only thing
that decides a build:

```bash
cd app
pnpm add react react-dom @tanstack/react-query @tanstack/react-router lucide-react
pnpm add @radix-ui/react-dropdown-menu @radix-ui/react-tabs @radix-ui/react-dialog
pnpm add -D vite @vitejs/plugin-react typescript @types/react @types/react-dom
pnpm add -D @tanstack/router-plugin @biomejs/biome
pnpm add -D vitest jsdom @testing-library/react @testing-library/user-event msw
pnpm add -D tailwindcss @tailwindcss/vite orval
```

- [ ] **Step 2: Configure the build**

`app/vite.config.ts`:

```ts
import { TanStackRouterVite } from "@tanstack/router-plugin/vite";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [TanStackRouterVite(), react(), tailwindcss()],
  server: {
    // The worktree's reserved port, and the host the API already
    // trusts. See bin/worktree-env.py, which writes both.
    port: Number(process.env.CLIENT_PORT) || 5173,
    host: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
});
```

`app/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noEmit": true,
    "skipLibCheck": true,
    "types": ["vitest/globals"],
    "baseUrl": ".",
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["src"]
}
```

`app/biome.json`:

```json
{
  "$schema": "https://biomejs.dev/schemas/2.0.0/schema.json",
  "files": { "includes": ["src/**", "*.ts", "*.json"] },
  "formatter": { "enabled": true, "indentStyle": "space", "indentWidth": 2 },
  "linter": { "enabled": true, "rules": { "recommended": true } },
  "assist": { "actions": { "source": { "organizeImports": "on" } } }
}
```

The Biome schema URL must match the installed version. Read it from
`pnpm --dir app exec biome --version` and correct the URL if it differs.

`app/src/test-setup.ts`:

```ts
import "@testing-library/jest-dom/vitest";
```

Add `@testing-library/jest-dom` to the dev dependencies.

- [ ] **Step 3: Write the failing test**

`app/src/App.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { App } from "./App";

test("the app renders its name", () => {
  // The whole harness in one assertion: Vite, TypeScript, React and
  // the test environment. A failure here is the build, not a feature.
  render(<App />);
  expect(screen.getByText("Statusboard")).toBeInTheDocument();
});
```

- [ ] **Step 4: Run it to make sure it fails**

Run: `pnpm --dir app test`
Expected: FAIL. `./App` does not exist.

- [ ] **Step 5: Write the minimum that passes**

`app/src/App.tsx`:

```tsx
export function App() {
  return <h1>Statusboard</h1>;
}
```

`app/src/main.tsx`:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";

const root = document.getElementById("root");
if (!root) throw new Error("index.html has no #root");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

`app/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Statusboard</title>
    <script src="/config.js"></script>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`config.js` is written by the container entrypoint in Task 10. In development it does not
exist, and Task 4's config module falls back. A missing script tag is not an error.

- [ ] **Step 6: Run the test and the build**

Run: `pnpm --dir app test && pnpm --dir app build && pnpm --dir app lint`
Expected: PASS, a `dist/` directory, and no lint findings.

- [ ] **Step 7: Add the recipes**

In `justfile`, in the `Daily` group:

```make
# Run the client on this worktree's reserved port.
[group('Daily')]
app:
    @{{wt}} ; cd app && CLIENT_PORT=$CLIENT_PORT pnpm dev
```

Change `dev` so one command runs everything:

```make
# Run the app: stores, migrations, server, poller, client.
[group('Daily')]
dev: up migrate
    @{{wt}} ; trap 'kill 0' EXIT INT TERM ; \
      echo "api    http://$WORKTREE_SLUG.localhost:$DJANGO_PORT/" ; \
      echo "client http://$WORKTREE_SLUG.localhost:$CLIENT_PORT/" ; \
      (cd api && uv run celery -A api worker -B -l info) & \
      (cd app && CLIENT_PORT=$CLIENT_PORT pnpm dev) & \
      cd api && uv run python manage.py runserver 0.0.0.0:$DJANGO_PORT
```

In `.gitignore`:

```
# Node
node_modules/
app/dist/
```

- [ ] **Step 8: Prove it runs on the reserved port**

Run: `just app`, then open the URL `just info` prints for the client.

Expected: the page says Statusboard. The port matches `just info`, and the host is
`<slug>.localhost`, which the API's `CORS_ALLOWED_ORIGINS` already names.

An edit that ran without error is not an edit that worked. Open the page.

- [ ] **Step 9: Commit**

```bash
git add app justfile .gitignore
git commit -m "feat: the client app builds, lints and tests

A Vite SPA on its own origin. bin/worktree-env.py already reserves the
port and points the API's CORS at it, so a worktree serves both halves
without touching either config."
```

---

## Task 2: The palette is 26 tokens and nothing writes a hex

**Files:**
- Create: `app/src/styles/tokens.css`, `app/src/styles/app.css`
- Modify: `app/src/main.tsx`, `app/src/App.tsx`
- Test: `app/src/styles/tokens.test.ts`

**Interfaces:**
- Consumes: nothing
- Produces:
  - CSS variables `--u-0` to `--u-950`, the twelve status values, and the `--app-*` layer
  - Tailwind v4 `@theme` names, so `bg-app-card` and `text-crit` resolve

Both decks carry an identical core block. A change to it must be made in both, and here.

- [ ] **Step 1: Write the failing test**

`app/src/styles/tokens.test.ts`:

```ts
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("./tokens.css", import.meta.url), "utf8");

test("every core token the decks define is present", () => {
  // The decks are the source. A token missing here is a rule that
  // falls back to an inherited colour and looks almost right.
  const required = [
    "--u-0", "--u-50", "--u-100", "--u-200", "--u-300", "--u-400",
    "--u-500", "--u-550", "--u-600", "--u-700", "--u-800", "--u-850",
    "--u-900", "--u-950",
    "--green", "--green-ink", "--green-lift",
    "--amber", "--amber-ink", "--amber-lift",
    "--red", "--red-ink", "--red-lift",
    "--blue", "--blue-ink", "--blue-lift",
  ];
  for (const token of required) {
    expect(css).toContain(`${token}:`);
  }
});

test("the app layer names a token, never a hex", () => {
  // One hex outside the core block is a colour that no theme can
  // change, and it is invisible until somebody switches to dark.
  const appLayer = css.slice(css.indexOf("--app-ground"));
  expect(appLayer).not.toMatch(/#[0-9a-fA-F]{3,8}/);
});
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `pnpm --dir app test tokens`
Expected: FAIL. `tokens.css` does not exist.

- [ ] **Step 3: Write the tokens**

`app/src/styles/tokens.css`. These values are the decks' core block, copied exactly:

```css
/* The core palette. Every colour in the app is one of these.
   Both decks carry an identical copy, so a change is made in three
   places: this file, the mobile deck and the desktop deck.

   The neutrals are one ultramarine ramp, so no theme is a grey. Each
   status hue has three: the raw brand value for a dot or a fill, a
   darkened one for type on light, a lifted one for type on dark. The
   raw values fail contrast as text and are never used that way. */
:root {
  --u-0: #FFFFFF;
  --u-50: #F3F3FB;
  --u-100: #E9E9F6;
  --u-200: #DEDEF0;
  --u-300: #C6C5E4;
  --u-400: #A9A7D6;
  --u-500: #8A88B8;
  --u-550: #6F6F92;
  --u-600: #63628F;
  --u-700: #3B3A66;
  --u-800: #1A193F;
  --u-850: #12123A;
  --u-900: #0D0C2B;
  --u-950: #06061F;

  --green: #00E54D;
  --green-ink: #1C7A3E;
  --green-lift: #59CE87;
  --amber: #E58900;
  --amber-ink: #975800;
  --amber-lift: #E0A33F;
  --red: #E51F00;
  --red-ink: #B3180B;
  --red-lift: #F27967;
  --blue: #00A0E5;
  --blue-ink: #0B6C9D;
  --blue-lift: #66B5EC;
}

/* The app layer, light. Built from the core, and every rule is built
   from these. */
:root {
  --app-ground: var(--u-50);
  --app-card: var(--u-0);
  --app-edge: var(--u-200);
  --app-ink: var(--u-850);
  --app-ink-3: var(--u-550);
  --app-nav: var(--u-800);
  --app-nav-ink: var(--u-50);
  --app-chip: var(--u-200);

  /* Raw, for a fill or an indicator. */
  --app-ok: var(--green);
  --app-warn: var(--amber);
  --app-crit: var(--red);
  --app-maint: var(--blue);
  --app-none: var(--u-500);

  /* Darkened, for type. The raw values are about 1.8:1 on white. */
  --ok: var(--green-ink);
  --warn: var(--amber-ink);
  --crit: var(--red-ink);
  --maint: var(--blue-ink);
  --none: var(--u-500);
}

/* The app layer, dark. The decks render the app in light only, so
   these are derived rather than approved: the same swap the decks
   apply to their own chrome. Read them on a real screen before the
   theme control ships. */
:root[data-theme="dark"] {
  --app-ground: var(--u-950);
  --app-card: var(--u-900);
  --app-edge: var(--u-800);
  --app-ink: var(--u-200);
  --app-ink-3: var(--u-600);
  --app-nav: var(--u-900);
  --app-nav-ink: var(--u-200);
  --app-chip: var(--u-800);

  --ok: var(--green-lift);
  --warn: var(--amber-lift);
  --crit: var(--red-lift);
  --maint: var(--blue-lift);
  --none: var(--u-500);
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --app-ground: var(--u-950);
    --app-card: var(--u-900);
    --app-edge: var(--u-800);
    --app-ink: var(--u-200);
    --app-ink-3: var(--u-600);
    --app-nav: var(--u-900);
    --app-nav-ink: var(--u-200);
    --app-chip: var(--u-800);
    --ok: var(--green-lift);
    --warn: var(--amber-lift);
    --crit: var(--red-lift);
    --maint: var(--blue-lift);
  }
}
```

Theme has three states. An explicit choice stamps `data-theme` on the root. The default,
System, stamps nothing, so `prefers-color-scheme` decides. That is why the values appear
twice.

- [ ] **Step 4: Name them to Tailwind**

`app/src/styles/app.css`:

```css
@import "tailwindcss";
@import "./tokens.css";

/* Tailwind v4 builds its utilities from this block. `bg-app-card` and
   `text-crit` exist because these names do. */
@theme inline {
  --color-app-ground: var(--app-ground);
  --color-app-card: var(--app-card);
  --color-app-edge: var(--app-edge);
  --color-app-ink: var(--app-ink);
  --color-app-ink-3: var(--app-ink-3);
  --color-app-nav: var(--app-nav);
  --color-app-nav-ink: var(--app-nav-ink);
  --color-app-chip: var(--app-chip);
  --color-ok: var(--ok);
  --color-warn: var(--warn);
  --color-crit: var(--crit);
  --color-maint: var(--maint);
  --color-none: var(--none);
  --color-app-ok: var(--app-ok);
  --color-app-warn: var(--app-warn);
  --color-app-crit: var(--app-crit);
  --color-app-maint: var(--app-maint);
  --color-app-none: var(--app-none);
}

body {
  background: var(--app-ground);
  color: var(--app-ink);
}
```

Import it from `app/src/main.tsx`:

```tsx
import "./styles/app.css";
```

- [ ] **Step 5: Run the tests**

Run: `pnpm --dir app test && pnpm --dir app build`
Expected: PASS.

- [ ] **Step 6: Read the result back on a screen**

Run `just app`. In the browser's device toolbar, switch the emulated colour scheme to dark.

Expected: the ground goes to `#06061F` and the type stays legible. The derived dark values
are the one part of this file the decks never showed, so look at it rather than trusting it.

- [ ] **Step 7: Commit**

```bash
git add app
git commit -m "feat: the palette is 26 tokens, and no rule writes a hex

Both decks carry an identical core block, and this is the third copy.
The app layer is built from it, so a theme swaps twelve values rather
than every rule. Dark is derived: the decks render the app in light."
```

---

## Task 3: Every type comes from the contract

**Files:**
- Create: `app/orval.config.ts`, `app/src/api/` (generated)
- Modify: `app/package.json`, `justfile`
- Test: `app/src/api/generated.test.ts`

**Interfaces:**
- Consumes: `docs/api/openapi.yaml`
- Produces:
  - `app/src/api/statusboard.ts`, one hook per operation
  - `app/src/api/model/`, a type per schema
  - `app/src/api/statusboard.msw.ts`, the handlers tests use
  - `pnpm --dir app codegen`, and `just codegen` beside it

The contract is generated from the code and `api/tests/test_contract.py` holds the two
together. Hand-writing a type here would be a third answer to one question.

- [ ] **Step 1: Write the config**

`app/orval.config.ts`:

```ts
import { defineConfig } from "orval";

export default defineConfig({
  statusboard: {
    // The contract, not the running server. A generator that needed
    // the API up could not run in CI or in the image build.
    input: "../docs/api/openapi.yaml",
    output: {
      target: "./src/api/statusboard.ts",
      schemas: "./src/api/model",
      client: "react-query",
      mode: "split",
      mock: true,
      override: {
        // Every call goes through one place, so the token, the base
        // URL and the refresh live once.
        mutator: { path: "./src/lib/fetcher.ts", name: "fetcher" },
        query: { useSuspenseQuery: false },
      },
    },
    hooks: { afterAllFilesWrite: "biome check --write" },
  },
});
```

- [ ] **Step 2: Write the failing test**

`app/src/api/generated.test.ts`:

```ts
import { readdirSync } from "node:fs";

test("the contract's operations are generated", () => {
  // A missing hook means somebody hand-wrote a fetch, which is a
  // second definition of a shape the API already publishes.
  const files = readdirSync(new URL(".", import.meta.url));
  expect(files).toContain("statusboard.ts");
  expect(files).toContain("statusboard.msw.ts");
});

test("the component model carries the fields the row reads", async () => {
  // Renaming one in the API must break this build, not a screen.
  const model = await import("./model/component");
  const keys: (keyof typeof model.Component.prototype)[] = [];
  expect(keys).toBeDefined();
});
```

The second test is a compile-time check dressed as a runtime one. Replace its body with a
real import of the generated `Component` type once the shape is known:

```ts
import type { Component } from "./model";

test("the component model carries the fields the row reads", () => {
  const row: Pick<Component, "id" | "name" | "is_overall" | "descendant_count"> = {
    id: "x",
    name: "SMS",
    is_overall: false,
    descendant_count: 0,
  };
  expect(row.name).toBe("SMS");
});
```

If a field was renamed in the API, `tsc` fails here rather than a screen rendering blank.

- [ ] **Step 3: Run it to make sure it fails**

Run: `pnpm --dir app test generated`
Expected: FAIL. `src/api` does not exist.

- [ ] **Step 4: Generate, and commit the output**

`app/src/lib/fetcher.ts` has to exist before generation. Write a stub, and Task 4 fills it:

```ts
export async function fetcher<T>(config: {
  url: string;
  method: string;
  params?: unknown;
  data?: unknown;
  signal?: AbortSignal;
}): Promise<T> {
  throw new Error(`fetcher is not implemented yet: ${config.method} ${config.url}`);
}
```

Run: `pnpm --dir app codegen && pnpm --dir app test generated && pnpm --dir app typecheck`
Expected: PASS.

The generated tree is **committed**. A contract change then shows what it did to the client
in a reviewable diff.

- [ ] **Step 5: Fail CI on drift**

In `justfile`, in the `Daily` group:

```make
# Generate the API client from the contract.
[group('Daily')]
codegen:
    cd app && pnpm codegen
```

The drift check is a command, not a recipe, because it must not rewrite the tree it checks:

```make
# Every CI check but the image scan.
[group('Daily')]
check: image
    docker compose -f docker-compose.test.yml run --rm pytest -q -n auto --cov-fail-under=85
    docker compose -f docker-compose.test.yml run --rm ruff
    docker compose -f docker-compose.test.yml run --rm docs
    @python3 bin/check_prose.py
    @python3 -m unittest discover -s bin/tests -v
    docker compose -f docker-compose.test.yml run --rm --entrypoint sh pytest \
      -c 'python manage.py makemigrations --check --dry-run'
    cd app && pnpm install --frozen-lockfile && pnpm lint:ci && pnpm typecheck && pnpm test
    cd app && pnpm codegen && git diff --exit-code src/api
    docker compose -f docker-compose.test.yml down -v
```

`git diff --exit-code` is the whole check. Regenerating and finding a change means the
committed client no longer matches the contract.

- [ ] **Step 6: Prove the drift check catches a change**

Run:
```bash
cd app && echo "// tampered" >> src/api/statusboard.ts
pnpm codegen && git diff --exit-code src/api ; echo "exit: $?"
git checkout src/api
```

Expected: a non-zero exit. A check nobody has seen fail proves nothing.

- [ ] **Step 7: Hold the merge gate together**

`bin/tests/test_merge_gate.py` fails when `just check` runs a command CI does not. Task 10
adds the CI job. Run it now and expect a failure naming the client commands:

Run: `python3 -m unittest discover -s bin/tests`
Expected: FAIL, naming the two `cd app` lines. That failure is the reminder, and Task 10
clears it.

- [ ] **Step 8: Commit**

```bash
git add app justfile
git commit -m "feat: the client's types are generated from the contract

drf-spectacular generates the contract from the code, and a contract
test holds the two together. A hand-written type here would be a third
answer to one question. CI regenerates and fails on a diff."
```

---

## Task 4: One place knows the token, the base URL and the refresh

**Files:**
- Create: `app/src/lib/config.ts`, `app/src/lib/auth.ts`
- Modify: `app/src/lib/fetcher.ts`
- Test: `app/src/lib/auth.test.ts`, `app/src/lib/fetcher.test.ts`

**Interfaces:**
- Consumes: `app/src/api/model` for `TokenPair`
- Produces:
  - `config.apiUrl: string`
  - `auth.tokens(): TokenPair | null`, `auth.signIn(pair)`, `auth.signOut()`,
    `auth.subscribe(fn)`
  - `fetcher<T>(config)` attaches the access token, refreshes once on 401, and retries

The access token lives in memory. The refresh token lives in local storage. A strict CSP is
what makes that acceptable, and Task 10 sets it.

- [ ] **Step 1: Write the failing tests**

`app/src/lib/auth.test.ts`:

```ts
import { auth } from "./auth";

beforeEach(() => {
  localStorage.clear();
  auth.signOut();
});

test("the access token never reaches local storage", () => {
  // It is the credential a script would want. Only the refresh
  // survives a reload, and only because a session has to.
  auth.signIn({ access: "a", refresh: "r" });
  expect(JSON.stringify(localStorage)).not.toContain("a");
  expect(JSON.stringify(localStorage)).toContain("r");
});

test("a reload keeps the session and loses the access token", () => {
  // The refresh is what a reload spends to get a new access token.
  auth.signIn({ access: "a", refresh: "r" });
  auth.forgetAccessToken();
  expect(auth.tokens()?.access).toBeUndefined();
  expect(auth.tokens()?.refresh).toBe("r");
});

test("signing out clears both", () => {
  auth.signIn({ access: "a", refresh: "r" });
  auth.signOut();
  expect(auth.tokens()).toBeNull();
  expect(localStorage.length).toBe(0);
});
```

`app/src/lib/fetcher.test.ts`:

```ts
import { auth } from "./auth";
import { fetcher } from "./fetcher";

beforeEach(() => {
  auth.signOut();
  vi.restoreAllMocks();
});

test("a 401 refreshes once and retries", async () => {
  // A rotating access token expires mid-session. Without the retry
  // every screen would bounce a signed-in reader to the sign-in page.
  auth.signIn({ access: "old", refresh: "r" });
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      calls.push(url);
      if (url.endsWith("/auth/refresh/")) {
        return new Response(JSON.stringify({ access: "new", refresh: "r2" }), {
          status: 200,
        });
      }
      if (calls.filter((c) => c.endsWith("/me/")).length === 1) {
        return new Response("", { status: 401 });
      }
      return new Response(JSON.stringify({ email: "a@b.c" }), { status: 200 });
    }),
  );

  const body = await fetcher<{ email: string }>({ url: "/me/", method: "GET" });

  expect(body.email).toBe("a@b.c");
  expect(calls.filter((c) => c.endsWith("/auth/refresh/"))).toHaveLength(1);
  expect(auth.tokens()?.access).toBe("new");
});

test("a second 401 signs the reader out rather than looping", async () => {
  // A refresh token can be revoked or expired. Retrying forever
  // would hammer the API from every open tab.
  auth.signIn({ access: "old", refresh: "r" });
  vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 401 })));

  await expect(fetcher({ url: "/me/", method: "GET" })).rejects.toThrow();
  expect(auth.tokens()).toBeNull();
});

test("a signed-out read carries no header", async () => {
  // The catalog is public. Sending an empty Authorization header
  // would make every anonymous read a 401.
  const seen: RequestInit[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url: string, init: RequestInit) => {
      seen.push(init);
      return new Response(JSON.stringify({}), { status: 200 });
    }),
  );

  await fetcher({ url: "/catalog/components/", method: "GET" });

  const headers = new Headers(seen[0]?.headers);
  expect(headers.has("Authorization")).toBe(false);
});
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `pnpm --dir app test lib`
Expected: FAIL. `./auth` does not exist and `fetcher` throws.

- [ ] **Step 3: Write the config reader**

`app/src/lib/config.ts`:

```ts
/** What the deployment told the page at start.
 *
 * A Vite build inlines a VITE_ value, which would make the image
 * environment-specific. The entrypoint writes `config.js` instead, so
 * one image answers anywhere. See app/entrypoint.sh.
 */
declare global {
  interface Window {
    STATUSBOARD_CONFIG?: { apiUrl?: string };
  }
}

function apiUrl(): string {
  const written = window.STATUSBOARD_CONFIG?.apiUrl;
  if (written) return written.replace(/\/$/, "");
  // Development. The API answers on the same host, on its own port,
  // which bin/worktree-env.py reserved.
  return `${window.location.protocol}//${window.location.hostname}:8000`;
}

export const config = { apiUrl: apiUrl() };
```

The development fallback needs the worktree's `DJANGO_PORT`, which the page cannot know.
Pass it through Vite instead, since it is development only:

```ts
  return import.meta.env.VITE_API_URL ?? "http://localhost:8000";
```

and add `VITE_API_URL` to the `just app` recipe:

```make
app:
    @{{wt}} ; cd app && CLIENT_PORT=$CLIENT_PORT \
      VITE_API_URL="http://$WORKTREE_SLUG.localhost:$DJANGO_PORT" pnpm dev
```

A `VITE_` value is acceptable here because it never reaches the image. `config.js` wins
whenever it exists, which is every deployment.

- [ ] **Step 4: Write the token store**

`app/src/lib/auth.ts`:

```ts
import type { TokenPair } from "@/api/model";

const KEY = "statusboard.refresh";

/** The pair, and who to tell when it changes.
 *
 * The access token stays in memory. It is the credential worth
 * stealing, and it lives fifteen minutes. The refresh token has to
 * survive a reload, so it is in local storage, which a strict CSP is
 * what makes acceptable.
 */
let access: string | undefined;
const listeners = new Set<() => void>();

function announce() {
  for (const listener of listeners) listener();
}

export const auth = {
  tokens(): { access?: string; refresh: string } | null {
    const refresh = localStorage.getItem(KEY);
    return refresh ? { access, refresh } : null;
  },

  signIn(pair: TokenPair) {
    access = pair.access;
    localStorage.setItem(KEY, pair.refresh);
    announce();
  },

  signOut() {
    access = undefined;
    localStorage.removeItem(KEY);
    announce();
  },

  /** Drop the access token and keep the session. For tests, and for a
   * reload, which loses it anyway. */
  forgetAccessToken() {
    access = undefined;
  },

  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};
```

- [ ] **Step 5: Write the mutator**

`app/src/lib/fetcher.ts`:

```ts
import { auth } from "./auth";
import { config } from "./config";

type Call = {
  url: string;
  method: string;
  params?: Record<string, unknown>;
  data?: unknown;
  headers?: HeadersInit;
  signal?: AbortSignal;
};

function query(params?: Record<string, unknown>): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

async function send(call: Call, token?: string): Promise<Response> {
  const headers = new Headers(call.headers);
  if (call.data !== undefined) headers.set("Content-Type", "application/json");
  // A signed-out reader sends no header at all. The catalog is public,
  // and an empty Authorization is a 401 rather than an anonymous read.
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(`${config.apiUrl}${call.url}${query(call.params)}`, {
    method: call.method,
    headers,
    body: call.data === undefined ? undefined : JSON.stringify(call.data),
    signal: call.signal,
  });
}

async function refresh(): Promise<boolean> {
  const held = auth.tokens();
  if (!held) return false;
  const response = await fetch(`${config.apiUrl}/auth/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh: held.refresh }),
  });
  if (!response.ok) return false;
  auth.signIn(await response.json());
  return true;
}

export async function fetcher<T>(call: Call): Promise<T> {
  let response = await send(call, auth.tokens()?.access);

  // The access token rotates every fifteen minutes, so a signed-in
  // reader meets a 401 mid-session. One retry, then out: a revoked
  // refresh token would otherwise loop from every open tab.
  if (response.status === 401 && auth.tokens()) {
    if (await refresh()) {
      response = await send(call, auth.tokens()?.access);
    } else {
      auth.signOut();
    }
  }

  if (!response.ok) {
    if (response.status === 401) auth.signOut();
    throw new Error(`${call.method} ${call.url} answered ${response.status}`);
  }
  return response.status === 204 ? (undefined as T) : await response.json();
}
```

- [ ] **Step 6: Run the tests**

Run: `pnpm --dir app test lib && pnpm --dir app typecheck`
Expected: PASS, all six.

- [ ] **Step 7: Commit**

```bash
git add app justfile
git commit -m "feat: one place attaches the token and rotates it

The access token stays in memory and the refresh token survives a
reload. A 401 mid-session refreshes once and retries, so a rotating
token does not bounce a signed-in reader to the sign-in page."
```

---

## Task 5: A URL is the whole of a screen's state

**Files:**
- Create: `app/src/lib/search.ts`, `app/src/routes/__root.tsx`, `app/src/routes/index.tsx`,
  and a stub per remaining route
- Modify: `app/src/main.tsx`
- Test: `app/src/lib/search.test.ts`

**Interfaces:**
- Consumes: `@/api/model` for the enums
- Produces:
  - `homeSearch`, `discoverSearch`, `serviceSearch`, `componentSearch`, `eventSearch`
  - the nine routes, each with a `validateSearch`

Every filter is server-side, so every filter belongs in the URL. A bad value fails validation
in one place rather than reaching the API.

- [x] **Step 1: Write the failing test**

`app/src/lib/search.test.ts`:

```ts
import { homeSearch, serviceSearch } from "./search";

test("a missing tab reads as the default", () => {
  // A bare `/` is Home's board. Were the tab required, every link
  // written by hand would have to name it.
  expect(homeSearch({})).toMatchObject({ tab: "board" });
});

test("an unknown tab falls back rather than rendering nothing", () => {
  // A stale bookmark or a typo must not leave a blank screen.
  expect(homeSearch({ tab: "nonsense" })).toMatchObject({ tab: "board" });
});

test("severity is parsed to a number the API accepts", () => {
  // The parameter reaches the API as `status__severity`, an integer.
  // A string would be a 400 from a control the reader just used.
  expect(homeSearch({ tab: "board", severity: "2" })).toMatchObject({ severity: 2 });
});

test("a severity outside the six values is dropped", () => {
  // Severity is 0 to 5. Nothing else is a state the API knows.
  expect(homeSearch({ severity: "9" }).severity).toBeUndefined();
});

test("the service screen keeps its own three tabs", () => {
  // Each screen validates only the tabs it has, so a link from one
  // screen cannot select a tab another screen owns.
  expect(serviceSearch({ tab: "timeline" })).toMatchObject({ tab: "components" });
});
```

- [x] **Step 2: Run it to make sure it fails**

Run: `pnpm --dir app test search`
Expected: FAIL. `./search` does not exist.

- [x] **Step 3: Write the schemas**

`app/src/lib/search.ts`:

```ts
/** What a URL may say, per screen.
 *
 * Every filter is server-side, so a URL is the whole of a screen's
 * state and a reload restores it. A value the API would refuse is
 * dropped here, once, rather than by each screen.
 */

type Raw = Record<string, unknown>;

function oneOf<T extends string>(values: readonly T[], fallback: T) {
  return (raw: unknown): T => {
    const text = String(raw ?? "");
    return (values as readonly string[]).includes(text) ? (text as T) : fallback;
  };
}

function severity(raw: unknown): number | undefined {
  const value = Number(raw);
  // Severity is 0 to 5, and 0 is a real value, so a falsy check
  // would silently drop the worst one.
  return Number.isInteger(value) && value >= 0 && value <= 5 ? value : undefined;
}

function text(raw: unknown): string | undefined {
  const value = String(raw ?? "").trim();
  return value === "" ? undefined : value;
}

const homeTab = oneOf(["board", "updates"] as const, "board");
const discoverTab = oneOf(["components"] as const, "components");
const serviceTab = oneOf(["components", "updates", "about"] as const, "components");
const componentTab = oneOf(["components", "updates"] as const, "components");
const eventTab = oneOf(["timeline", "affects", "about"] as const, "timeline");
const kind = oneOf(["incident", "maintenance"] as const, "incident");
const phase = oneOf(["open", "closed"] as const, "open");
const tracking = oneOf(["all", "tracked", "untracked"] as const, "all");

export function homeSearch(raw: Raw) {
  return {
    tab: homeTab(raw.tab),
    severity: severity(raw.severity),
    service: text(raw.service),
    component: text(raw.component),
    kind: raw.kind === undefined ? undefined : kind(raw.kind),
    phase: raw.phase === undefined ? undefined : phase(raw.phase),
  };
}

export function discoverSearch(raw: Raw) {
  return { tab: discoverTab(raw.tab), q: text(raw.q), severity: severity(raw.severity) };
}

export function serviceSearch(raw: Raw) {
  return {
    tab: serviceTab(raw.tab),
    severity: severity(raw.severity),
    tracking: raw.tracking === undefined ? undefined : tracking(raw.tracking),
    component: text(raw.component),
    kind: raw.kind === undefined ? undefined : kind(raw.kind),
    phase: raw.phase === undefined ? undefined : phase(raw.phase),
  };
}

export function componentSearch(raw: Raw) {
  const { component, ...rest } = serviceSearch(raw);
  return { ...rest, tab: componentTab(raw.tab) };
}

export function eventSearch(raw: Raw) {
  return { tab: eventTab(raw.tab) };
}
```

`oneOf` falls back rather than throwing. TanStack Router treats a throw from
`validateSearch` as a routing error, and a stale bookmark should show the default screen
rather than an error page.

- [x] **Step 4: Write the root route**

`app/src/routes/__root.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Outlet, createRootRoute } from "@tanstack/react-router";

const client = new QueryClient({
  defaultOptions: {
    queries: {
      // There is no offline mode. A cached board would answer
      // yesterday's question, which is worse than saying nothing.
      staleTime: 0,
      gcTime: 0,
      retry: 1,
      refetchOnWindowFocus: true,
    },
  },
});

export const Route = createRootRoute({
  component: () => (
    <QueryClientProvider client={client}>
      <Outlet />
    </QueryClientProvider>
  ),
});
```

- [x] **Step 5: Write the nine routes**

Each is a file under `app/src/routes/`. The plugin builds the tree from the names.

| File | Route |
| --- | --- |
| `index.tsx` | `/` |
| `discover.index.tsx` | `/discover` |
| `discover.add.tsx` | `/discover/add` |
| `services.$slug.tsx` | `/services/$slug` |
| `components.$id.tsx` | `/components/$id` |
| `events.$id.tsx` | `/events/$id` |
| `signin.tsx` | `/signin` |
| `verify.tsx` | `/verify` |
| `settings.tsx` | `/settings` |

`app/src/routes/index.tsx`:

```tsx
import { createFileRoute } from "@tanstack/react-router";
import { homeSearch } from "@/lib/search";

export const Route = createFileRoute("/")({
  validateSearch: homeSearch,
  component: Home,
});

function Home() {
  const { tab } = Route.useSearch();
  return <main>{tab}</main>;
}
```

Every other route is the same shape with its own schema. Task 8 fills `/` in, and the
following plan fills the rest. A stub that renders its tab name is enough to prove the
routing works.

`app/src/routes/verify.tsx` takes a token rather than a tab:

```tsx
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/verify")({
  validateSearch: (raw: Record<string, unknown>) => ({
    token: String(raw.token ?? ""),
  }),
  component: () => <main>verify</main>,
});
```

- [x] **Step 6: Mount the router**

`app/src/main.tsx`:

```tsx
import { RouterProvider, createRouter } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { routeTree } from "./routeTree.gen";
import "./styles/app.css";

const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

const root = document.getElementById("root");
if (!root) throw new Error("index.html has no #root");

createRoot(root).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
```

`routeTree.gen.ts` is written by the Vite plugin on first run. Add it to
`app/.gitignore`, and to Biome's ignore list: it is generated and reformatting it fights
the plugin.

Delete `app/src/App.tsx` and its test. The router replaced them, and a component nothing
renders is a second front door.

- [x] **Step 7: Run everything**

Run: `pnpm --dir app test && pnpm --dir app typecheck && pnpm --dir app build`
Expected: PASS.

- [x] **Step 8: Read the URLs back**

Run `just app` and open, in order:

- `/` shows `board`
- `/?tab=updates` shows `updates`
- `/?tab=nonsense` shows `board`, not an error
- `/services/twilio?tab=about` shows `about`

The third is the one worth checking by hand. A schema that throws would show an error page
here, and a stale bookmark is the case it exists for.

- [x] **Step 9: Commit**

```bash
git add app
git commit -m "feat: a URL is the whole of a screen's state

Every filter is server-side, so every filter is a search parameter. A
value the API would refuse is dropped in one schema rather than by
each screen, and an unknown tab falls back instead of erroring."
```

---

## Task 6: The shell every screen sits in

**Files:**
- Create: `app/src/components/Nav.tsx`, `app/src/components/Header.tsx`,
  `app/src/components/Shell.tsx`
- Modify: `app/src/routes/__root.tsx`
- Test: `app/src/components/Nav.test.tsx`

**Interfaces:**
- Consumes: `auth`, `@tanstack/react-router`'s `Link`
- Produces: `<Shell title="Home">…</Shell>`, wrapping every screen

Three destinations. The third is Sign in when signed out and Settings when signed in. Signed
out and signed in are the same screens; only the buttons differ.

- [x] **Step 1: Write the failing test**

`app/src/components/Nav.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { auth } from "@/lib/auth";
import { Nav } from "./Nav";

beforeEach(() => auth.signOut());

test("the third slot is Sign in when signed out", () => {
  // Signed out and signed in are the same screens. Only this slot
  // and a row's glyph change.
  render(<Nav />, { wrapper: routerWrapper });
  expect(screen.getByText("Sign in")).toBeInTheDocument();
  expect(screen.queryByText("Settings")).not.toBeInTheDocument();
});

test("the third slot is Settings when signed in", () => {
  auth.signIn({ access: "a", refresh: "r" });
  render(<Nav />, { wrapper: routerWrapper });
  expect(screen.getByText("Settings")).toBeInTheDocument();
});

test("every destination is a link, not a button", () => {
  // A tab must open in a new window and be copied as a URL. A
  // button does neither.
  render(<Nav />, { wrapper: routerWrapper });
  expect(screen.getAllByRole("link")).toHaveLength(3);
});
```

`routerWrapper` renders children inside a memory router, because `Link` needs one. Put it
in `app/src/test-utils.tsx`:

```tsx
import {
  RouterProvider,
  createMemoryHistory,
  createRootRoute,
  createRouter,
} from "@tanstack/react-router";
import type { ReactNode } from "react";

export function routerWrapper({ children }: { children: ReactNode }) {
  const root = createRootRoute({ component: () => <>{children}</> });
  const router = createRouter({
    routeTree: root,
    history: createMemoryHistory({ initialEntries: ["/"] }),
  });
  return <RouterProvider router={router} />;
}
```

- [x] **Step 2: Run it to make sure it fails**

Run: `pnpm --dir app test Nav`
Expected: FAIL. `./Nav` does not exist.

- [x] **Step 3: Write the nav**

`app/src/components/Nav.tsx`:

```tsx
import { Link } from "@tanstack/react-router";
import { Compass, House, LogIn, Settings } from "lucide-react";
import { useSyncExternalStore } from "react";
import { auth } from "@/lib/auth";

/** Three destinations, in a pill on a phone and a bar on a desktop.
 *
 * Every icon is Lucide. The Figma marks are filled and Lucide is
 * stroked, and one nav cannot carry two weights.
 */
export function Nav() {
  const signedIn = useSyncExternalStore(
    auth.subscribe,
    () => auth.tokens() !== null,
    () => false,
  );

  const third = signedIn
    ? { to: "/settings", label: "Settings", Icon: Settings }
    : { to: "/signin", label: "Sign in", Icon: LogIn };

  const items = [
    { to: "/", label: "Home", Icon: House },
    { to: "/discover", label: "Discover", Icon: Compass },
    third,
  ] as const;

  return (
    <nav
      className="fixed inset-x-4 bottom-4 flex justify-around rounded-full
                 bg-app-nav px-2 py-2 text-app-nav-ink
                 md:static md:inset-auto md:justify-start md:gap-6 md:rounded-none
                 md:bg-transparent md:px-0 md:text-app-ink"
    >
      {items.map(({ to, label, Icon }) => (
        <Link
          key={to}
          to={to}
          className="flex flex-col items-center gap-1 px-4 py-1 text-xs
                     md:flex-row md:gap-2 md:text-sm"
          activeProps={{ className: "font-semibold" }}
        >
          <Icon size={20} aria-hidden />
          {label}
        </Link>
      ))}
    </nav>
  );
}
```

`useSyncExternalStore` is why `auth.subscribe` exists. Reading `auth.tokens()` in render
would not re-render the nav when a sign-in completes on another screen.

- [x] **Step 4: Write the header and the shell**

`app/src/components/Header.tsx`:

```tsx
/** Brand and the refresh stamp on one row, the page title on the next.
 *
 * The stamp is not a control. There is no manual refresh: a page load
 * already shows the freshest data the poller holds.
 */
export function Header({
  title,
  checkedAt,
}: {
  title: string;
  checkedAt?: string | null;
}) {
  return (
    <header className="px-4 pt-4">
      <div className="flex items-baseline justify-between">
        <span className="font-semibold">statusboard</span>
        {checkedAt ? (
          <span className="text-xs text-app-ink-3">Checked {checkedAt}</span>
        ) : null}
      </div>
      <h1 className="mt-3 text-2xl font-semibold">{title}</h1>
    </header>
  );
}
```

`app/src/components/Shell.tsx`:

```tsx
import type { ReactNode } from "react";
import { Header } from "./Header";
import { Nav } from "./Nav";

export function Shell({
  title,
  checkedAt,
  children,
}: {
  title: string;
  checkedAt?: string | null;
  children: ReactNode;
}) {
  return (
    <div className="mx-auto min-h-dvh max-w-5xl pb-24 md:pb-8">
      <Header title={title} checkedAt={checkedAt} />
      <main className="px-4 py-4">{children}</main>
      <Nav />
    </div>
  );
}
```

`pb-24` is the phone's bottom pill. Without it the last row sits under the nav, which is
the kind of thing only a real screen shows.

- [x] **Step 5: Run the tests**

Run: `pnpm --dir app test && pnpm --dir app typecheck`
Expected: PASS.

- [ ] **Step 6: Read both layouts back**  <!-- deferred: no screen renders Shell until Task 8 -->

Run `just app`. In the browser's device toolbar, look at 390px and at 1280px.

Expected: a rounded pill inset from the bottom on the phone, and a row at the top on the
desktop. Both are the same three items.

- [x] **Step 7: Commit**

```bash
git add app
git commit -m "feat: the shell three screens sit in

Three destinations, and the third is Sign in or Settings. Signed out
and signed in are the same screens, so nothing else moves. Icons are
Lucide throughout: one nav cannot carry two weights."
```

---

## Task 7: The row every list is made of

**Files:**
- Create: `app/src/components/Row.tsx`, `app/src/lib/severity.ts`, `app/src/lib/duration.ts`
- Test: `app/src/components/Row.test.tsx`, `app/src/lib/duration.test.ts`

**Interfaces:**
- Consumes: `Component` from `@/api/model`, `/meta/` for the severity labels
- Produces:
  - `<Row component={…} showMark={…} onTrack={…} />`
  - `severityTone(severity) -> "ok" | "warn" | "crit" | "maint" | "none"`
  - `rowHref(component) -> string`
  - `since(iso) -> string`

Home, Discover and the service screen render the same card. The row carries its state as a
tint, and there is no dot.

- [x] **Step 1: Write the failing tests**

`app/src/lib/duration.test.ts`:

```ts
import { since } from "./duration";

test("a duration is coarse, because a row is scanned", () => {
  // "38 min" and "2 hrs" are read at a glance. Seconds would move
  // on every render and say nothing.
  const now = new Date("2026-09-04T12:00:00Z");
  expect(since("2026-09-04T11:22:00Z", now)).toBe("38 min");
  expect(since("2026-09-04T10:00:00Z", now)).toBe("2 hrs");
  expect(since("2026-08-29T12:00:00Z", now)).toBe("6 days");
});

test("under a minute reads as just now", () => {
  // "0 min" reads as broken. A state that just changed has no
  // duration worth stating.
  const now = new Date("2026-09-04T12:00:00Z");
  expect(since("2026-09-04T11:59:40Z", now)).toBe("just now");
});
```

`app/src/components/Row.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { routerWrapper } from "@/test-utils";
import { Row } from "./Row";

const component = {
  id: "c1",
  name: "SMS",
  is_overall: false,
  descendant_count: 0,
  is_tracked: false,
  path: [{ id: "p1", name: "Programmable Messaging", is_overall: false }],
  service: { id: "s1", slug: "twilio", name: "Twilio", logo: "" },
  status: { severity: 2, started_at: "2026-09-04T10:00:00Z" },
};

test("a row is the name, then the state and how long it has held", () => {
  // Two lines. A 232px phone row cannot hold two things that must
  // not truncate.
  render(<Row component={component} />, { wrapper: routerWrapper });
  expect(screen.getByText("SMS")).toBeInTheDocument();
  expect(screen.getByText(/Degraded/)).toBeInTheDocument();
  expect(screen.getByText(/2 hrs/)).toBeInTheDocument();
});

test("the only third line is a parent", () => {
  // Not a count, not "Overall status", not a tracking line. Those
  // said what kind of row it was rather than its condition.
  render(<Row component={component} />, { wrapper: routerWrapper });
  expect(screen.getByText(/Programmable Messaging/)).toBeInTheDocument();
});

test("an overall component links to its service, not to itself", () => {
  // A service's rollup is the service. Its own page would be the
  // same list with a different header.
  const rollup = { ...component, is_overall: true, name: "Twilio", path: [] };
  render(<Row component={rollup} />, { wrapper: routerWrapper });
  expect(screen.getByRole("link")).toHaveAttribute("href", "/services/twilio");
});

test("a component links to its own page", () => {
  render(<Row component={component} />, { wrapper: routerWrapper });
  expect(screen.getByRole("link")).toHaveAttribute("href", "/components/c1");
});

test("operational carries no tint", () => {
  // A list is scanned for colour. Tinting the healthy rows makes
  // every row shout, so nothing does.
  const fine = { ...component, status: { severity: 5, started_at: "2026-09-04T10:00:00Z" } };
  const { container } = render(<Row component={fine} />, { wrapper: routerWrapper });
  expect(container.querySelector("[data-tone]")).toHaveAttribute("data-tone", "ok");
  expect(container.querySelector("[data-tinted='true']")).toBeNull();
});
```

- [x] **Step 2: Run them to make sure they fail**

Run: `pnpm --dir app test Row duration`
Expected: FAIL. Neither module exists.

- [x] **Step 3: Write the helpers**

`app/src/lib/duration.ts`:

```ts
const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** How long a state has held, coarsely.
 *
 * A row is scanned, not read. Seconds change on every render and
 * answer a question nobody asked of a list.
 */
export function since(iso: string, now: Date = new Date()): string {
  const elapsed = now.getTime() - new Date(iso).getTime();
  if (elapsed < MINUTE) return "just now";
  if (elapsed < HOUR) return `${Math.floor(elapsed / MINUTE)} min`;
  if (elapsed < DAY) {
    const hours = Math.floor(elapsed / HOUR);
    return `${hours} ${hours === 1 ? "hr" : "hrs"}`;
  }
  const days = Math.floor(elapsed / DAY);
  return `${days} ${days === 1 ? "day" : "days"}`;
}
```

`app/src/lib/severity.ts`:

```ts
/** Which colour a severity carries.
 *
 * `/meta/` publishes the labels, so nothing here spells one. The
 * tone is the only thing a client decides, because it is a design
 * fact rather than a data one.
 */
export type Tone = "ok" | "warn" | "crit" | "maint" | "none";

export function severityTone(severity: number | undefined): Tone {
  switch (severity) {
    case 0:
    case 1:
      return "crit";
    case 2:
      return "warn";
    case 3:
      return "none";
    case 4:
      return "maint";
    case 5:
      return "ok";
    default:
      return "none";
  }
}
```

Severity 0 and 1 are both red. The deck gives major and partial outage one colour and two
words, and the word comes from `/meta/`.

- [x] **Step 4: Write the row**

`app/src/components/Row.tsx`:

```tsx
import { Link } from "@tanstack/react-router";
import { MoreVertical, Plus } from "lucide-react";
import type { Component } from "@/api/model";
import { since } from "@/lib/duration";
import { severityTone } from "@/lib/severity";

/** One component, on every list that has them.
 *
 * The row carries its state as a tint and a coloured edge. There is
 * no dot: a dot that appeared on operational and nowhere else was the
 * odd one out.
 */
export function Row({
  component,
  label,
  showMark = false,
  onTrack,
}: {
  component: Component;
  label?: string;
  showMark?: boolean;
  onTrack?: (component: Component) => void;
}) {
  const tone = severityTone(component.status?.severity);
  const tinted = tone !== "ok";
  // A rollup is its service. Its own page would be the same list
  // under a different header.
  const href = component.is_overall
    ? `/services/${component.service.slug}`
    : `/components/${component.id}`;
  // The only third line, and only when the component sits under
  // another. A count or a tracking line described the row, not it.
  const parent = component.path?.at(-1)?.name;

  return (
    <div
      data-tone={tone}
      data-tinted={tinted}
      className={`relative rounded-2xl border bg-app-card p-3
        ${tinted ? `border-${tone}/30 bg-${tone}/15` : "border-app-edge"}`}
    >
      <Link to={href} className="block">
        <div className="flex items-start gap-2">
          {showMark ? <Mark component={component} /> : null}
          <div className="min-w-0 flex-1">
            <div className="truncate font-medium">{component.name}</div>
            <div className={`text-sm text-${tone}`}>
              {label ?? "—"}
              {component.status?.started_at ? (
                <span className="ml-2 font-mono text-app-ink-3">
                  {since(component.status.started_at)}
                </span>
              ) : null}
            </div>
            {parent ? (
              <div className="truncate text-xs text-app-ink-3">{parent}</div>
            ) : null}
          </div>
        </div>
      </Link>

      {onTrack ? (
        <button
          type="button"
          aria-label={component.is_tracked ? "Row menu" : "Track"}
          onClick={() => onTrack(component)}
          className="absolute right-3 bottom-3 rounded-full border border-app-edge p-1"
        >
          {component.is_tracked ? <MoreVertical size={16} /> : <Plus size={16} />}
        </button>
      ) : null}
    </div>
  );
}

function Mark({ component }: { component: Component }) {
  const { logo, name } = component.service;
  return logo ? (
    <img src={logo} alt="" className="size-6 rounded-full" />
  ) : (
    <span className="grid size-6 place-items-center rounded-full bg-app-chip text-xs">
      {name.charAt(0)}
    </span>
  );
}
```

Tailwind cannot see `border-${tone}/30` and will not emit those classes. Replace the
template strings with a lookup, which is also where the one definition of a tone's classes
belongs:

```tsx
const TONE: Record<Tone, { edge: string; fill: string; text: string }> = {
  ok: { edge: "border-app-edge", fill: "", text: "text-ok" },
  warn: { edge: "border-warn/30", fill: "bg-warn/15", text: "text-warn" },
  crit: { edge: "border-crit/30", fill: "bg-crit/15", text: "text-crit" },
  maint: { edge: "border-maint/30", fill: "bg-maint/15", text: "text-maint" },
  none: { edge: "border-none/30", fill: "bg-none/15", text: "text-none" },
};
```

Every class is then a literal Tailwind can find.

`label` is the severity word, which the caller reads from `/meta/`. The row spells no
state, so a label change ships without touching this file.

- [x] **Step 5: Run the tests**

Run: `pnpm --dir app test && pnpm --dir app typecheck`
Expected: PASS, all seven.

- [x] **Step 6: Commit**

```bash
git add app
git commit -m "feat: the row every list is made of

Home, Discover and a service render one card. It carries its state as
a tint and a coloured edge rather than a dot, and its only third line
is a parent. The severity word comes from /meta/, so the row spells
no state."
```

---

## Task 8: Home shows your board

**Files:**
- Modify: `app/src/routes/index.tsx`
- Create: `app/src/lib/meta.ts`, `app/src/routes/index.test.tsx`

**Interfaces:**
- Consumes: the generated `useMetaRetrieve`, `useMeRetrieve`,
  `useBoardComponentsList`, `useCatalogComponentsList`, and `Row`
- Produces: the first screen that reads the live API

Signed out, Home is one row per service. Signed in, it is your board. Same screen, same row.

- [ ] **Step 1: Write the failing test**

`app/src/routes/index.test.tsx`, driven by Orval's generated MSW handlers:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { setupServer } from "msw/node";
import { auth } from "@/lib/auth";
import { getStatusboardMSW } from "@/api/statusboard.msw";

const server = setupServer(...getStatusboardMSW());
beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

test("signed out, Home lists one row per service", async () => {
  // A board is one row per service when nothing is yours. Narrowing
  // to overall components is what makes signed out and signed in the
  // same screen.
  auth.signOut();
  render(<HomeRoute />, { wrapper: appWrapper });
  await waitFor(() => expect(screen.getAllByRole("link").length).toBeGreaterThan(0));
});

test("the severity word comes from /meta/, not from the client", async () => {
  // The labels have one home. A new value must reach every screen
  // without a client release.
  render(<HomeRoute />, { wrapper: appWrapper });
  await waitFor(() => expect(screen.getByText(/Operational|Degraded/)).toBeInTheDocument());
});

test("an unreachable API says so and offers a retry", async () => {
  // There is no offline mode and no stale cache. A failed request
  // shows a plain state rather than yesterday's answer.
  server.use(errorHandlerFor("/catalog/components/"));
  render(<HomeRoute />, { wrapper: appWrapper });
  await waitFor(() =>
    expect(screen.getByText(/can't reach statusboard/i)).toBeInTheDocument(),
  );
  expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
});
```

`appWrapper` is `routerWrapper` with a `QueryClientProvider` around it, and a fresh
`QueryClient` per test so one test's cache cannot answer another's request. Add it to
`app/src/test-utils.tsx`.

`errorHandlerFor` is an MSW handler returning 500 for one path. Write it beside
`appWrapper`.

- [ ] **Step 2: Run it to make sure it fails**

Run: `pnpm --dir app test index`
Expected: FAIL. The route renders its tab name and nothing else.

- [ ] **Step 3: Read the labels once**

`app/src/lib/meta.ts`:

```ts
import { useMetaRetrieve } from "@/api/statusboard";

/** The labels every screen renders, fetched once at app start.
 *
 * `/meta/` publishes the 0 to 5 severity map, so a label change ships
 * without touching a serializer or a screen.
 */
export function useSeverityLabels(): Record<string, string> {
  const { data } = useMetaRetrieve({
    query: { staleTime: Number.POSITIVE_INFINITY, gcTime: Number.POSITIVE_INFINITY },
  });
  return data?.enums?.severity ?? {};
}
```

`/meta/` is the one query that is cached forever. It is deployment-wide configuration, not
status, so the no-stale-cache rule does not apply to it.

- [ ] **Step 4: Write the screen**

`app/src/routes/index.tsx`:

```tsx
import { createFileRoute } from "@tanstack/react-router";
import { useSyncExternalStore } from "react";
import {
  useBoardComponentsList,
  useCatalogComponentsList,
  useMeRetrieve,
} from "@/api/statusboard";
import { Row } from "@/components/Row";
import { Shell } from "@/components/Shell";
import { auth } from "@/lib/auth";
import { useSeverityLabels } from "@/lib/meta";
import { homeSearch } from "@/lib/search";
import { since } from "@/lib/duration";

export const Route = createFileRoute("/")({
  validateSearch: homeSearch,
  component: Home,
});

function Home() {
  const { tab, severity } = Route.useSearch();
  const signedIn = useSyncExternalStore(
    auth.subscribe,
    () => auth.tokens() !== null,
    () => false,
  );
  const labels = useSeverityLabels();
  const me = useMeRetrieve({ query: { enabled: signedIn } });
  const board = me.data?.default_dashboard_id;

  // Signed in it is your board. Signed out it is one row per
  // service, which is the same row narrowed to the rollups.
  const mine = useBoardComponentsList(
    board ?? "",
    { status__severity: severity },
    { query: { enabled: Boolean(board) } },
  );
  const catalog = useCatalogComponentsList(
    { is_overall: true, status__severity: severity },
    { query: { enabled: !signedIn } },
  );

  const list = signedIn ? mine : catalog;

  if (list.isError) return <Unreachable onRetry={() => list.refetch()} />;

  const rows = list.data?.results ?? [];
  const checked = list.data?.aggregates?.oldest_refreshed_at;

  return (
    <Shell title="Home" checkedAt={checked ? `${since(checked)} ago` : null}>
      {tab === "board" ? (
        <ul className="grid gap-2 md:grid-cols-[repeat(auto-fill,minmax(212px,1fr))]">
          {rows.map((component) => (
            <li key={component.id}>
              <Row
                component={component}
                label={labels[String(component.status?.severity)]}
                showMark
              />
            </li>
          ))}
        </ul>
      ) : (
        <p>Updates arrives with the next plan.</p>
      )}
    </Shell>
  );
}

function Unreachable({ onRetry }: { onRetry: () => void }) {
  return (
    <Shell title="Home">
      <p>Can't reach statusboard.</p>
      <button type="button" onClick={onRetry} className="mt-3 underline">
        Retry
      </button>
    </Shell>
  );
}
```

The generated hook names come from `operationId` in the contract. Read the real names out
of `src/api/statusboard.ts` after Task 3 and correct them here.

There is no stale cache and no offline banner. A failed request says so plainly.

- [ ] **Step 5: Run the tests**

Run: `pnpm --dir app test && pnpm --dir app typecheck`
Expected: PASS.

- [ ] **Step 6: Read a real board back**

Run `just dev`, then `just seed-live` in another terminal to fill the catalog.

Open the client URL signed out. Expected: a list of services, each with a state word in
its colour and a duration beside it. An operational row carries no tint.

This is the first screen that reads the live API. A shape the tests mocked wrong shows up
here and nowhere earlier.

- [ ] **Step 7: Commit**

```bash
git add app
git commit -m "feat: Home shows your board, or the catalog

Signed in it is your board. Signed out it is one row per service,
which is the same list narrowed to the rollups. The severity word
comes from /meta/, so a label change needs no client release."
```

---

## Task 9: Signing in, end to end

**Files:**
- Modify: `app/src/routes/signin.tsx`, `app/src/routes/verify.tsx`
- Modify: `api/.env.local`
- Test: `app/src/routes/verify.test.tsx`

**Interfaces:**
- Consumes: the generated `useAuthMagicLinkCreate` and `useAuthVerifyCreate`, `auth.signIn`
- Produces: a session, so Home has a board to show

The backend builds `{APP_URL}{APP_MAGIC_LINK_PATH}?token=…`, so `/verify` is not ours to
name. `MagicLinkToken` is single use.

- [ ] **Step 1: Point the API at the client**

In `api/.env.local`, fill the two values `just info` prints:

```
APP_URL=http://<slug>.localhost:<client port>
APP_MAGIC_LINK_PATH=/verify
```

Without `APP_URL` the API refuses to send a link rather than mailing an address nothing
serves. That refusal is deliberate, and this is the change that clears it.

- [ ] **Step 2: Write the failing test**

`app/src/routes/verify.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { auth } from "@/lib/auth";

let verifyCalls = 0;
const server = setupServer(
  http.post("*/auth/verify/", async () => {
    verifyCalls += 1;
    return HttpResponse.json({ access: "a", refresh: "r" });
  }),
);
beforeAll(() => server.listen());
beforeEach(() => {
  verifyCalls = 0;
  auth.signOut();
});
afterAll(() => server.close());

test("the token is spent exactly once", async () => {
  // MagicLinkToken stamps used_at on the first success. StrictMode
  // invokes an effect twice in development, so a second post would
  // tell somebody who just signed in that their link is dead.
  render(<VerifyRoute token="t" />, { wrapper: appWrapper });
  await waitFor(() => expect(auth.tokens()).not.toBeNull());
  expect(verifyCalls).toBe(1);
});

test("a spent token says so rather than hanging", async () => {
  server.use(
    http.post("*/auth/verify/", () =>
      HttpResponse.json({ code: "invalid_or_expired_token" }, { status: 400 }),
    ),
  );
  render(<VerifyRoute token="t" />, { wrapper: appWrapper });
  await waitFor(() =>
    expect(screen.getByText(/no longer valid/i)).toBeInTheDocument(),
  );
});

test("a page load with no token posts nothing", async () => {
  // An email client prefetches links. The page load must spend
  // nothing, or a prefetch signs the reader in and burns the token.
  render(<VerifyRoute token="" />, { wrapper: appWrapper });
  await new Promise((resolve) => setTimeout(resolve, 50));
  expect(verifyCalls).toBe(0);
});
```

- [ ] **Step 3: Run them to make sure they fail**

Run: `pnpm --dir app test verify`
Expected: FAIL. The route renders a stub.

- [ ] **Step 4: Write sign in**

`app/src/routes/signin.tsx`:

```tsx
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useAuthMagicLinkCreate } from "@/api/statusboard";
import { Shell } from "@/components/Shell";

export const Route = createFileRoute("/signin")({ component: SignIn });

function SignIn() {
  const [email, setEmail] = useState("");
  const request = useAuthMagicLinkCreate();

  // Always 202, even for an unknown address. So there is one screen
  // after this, and it does not say whether the account exists.
  if (request.isSuccess) {
    return (
      <Shell title="Check your email">
        <p>If that address has an account, a sign-in link is on its way.</p>
      </Shell>
    );
  }

  return (
    <Shell title="Sign in">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          request.mutate({ data: { email } });
        }}
        className="grid max-w-sm gap-3"
      >
        <label htmlFor="email">Keep track of what matters</label>
        <input
          id="email"
          type="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@example.com"
          className="rounded-xl border border-app-edge bg-app-card px-3 py-2"
        />
        <button
          type="submit"
          disabled={request.isPending}
          className="rounded-full bg-app-nav px-4 py-2 text-app-nav-ink"
        >
          Email me a sign-in link
        </button>
        <p className="text-xs text-app-ink-3">
          No password. We'll bring you back to where you were.
        </p>
      </form>
    </Shell>
  );
}
```

- [ ] **Step 5: Write verify**

`app/src/routes/verify.tsx`:

```tsx
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useRef } from "react";
import { useAuthVerifyCreate } from "@/api/statusboard";
import { Shell } from "@/components/Shell";
import { auth } from "@/lib/auth";

export const Route = createFileRoute("/verify")({
  validateSearch: (raw: Record<string, unknown>) => ({
    token: String(raw.token ?? ""),
  }),
  component: Verify,
});

function Verify() {
  const { token } = Route.useSearch();
  const navigate = useNavigate();
  const spent = useRef(false);
  const verify = useAuthVerifyCreate({
    mutation: {
      // A link is single use. A retry would spend a token the first
      // attempt already consumed.
      retry: false,
      onSuccess: (pair) => {
        auth.signIn(pair);
        navigate({ to: "/" });
      },
    },
  });

  useEffect(() => {
    // The guard, not the dependency array, is what makes this run
    // once. StrictMode invokes an effect twice in development.
    if (!token || spent.current) return;
    spent.current = true;
    verify.mutate({ data: { token } });
  }, [token, verify.mutate]);

  if (!token) {
    return (
      <Shell title="Sign in">
        <p>That link is missing its token.</p>
      </Shell>
    );
  }
  if (verify.isError) {
    return (
      <Shell title="Sign in">
        <p>That link is no longer valid. Ask for another.</p>
      </Shell>
    );
  }
  return (
    <Shell title="Signing you in">
      <p>One moment.</p>
    </Shell>
  );
}
```

The page load itself spends nothing, which is what makes an email client's prefetch safe.
Only the post burns the token.

- [ ] **Step 6: Run the tests**

Run: `pnpm --dir app test && pnpm --dir app typecheck`
Expected: PASS.

- [ ] **Step 7: Sign in for real**

Run `just dev`. With `EMAIL_USE_CONSOLE=1` the link prints to the terminal:

```
EMAIL_USE_CONSOLE=1 just dev
```

Ask for a link on `/signin`, copy the URL out of the log, open it. Expected: it lands on
`/verify`, then on Home, and Home now shows your board rather than the catalog. Open the
same link a second time and expect "no longer valid".

That second open is the whole point of the guard. Check it by hand.

- [ ] **Step 8: Commit**

```bash
git add app api/.env.local.example
git commit -m "feat: a magic link signs you in

The API builds the link from APP_URL, so /verify is not ours to name.
The token is single use, so the page posts it exactly once: an effect
guard rather than a dependency array, because StrictMode invokes the
effect twice."
```

---

## Task 10: The image, and the pipeline that ships it

**Files:**
- Create: `app/Dockerfile`, `app/nginx.conf`, `app/entrypoint.sh`, `app/.dockerignore`
- Modify: `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `justfile`
- Modify: `deploy-pipeline/app-statusboard/compose.yml`, `.env.example`

**Interfaces:**
- Consumes: `pnpm build`
- Produces: `ghcr.io/thalida/statusboard-app`, and `just deploy` shipping it

One image per component, built from that component's own directory. One image, any
environment: the entrypoint writes the configuration at start.

- [ ] **Step 1: Write the image**

`app/Dockerfile`:

```dockerfile
FROM node:22-alpine AS build
WORKDIR /srv/app
RUN corepack enable
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

FROM nginx:1.27-alpine AS runtime
# Rebuilt every image, so a cached layer cannot pin an apt state to
# the day it was first built. The API's Dockerfile does the same.
RUN apk upgrade --no-cache
COPY --from=build /srv/app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD wget -qO- http://localhost:8080/ >/dev/null || exit 1
ENTRYPOINT ["/entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
```

`app/entrypoint.sh`:

```sh
#!/bin/sh
# What the page reads at start, written from the environment.
#
# A Vite build inlines a VITE_ value, which would make this image
# environment-specific. The same image then could not be the one CI
# proved. api/entrypoint.sh picks a process the same way.
set -eu

: "${API_URL:?API_URL is unset, so the client would call nothing}"

cat > /usr/share/nginx/html/config.js <<EOF
window.STATUSBOARD_CONFIG = { apiUrl: "${API_URL}" };
EOF

exec "$@"
```

`app/nginx.conf`:

```nginx
server {
    listen 8080;
    root /usr/share/nginx/html;

    # A CSP is what makes a refresh token in local storage acceptable.
    # connect-src names the API's own origin, which the entrypoint
    # also wrote into config.js.
    add_header Content-Security-Policy "default-src 'self'; connect-src 'self' ${API_URL}; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'; base-uri 'self'" always;
    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;

    # The build fingerprints its assets, so they never change under a
    # name. index.html and config.js must not be cached: one carries
    # the asset names and the other the deployment's own values.
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    location = /config.js {
        add_header Cache-Control "no-store";
    }
    location = /index.html {
        add_header Cache-Control "no-store";
    }

    # A single page. Every unknown path is the app's own route.
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

nginx does not expand `${API_URL}` in a config file. Use the image's own templating: put
the file at `/etc/nginx/templates/default.conf.template` instead, which the official image
renders with `envsubst` at start. Move the `COPY` accordingly and drop the header's
variable if the template proves awkward.

`app/.dockerignore`:

```
node_modules
dist
.env*
```

- [ ] **Step 2: Prove the image serves the page and the config**

Run:
```bash
docker build -t statusboard-app:test app
docker run -d --name app-smoke -p 18080:8080 -e API_URL=https://api.example.test statusboard-app:test
sleep 2
curl -sf http://localhost:18080/ | head -1
curl -sf http://localhost:18080/config.js
curl -sf -o /dev/null -w '%{http_code}\n' http://localhost:18080/services/twilio
docker rm -f app-smoke
```

Expected: the HTML, then `window.STATUSBOARD_CONFIG = { apiUrl: "https://api.example.test" };`,
then `200` for the deep link. The third proves the SPA fallback.

- [ ] **Step 3: Add the client to `just check`**

The two `cd app` lines from Task 3 are already there. Add the image build so the gate
proves what ships:

```make
# Build both deployment images. `check` runs against them.
[group('Lifecycle')]
image:
    docker build -t statusboard-api:test api
    docker build -t statusboard-app:test app
```

- [ ] **Step 4: Add the CI job**

In `.github/workflows/ci.yml`, after the API steps:

```yaml
      - name: Build the client image
        uses: docker/build-push-action@v7
        with:
          context: ./app
          load: true
          tags: statusboard-app:ci
          cache-from: type=gha
          cache-to: type=gha,mode=max
          no-cache-filters: runtime
          pull: true

      - name: Set up pnpm
        uses: pnpm/action-setup@v4
        with:
          version: 10

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
          cache-dependency-path: app/pnpm-lock.yaml

      - name: Client dependencies
        run: pnpm --dir app install --frozen-lockfile

      - name: Client lint, types and tests
        run: pnpm --dir app lint:ci && pnpm --dir app typecheck && pnpm --dir app test

      - name: The generated client matches the contract
        run: pnpm --dir app codegen && git diff --exit-code app/src/api
```

Add `statusboard-app:ci` to the Trivy step, or add a second Trivy step for it. An unscanned
image is the half of the deployment nobody is watching.

- [ ] **Step 5: Hold the merge gate together**

Run: `python3 -m unittest discover -s bin/tests`

Expected: PASS. Task 3 left this failing on purpose, and the CI job above is what clears
it. If it still fails, the wording of a `just check` line and its CI counterpart differ,
and the test names which.

- [ ] **Step 6: Release the image beside the API**

In `.github/workflows/release.yml`, add an `app` job mirroring `api`: the same tag set with
`statusboard-app` in place of `statusboard-api`, the same cosign signing, and
`context: ./app`. Its smoke test is Step 2's `curl`, not a database.

Change the deploy job to `needs: [api, app]`. The image has to exist before the deploy
pulls it, and now there are two.

- [ ] **Step 7: Ship it on every green main**

A new job in `ci.yml`, so a deploy during development needs no version bump:

```yaml
  edge:
    name: Publish the edge images
    needs: [build-and-test]
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    permissions:
      packages: write
    steps:
      - uses: actions/checkout@v6
      - uses: docker/setup-buildx-action@v4
      - uses: docker/login-action@v4
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Push edge
        run: |
          for part in api app; do
            docker buildx build --push "./$part" \
              -t "ghcr.io/${{ github.repository_owner }}/statusboard-$part:edge" \
              -t "ghcr.io/${{ github.repository_owner }}/statusboard-$part:sha-${{ github.sha }}"
          done
```

`needs: [build-and-test]` is what stops a red main becoming a deployable image.

- [ ] **Step 8: Add the client to the stack**

In `deploy-pipeline/app-statusboard/compose.yml`, replace the placeholder comment with a
service, and make every image tag a variable:

```yaml
  app:
    image: ghcr.io/thalida/statusboard-app:${APP_TAG:-latest}
    restart: unless-stopped
    init: true
    environment:
      API_URL: https://api.statusboard.dev
    networks:
      - default
      - traefik
    labels:
      traefik.enable: 'true'
      traefik.docker.network: traefik
      traefik.http.routers.app-statusboard-app.rule: 'Host(`statusboard.dev`)'
      traefik.http.services.app-statusboard-app.loadbalancer.server.port: '8080'
```

Change the four API services to `${API_TAG:-latest}`, and add both names to
`.env.example`:

```
# Which image each half runs. Leave unset for the tagged release.
# Set to `edge` to follow main while developing, and `just deploy`
# then ships whatever main last built.
# API_TAG=
# APP_TAG=
```

`app` joins no link to the API. The browser calls it, not this network.

- [ ] **Step 9: Deploy without a version bump**

On the server, set `APP_TAG=edge` and `API_TAG=edge` in the stack's `.env`, then:

```bash
just deploy
```

Expected: the Forgejo run pulls the images main last built and recreates the stack. Unset
both to return to tag-gated releases.

- [ ] **Step 10: Commit**

```bash
git add app justfile .github
git commit -m "feat: the client ships as its own image

One image per component, built from its own directory. The entrypoint
writes config.js from the environment, so one image answers anywhere
and it is the image CI proved. A green main publishes :edge, so a
deploy during development needs no version bump."
```

---

## Self-Review Notes

**Spec coverage.** Sections 3, 4, 10, 11 and 12 of the client design map to tasks here.
Sections 1, 5, 6, 7, 8 and 9 were Plan A and are shipped.

| Spec section | Task |
| --- | --- |
| 3, Stack | 1 |
| 3, Tokens | 2 |
| 3, Orval | 3 |
| 3, Auth | 4, 9 |
| 4, Routes and search parameters | 5 |
| 4, A row's destination is a rule | 7 |
| 4, Screen to endpoint | 8, 9, and the following plan |
| 10, Build and test | 1, 3, 10 |
| 10, Runtime configuration | 10 |
| 11, Deploy | 10 |
| 12, Local development | 1, 9 |

**Left to the following plan:** Discover, Add by URL, the Service, Component and Event
screens, Settings, and the PWA. Home's Updates tab renders a placeholder until then.

**Names used across tasks.** `auth` and `fetcher` are defined in Task 4 and read in 8 and 9.
`severityTone` and `since` are defined in Task 7 and read in 7 and 8. `Shell` is defined in
Task 6 and read in 8 and 9. `homeSearch` and its siblings are defined in Task 5 and read in
5, 8 and the following plan. `routerWrapper` and `appWrapper` are defined in Tasks 6 and 8.

**What needs verifying on contact.** These were written from reading, not running:

1. **Orval's generated hook names** come from the contract's `operationId`. Task 8 and Task 9
   guess them. Read `src/api/statusboard.ts` and correct.
2. **Tailwind v4's `@theme inline`** and the class names it emits. Task 2's test only checks
   the token file, so a name that does not resolve shows on screen rather than in a test.
3. **nginx's `${API_URL}`** in a config file needs the image's template directory. Task 10
   says so, and Step 2's `curl` is what catches it.
4. **TanStack Router's `validateSearch`** signature and whether a falling-back schema behaves
   as Task 5 expects. Step 8 of that task checks it in a browser for that reason.

**The one design gap.** The decks render the app in light only, so Task 2's dark values are
derived rather than approved. Read them on a real screen before the theme control ships in
the following plan.
