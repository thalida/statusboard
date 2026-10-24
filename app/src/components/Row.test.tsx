import { render, screen } from "@testing-library/react";
import { afterAll, beforeAll, vi } from "vitest";
import type { Component } from "@/api/model";
import { routerWrapper } from "@/test-utils";
import { Row } from "./Row";

const component: Component = {
  id: "c1",
  name: "SMS",
  is_overall: false,
  descendant_count: 0,
  is_tracked: false,
  path: [{ id: "p1", name: "Programmable Messaging", is_overall: false }],
  service: { id: "s1", slug: "twilio", name: "Twilio", logo: "" },
  status: { severity: 2, started_at: "2026-09-04T10:00:00Z" },
};

// The severity word comes from `/meta/`, so every render here passes
// the label a caller would have read from it.

// A row reads the clock to say how long a state has held. Without a
// frozen one these durations grow by a day every day.
// `shouldAdvanceTime` keeps the timers running. An async query
// polls on a timer, and a frozen one never resolves.
beforeAll(() =>
  vi.useFakeTimers({
    now: new Date("2026-09-04T12:00:00Z"),
    shouldAdvanceTime: true,
  }),
);
afterAll(() => vi.useRealTimers());

test("a row is the name, then the state and how long it has held", async () => {
  // Two lines. A 232px phone row cannot hold two things that must
  // not truncate.
  render(<Row component={component} label="Degraded" />, {
    wrapper: routerWrapper,
  });
  expect(await screen.findByText("SMS")).toBeInTheDocument();
  expect(screen.getByText(/Degraded/)).toBeInTheDocument();
  expect(screen.getByText(/2 hrs/)).toBeInTheDocument();
});

test("the only third line is a parent", async () => {
  // Not a count, not "Overall status", not a tracking line. Those
  // said what kind of row it was rather than its condition.
  render(<Row component={component} label="Degraded" />, {
    wrapper: routerWrapper,
  });
  expect(await screen.findByText(/Programmable Messaging/)).toBeInTheDocument();
});

test("an overall component links to its service, not to itself", async () => {
  // A service's rollup is the service. Its own page would be the
  // same list with a different header.
  const rollup: Component = {
    ...component,
    is_overall: true,
    name: "Twilio",
    path: [],
  };
  render(<Row component={rollup} label="Degraded" />, {
    wrapper: routerWrapper,
  });
  expect(await screen.findByRole("link")).toHaveAttribute(
    "href",
    "/services/twilio",
  );
});

test("a component links to its own page", async () => {
  render(<Row component={component} label="Degraded" />, {
    wrapper: routerWrapper,
  });
  expect(await screen.findByRole("link")).toHaveAttribute(
    "href",
    "/components/c1",
  );
});

test("operational carries no tint", async () => {
  // A list is scanned for colour. Tinting the healthy rows makes
  // every row shout, so nothing does.
  const fine: Component = {
    ...component,
    status: { severity: 5, started_at: "2026-09-04T10:00:00Z" },
  };
  const { container } = render(<Row component={fine} label="Operational" />, {
    wrapper: routerWrapper,
  });
  await screen.findByText("SMS");
  expect(container.querySelector("[data-tone]")).toHaveAttribute(
    "data-tone",
    "ok",
  );
  expect(container.querySelector("[data-tinted='true']")).toBeNull();
});
