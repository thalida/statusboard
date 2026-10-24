import { screen } from "@testing-library/react";
import { renderRoute } from "@/test-utils";

// A tab is a path. The service screen is still a stub, so these read
// the routing itself and reach no API.

test("a bare screen path shows its first tab", async () => {
  // Components is what a service screen opens on. A bare path must
  // land somewhere rather than on an empty body.
  renderRoute("/services/twilio");
  expect(await screen.findByText(/Components arrives/)).toBeInTheDocument();
});

test("a tab is its own path", async () => {
  renderRoute("/services/twilio/about");
  expect(await screen.findByText(/About arrives/)).toBeInTheDocument();
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
