import {
  createMemoryHistory,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import { routeTree } from "../routeTree.gen";

async function at(path: string) {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [path] }),
  });
  render(<RouterProvider router={router} />);
  return screen.findByRole("main");
}

test("a bare path renders the default tab", async () => {
  // Home's board is what `/` means. A required tab would break
  // every link written by hand.
  expect(await at("/")).toHaveTextContent("board");
});

test("a named tab renders that tab", async () => {
  // The URL is the whole of the screen's state, so a reload
  // restores the tab the reader chose.
  expect(await at("/?tab=updates")).toHaveTextContent("updates");
});

test("an unknown tab renders the default, not an error", async () => {
  // A schema that threw would show the router's error page here.
  // This is the case the fallback exists for.
  expect(await at("/?tab=nonsense")).toHaveTextContent("board");
});

test("each screen validates only its own tabs", async () => {
  // `about` belongs to the service screen. Home has no such tab.
  expect(await at("/services/twilio?tab=about")).toHaveTextContent("about");
});
