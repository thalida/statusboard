import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll } from "vitest";
import { getStatusboardAPIMock } from "@/api/statusboard.msw";
import { renderRoute } from "@/test-utils";

const server = setupServer(...getStatusboardAPIMock());
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

test("an unknown URL gets a neutral request confirmation", async () => {
  // The confirmation must not reveal whether the catalog already holds the URL.
  const user = userEvent.setup();
  let requestedUrl = "";
  server.use(
    http.post(
      "*/catalog/import/",
      () => new HttpResponse(null, { status: 404 }),
    ),
    http.post("*/catalog/requests/", async ({ request }) => {
      requestedUrl = ((await request.json()) as { url: string }).url;
      return new HttpResponse(null, { status: 202 });
    }),
  );
  renderRoute("/discover/add");
  await user.type(
    await screen.findByLabelText("Status page URL"),
    "https://example.test/status",
  );
  await user.click(screen.getByRole("button", { name: "Add status page" }));
  expect(
    await screen.findByText(/thanks\. we’ll review that status page/i),
  ).toBeInTheDocument();
  expect(requestedUrl).toBe("https://example.test/status");
});
