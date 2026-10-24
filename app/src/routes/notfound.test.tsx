import { screen } from "@testing-library/react";
import { renderRoute } from "@/test-utils";

// `/services` and `/components` name no page: every screen under them
// needs an id. TanStack's own fallback is the words "Not Found" with
// no header and no nav, which strands the reader.

test.each([
  ["a parent path that names no page", "/services"],
  ["a parent path with an id missing", "/components"],
  ["a typo", "/nonsense"],
  ["a dead tab", "/services/twilio/timeline"],
])("%s is a screen with a way out", async (_case, path) => {
  renderRoute(path);
  expect(await screen.findByText(/doesn't exist/i)).toBeInTheDocument();
  expect(screen.getByRole("navigation", { name: "" })).toBeInTheDocument();
});
