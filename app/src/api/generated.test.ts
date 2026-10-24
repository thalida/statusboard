// jsdom's global URL resolves "." against a fake location, not the
// file this module lives in. readdirSync then gets a non-file URL.
// @vitest-environment node
import { readdirSync } from "node:fs";
import type { Component } from "./model";

test("the contract's operations are generated", () => {
  // A missing hook means somebody hand-wrote a fetch, which is a
  // second definition of a shape the API already publishes.
  const files = readdirSync(new URL(".", import.meta.url));
  expect(files).toContain("statusboard.ts");
  expect(files).toContain("statusboard.msw.ts");
});

test("the component model carries the fields the row reads", () => {
  // If a field is renamed in the API, tsc fails here, not a screen.
  const row: Pick<
    Component,
    "id" | "name" | "is_overall" | "descendant_count"
  > = {
    id: "x",
    name: "SMS",
    is_overall: false,
    descendant_count: 0,
  };
  expect(row.name).toBe("SMS");
});
