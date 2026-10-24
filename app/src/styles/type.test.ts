// @vitest-environment node
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("./app.css", import.meta.url), "utf8");
const html = readFileSync(new URL("../../index.html", import.meta.url), "utf8");

test("the app sets its own faces", () => {
  // Without a family the app renders in the browser default, which
  // is not a face either deck chose. It looks almost right.
  expect(css).toMatch(/--font-sans:\s*"Outfit"/);
  expect(css).toMatch(/--font-mono:\s*"DM Mono"/);
  expect(css).toMatch(/body\s*{[^}]*font-family:\s*var\(--font-sans\)/);
});

test("both faces are actually fetched", () => {
  // A family named in CSS and absent from the page is a silent
  // fallback to the default.
  expect(html).toContain("family=Outfit");
  expect(html).toContain("family=DM+Mono");
});
