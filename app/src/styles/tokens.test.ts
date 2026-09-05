// @vitest-environment node
import { readFileSync } from "node:fs";

// jsdom's URL resolves a relative import.meta.url against the page
// origin, not the file. This test reads no DOM, so it runs in node.
const css = readFileSync(new URL("./tokens.css", import.meta.url), "utf8");

test("every core token the decks define is present", () => {
  // The decks are the source. A token missing here is a rule that
  // falls back to an inherited colour and looks almost right.
  const required = [
    "--u-0",
    "--u-50",
    "--u-100",
    "--u-200",
    "--u-300",
    "--u-400",
    "--u-500",
    "--u-550",
    "--u-600",
    "--u-700",
    "--u-800",
    "--u-850",
    "--u-900",
    "--u-950",
    "--green",
    "--green-ink",
    "--green-lift",
    "--amber",
    "--amber-ink",
    "--amber-lift",
    "--red",
    "--red-ink",
    "--red-lift",
    "--blue",
    "--blue-ink",
    "--blue-lift",
  ];
  for (const token of required) {
    expect(css).toContain(`${token}:`);
  }
});

test("the app layer names a token, never a hex", () => {
  // One hex outside the core block is a colour that no theme can
  // change, and it is invisible until somebody switches to dark.
  const appLayer = css.slice(css.indexOf("--app-ground"));
  expect(appLayer).not.toMatch(/#[0-9a-fA-F]{3,8}/);
});
