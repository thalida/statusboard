import { render, screen } from "@testing-library/react";
import { routerWrapper } from "@/test-utils";
import { Shell } from "./Shell";

test("the destinations sit in the header, not after the content", async () => {
  // On a desktop the nav is static, so its place in the document is
  // its place on screen. Rendered after <main> it reads as a footer.
  render(
    <Shell title="Home">
      <p>rows</p>
    </Shell>,
    { wrapper: routerWrapper },
  );
  const nav = await screen.findByRole("navigation");
  expect(screen.getByRole("banner")).toContainElement(nav);
});

test("the stamp only appears when there is one", async () => {
  // A header that always held the row would show "Checked" with
  // nothing after it before the first response lands.
  render(
    <Shell title="Home">
      <p>rows</p>
    </Shell>,
    { wrapper: routerWrapper },
  );
  await screen.findByRole("navigation");
  expect(screen.queryByText(/Checked/)).toBeNull();
});
