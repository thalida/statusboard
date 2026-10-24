import { render, screen } from "@testing-library/react";
import { auth } from "@/lib/auth";
import { routerWrapper } from "@/test-utils";
import { Nav } from "./Nav";

beforeEach(() => auth.signOut());

// Every query here is async. A router renders its tree after it
// loads, so a synchronous query sees an empty document.

test("the third slot is Sign in when signed out", async () => {
  // Signed out and signed in are the same screens. Only this slot
  // and a row's glyph change.
  render(<Nav />, { wrapper: routerWrapper });
  expect(await screen.findByText("Sign in")).toBeInTheDocument();
  expect(screen.queryByText("Settings")).not.toBeInTheDocument();
});

test("the third slot is Settings when signed in", async () => {
  auth.signIn({ access: "a", refresh: "r" });
  render(<Nav />, { wrapper: routerWrapper });
  expect(await screen.findByText("Settings")).toBeInTheDocument();
});

test("every destination is a link, not a button", async () => {
  // A tab must open in a new window and be copied as a URL. A
  // button does neither.
  render(<Nav />, { wrapper: routerWrapper });
  expect(await screen.findAllByRole("link")).toHaveLength(3);
});
