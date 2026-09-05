import { render, screen } from "@testing-library/react";
import { App } from "./App";

test("the app renders its name", () => {
  // The whole harness in one assertion: Vite, TypeScript, React and
  // the test environment. A failure here is the build, not a feature.
  render(<App />);
  expect(screen.getByText("Statusboard")).toBeInTheDocument();
});
