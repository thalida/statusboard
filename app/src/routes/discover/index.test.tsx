import { screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll } from "vitest";
import { getStatusboardAPIMock } from "@/api/statusboard.msw";
import { suggestedServices } from "@/lib/preferences";
import { renderRoute } from "@/test-utils";

const server = setupServer(...getStatusboardAPIMock());
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

test("Discover sends its search and renders the matching component", async () => {
  // A search must reach the API or shared links show unrelated rows.
  let requested = "";
  server.use(
    http.get("*/meta/", () =>
      HttpResponse.json({ enums: { severity: { "5": "Operational" } } }),
    ),
    http.get("*/catalog/components/", ({ request }) => {
      requested = new URL(request.url).searchParams.get("q") ?? "";
      return HttpResponse.json({
        next: null,
        aggregates: { total: 1 },
        results: [
          {
            id: "c1",
            name: "SMS",
            is_overall: false,
            service: { slug: "twilio", name: "Twilio" },
            status: { severity: 5 },
          },
        ],
      });
    }),
  );
  renderRoute("/discover?q=twilio");
  expect(await screen.findByRole("link", { name: /SMS/ })).toHaveAttribute(
    "href",
    "/components/c1",
  );
  expect(requested).toBe("twilio");
});

test("turning suggestions off leaves search available without loading recommendations", async () => {
  // A saved preference must suppress recommendations without disabling search.
  let requests = 0;
  suggestedServices.write(false);
  server.use(
    http.get("*/meta/", () => HttpResponse.json({ enums: { severity: {} } })),
    http.get("*/catalog/components/", () => {
      requests += 1;
      return HttpResponse.json({
        next: null,
        aggregates: { total: 0 },
        results: [],
      });
    }),
  );
  renderRoute("/discover");
  expect(
    await screen.findByText(/search for a service or component/i),
  ).toBeInTheDocument();
  expect(requests).toBe(0);
});
