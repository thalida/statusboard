import { screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll } from "vitest";
import { getStatusboardAPIMock } from "@/api/statusboard.msw";
import { auth } from "@/lib/auth";
import { errorHandlerFor, renderRoute } from "@/test-utils";

const server = setupServer(...getStatusboardAPIMock());
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  auth.signOut();
});
afterAll(() => server.close());

/** One service rollup, and the word for its severity. */
function board(label: string, severity: number) {
  return [
    http.get("*/meta/", () =>
      HttpResponse.json({ enums: { severity: { [String(severity)]: label } } }),
    ),
    http.get("*/catalog/components/", () =>
      HttpResponse.json({
        next: null,
        aggregates: { total: 1, oldest_refreshed_at: new Date().toISOString() },
        results: [
          {
            id: "c1",
            name: "SMS",
            is_overall: true,
            service: { id: "s1", slug: "twilio", name: "Twilio" },
            status: { severity, started_at: new Date().toISOString() },
          },
        ],
      }),
    ),
  ];
}

test("signed out, Home lists one row per service", async () => {
  // A board is one row per service when nothing is yours. Narrowing
  // to overall components is what makes signed out and signed in the
  // same screen. The row's own link is the assertion: the nav holds
  // three links of its own, so a count would pass without any row.
  server.use(...board("Operational", 5));
  renderRoute("/");
  const row = await screen.findByRole("link", { name: /SMS/ });
  expect(row).toHaveAttribute("href", "/services/twilio");
});

test("the severity word comes from /meta/, not from the client", async () => {
  // The labels have one home. A new value must reach every screen
  // without a client release. No client could spell this one.
  server.use(...board("Thoroughly bemused", 2));
  renderRoute("/");
  expect(await screen.findByText(/Thoroughly bemused/)).toBeInTheDocument();
});

test("the updates tab is its own path", async () => {
  // A tab is a place, so it is readable and shareable rather than a
  // parameter on the board.
  server.use(...board("Operational", 5));
  renderRoute("/updates");
  expect(await screen.findByText(/Updates arrives/)).toBeInTheDocument();
});

test("the board and the updates feed share one header", async () => {
  // A tabbed screen is one page: the header stays and the body
  // swaps. Both tabs therefore read "Home".
  server.use(...board("Operational", 5));
  renderRoute("/updates");
  expect(
    await screen.findByRole("heading", { name: "Home" }),
  ).toBeInTheDocument();
});

test("an unreachable API says so and offers a retry", async () => {
  // There is no offline mode and no stale cache. A failed request
  // shows a plain state rather than yesterday's answer.
  server.use(errorHandlerFor("/catalog/components/"));
  renderRoute("/");
  await waitFor(
    () =>
      expect(screen.getByText(/can't reach statusboard/i)).toBeInTheDocument(),
    { timeout: 3000 },
  );
  expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
});
