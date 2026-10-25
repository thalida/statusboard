import { render, screen } from "@testing-library/react";
import { LoadState } from "./LoadState";

test("an empty response shows its supplied empty state", () => {
  // A valid empty list differs from a failed request.
  render(<LoadState loading={false} error={false} empty="Nothing here yet." />);
  expect(screen.getByText("Nothing here yet.")).toBeInTheDocument();
});

test("a failed request offers a retry", () => {
  // Readers need a way back after a transient API failure.
  render(<LoadState loading={false} error onRetry={() => {}} />);
  expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
});
