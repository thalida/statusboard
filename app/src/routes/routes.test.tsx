import { screen } from "@testing-library/react";
import { renderRoute } from "@/test-utils";

// The service screen is still a stub that renders its tab name, so
// these read the routing itself and reach no API. Home's own tabs
// are covered in index.test.tsx, where it has data to render.

async function tabAt(path: string) {
  renderRoute(path);
  return screen.findByRole("main");
}

test("a bare path renders the default tab", async () => {
  // Components is what a service screen means. A required tab would
  // break every link written by hand.
  expect(await tabAt("/services/twilio")).toHaveTextContent("components");
});

test("a named tab renders that tab", async () => {
  // The URL is the whole of the screen's state, so a reload
  // restores the tab the reader chose.
  expect(await tabAt("/services/twilio?tab=about")).toHaveTextContent("about");
});

test("an unknown tab renders the default, not an error", async () => {
  // A schema that threw would show the router's error page here.
  // This is the case the fallback exists for.
  expect(await tabAt("/services/twilio?tab=nonsense")).toHaveTextContent(
    "components",
  );
});

test("each screen validates only its own tabs", async () => {
  // `timeline` belongs to the event screen. A service has no such
  // tab, so the link cannot select one another screen owns.
  expect(await tabAt("/services/twilio?tab=timeline")).toHaveTextContent(
    "components",
  );
});
