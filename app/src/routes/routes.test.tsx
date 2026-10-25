import { screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, beforeEach } from "vitest";
import { getStatusboardAPIMock } from "@/api/statusboard.msw";
import { renderRoute } from "@/test-utils";

const server = setupServer(...getStatusboardAPIMock());
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

beforeEach(() => {
  server.use(
    http.get("*/catalog/services/twilio/", () =>
      HttpResponse.json({
        slug: "twilio",
        name: "Twilio",
        component_count: 1,
        overall_component: { id: "overall", name: "Twilio", is_overall: true },
      }),
    ),
    http.get("*/catalog/components/", () =>
      HttpResponse.json({ next: null, aggregates: { total: 0 }, results: [] }),
    ),
    http.get("*/events/", () =>
      HttpResponse.json({ next: null, aggregates: { total: 0 }, results: [] }),
    ),
  );
});

test("a bare service path shows its first tab", async () => {
  // The service list is the default tab, so a shared bare link stays useful.
  renderRoute("/services/twilio");
  expect(
    await screen.findByRole("heading", { name: "Twilio" }),
  ).toBeInTheDocument();
  expect(screen.getByText("No components found.")).toBeInTheDocument();
});

test("a tab is its own path", async () => {
  renderRoute("/services/twilio/about");
  expect(
    await screen.findByRole("heading", { name: "Twilio" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("navigation", { name: "Tabs" })).toBeInTheDocument();
});

test("the service About tab reads provider metadata", async () => {
  // Readers need the provider URL when they want the original status page.
  server.use(
    http.get("*/catalog/services/twilio/", () =>
      HttpResponse.json({
        slug: "twilio",
        name: "Twilio",
        status_page: {
          url: "https://status.twilio.com",
          provider: "statuspage",
        },
      }),
    ),
  );
  renderRoute("/services/twilio/about");
  expect(
    await screen.findByRole("link", { name: "https://status.twilio.com" }),
  ).toHaveAttribute("href", "https://status.twilio.com");
});

test("a component page links through its served breadcrumb", async () => {
  // Breadcrumbs must use served ancestry when archived parents are missing.
  server.use(
    http.get("*/catalog/components/c1/", () =>
      HttpResponse.json({
        id: "c1",
        name: "Database",
        service: { slug: "twilio", name: "Twilio" },
        path: [{ id: "root", name: "Data" }],
        status: { severity: 2 },
      }),
    ),
    http.get("*/events/", () =>
      HttpResponse.json({ next: null, aggregates: { total: 0 }, results: [] }),
    ),
  );
  renderRoute("/components/c1");
  expect(await screen.findByRole("link", { name: "Twilio" })).toHaveAttribute(
    "href",
    "/services/twilio",
  );
  expect(screen.getByText("Data")).toBeInTheDocument();
});

test("a tab one screen owns is not a path on another", async () => {
  // `timeline` belongs to the event screen. On a service it is no
  // route at all, so the router says so rather than guessing.
  renderRoute("/services/twilio/timeline");
  expect(await screen.findByText(/not found/i)).toBeInTheDocument();
});

test("the tabs are links, so a tab can be opened in a new window", async () => {
  renderRoute("/services/twilio");
  const tabs = await screen.findByRole("navigation", { name: "Tabs" });
  expect(tabs.querySelectorAll("a")).toHaveLength(3);
});
