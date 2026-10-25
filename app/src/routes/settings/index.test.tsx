import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, beforeEach } from "vitest";
import { getStatusboardAPIMock } from "@/api/statusboard.msw";
import { auth } from "@/lib/auth";
import { renderRoute } from "@/test-utils";

let deleteCalls = 0;
const server = setupServer(...getStatusboardAPIMock());
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
beforeEach(() => {
  deleteCalls = 0;
  auth.signOut();
  server.use(
    http.get("*/me/", () =>
      HttpResponse.json({
        email: "reader@example.test",
        default_dashboard_id: "d1",
      }),
    ),
    http.delete("*/me/", () => {
      deleteCalls += 1;
      return new HttpResponse(null, { status: 204 });
    }),
    http.post("*/auth/logout/", () => HttpResponse.json({})),
  );
});
afterEach(() => {
  server.resetHandlers();
  localStorage.clear();
});
afterAll(() => server.close());

test("Suggested services toggle persists for Discover", async () => {
  // The Discover preference must survive when the reader changes screens.
  auth.signIn({ access: "a", refresh: "r" });
  renderRoute("/settings");
  const user = userEvent.setup();
  const toggle = await screen.findByRole("checkbox", {
    name: "Show suggestions in Discover",
  });
  expect(toggle).toBeChecked();
  await user.click(toggle);
  expect(localStorage.getItem("statusboard.suggested-services")).toBe("false");
});

test("account deletion requires a second action and clears the session", async () => {
  // An accidental click must not delete the account or leave a stale session.
  auth.signIn({ access: "a", refresh: "r" });
  renderRoute("/settings");
  const user = userEvent.setup();
  await user.click(
    await screen.findByRole("button", { name: "Delete account" }),
  );
  expect(deleteCalls).toBe(0);
  await user.click(screen.getByRole("button", { name: "Confirm deletion" }));
  await screen.findByRole("heading", { name: "Home" });
  expect(deleteCalls).toBe(1);
  expect(auth.tokens()).toBeNull();
});
