import { screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, beforeEach } from "vitest";
import { getStatusboardAPIMock } from "@/api/statusboard.msw";
import { auth } from "@/lib/auth";
import { renderRoute } from "@/test-utils";

let verifyCalls = 0;

// The generated handlers answer everything Home asks for after the
// redirect. Only /auth/verify/ is counted here.
const server = setupServer(...getStatusboardAPIMock());
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
beforeEach(() => {
  verifyCalls = 0;
  auth.signOut();
  server.use(
    http.post("*/auth/verify/", () => {
      verifyCalls += 1;
      return HttpResponse.json({ access: "a", refresh: "r" });
    }),
  );
});
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

test("the token is spent exactly once", async () => {
  // MagicLinkToken stamps used_at on the first success. StrictMode
  // invokes an effect twice in development, so a second post would
  // tell somebody who just signed in that their link is dead.
  renderRoute("/verify?token=t");
  await waitFor(() => expect(auth.tokens()).not.toBeNull());
  expect(verifyCalls).toBe(1);
});

test("a spent token says so rather than hanging", async () => {
  server.use(
    http.post("*/auth/verify/", () =>
      HttpResponse.json({ code: "invalid_or_expired_token" }, { status: 400 }),
    ),
  );
  renderRoute("/verify?token=t");
  expect(await screen.findByText(/no longer valid/i)).toBeInTheDocument();
});

test("a page load with no token posts nothing", async () => {
  // An email client prefetches links. The page load must spend
  // nothing, or a prefetch signs the reader in and burns the token.
  renderRoute("/verify");
  expect(await screen.findByText(/missing its token/i)).toBeInTheDocument();
  expect(verifyCalls).toBe(0);
});
