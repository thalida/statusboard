import { screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll } from "vitest";
import { getStatusboardAPIMock } from "@/api/statusboard.msw";
import { renderRoute } from "@/test-utils";

const server = setupServer(...getStatusboardAPIMock());
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

test("the timeline shows updates in the API's oldest-first order", async () => {
  // Reversing this order would change the event's recorded history.
  server.use(
    http.get("*/events/e1/", () =>
      HttpResponse.json({
        id: "e1",
        title: "Database unavailable",
        kind: "incident",
        phase: "detected",
        service: { slug: "twilio", name: "Twilio" },
      }),
    ),
    http.get("*/events/e1/updates/", () =>
      HttpResponse.json({
        next: null,
        results: [
          { posted_at: "2026-10-24T10:00:00Z", body: "The database failed." },
          { posted_at: "2026-10-24T10:05:00Z", body: "Recovery started." },
        ],
      }),
    ),
  );
  renderRoute("/events/e1");
  const first = await screen.findByText("The database failed.");
  const second = screen.getByText("Recovery started.");
  expect(
    first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
});

test("Affects shows zero when the event has no served components", async () => {
  // An empty relation is still a real tab with a stable zero count.
  server.use(
    http.get("*/events/e1/", () =>
      HttpResponse.json({
        id: "e1",
        title: "Short interruption",
        kind: "incident",
        phase: "resolved",
        affected_count: 0,
      }),
    ),
    http.get("*/catalog/components/", () =>
      HttpResponse.json({ next: null, aggregates: { total: 0 }, results: [] }),
    ),
  );
  renderRoute("/events/e1/affects");
  expect(
    await screen.findByRole("link", { name: "Affects 0" }),
  ).toBeInTheDocument();
  expect(screen.getByText("No components were affected.")).toBeInTheDocument();
});
