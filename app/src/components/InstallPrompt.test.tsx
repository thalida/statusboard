import { fireEvent, render, screen } from "@testing-library/react";
import { InstallPrompt } from "./InstallPrompt";

beforeEach(() => localStorage.clear());

test("the prompt appears after three visits when the browser can install", async () => {
  // The visit count keeps the install prompt from greeting a first-time reader.
  for (let visit = 0; visit < 3; visit += 1) {
    const view = render(<InstallPrompt />);
    view.unmount();
  }
  render(<InstallPrompt />);
  fireEvent(window, new Event("beforeinstallprompt", { cancelable: true }));
  expect(
    await screen.findByRole("complementary", { name: "Install Statusboard" }),
  ).toBeInTheDocument();
});

test("dismissal persists across visits", async () => {
  localStorage.setItem("statusboard.visits", "3");
  render(<InstallPrompt />);
  fireEvent(window, new Event("beforeinstallprompt", { cancelable: true }));
  fireEvent.click(await screen.findByRole("button", { name: "Dismiss" }));
  expect(localStorage.getItem("statusboard.install-dismissed")).toBe("true");
});
