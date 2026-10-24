import { since } from "./duration";

test("a duration is coarse, because a row is scanned", () => {
  // "38 min" and "2 hrs" are read at a glance. Seconds would move
  // on every render and say nothing.
  const now = new Date("2026-09-04T12:00:00Z");
  expect(since("2026-09-04T11:22:00Z", now)).toBe("38 min");
  expect(since("2026-09-04T10:00:00Z", now)).toBe("2 hrs");
  expect(since("2026-08-29T12:00:00Z", now)).toBe("6 days");
});

test("under a minute reads as just now", () => {
  // "0 min" reads as broken. A state that just changed has no
  // duration worth stating.
  const now = new Date("2026-09-04T12:00:00Z");
  expect(since("2026-09-04T11:59:40Z", now)).toBe("just now");
});
