// @vitest-environment node
import { readFileSync } from "node:fs";

// jsdom's URL resolves a relative import.meta.url against the page
// origin, not the file. This test reads no DOM, so it runs in node.
const css = readFileSync(new URL("./tokens.css", import.meta.url), "utf8");

test("every core token the app uses is present", () => {
  // The decks are the source. A token missing here is a rule that
  // falls back to an inherited colour and looks almost right.
  // The decks' lifted hues are left out: they are for type on
  // dark, and the app has no dark theme.
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
    "--amber",
    "--amber-ink",
    "--red",
    "--red-ink",
    "--blue",
    "--blue-ink",
  ];
  for (const token of required) {
    expect(css).toContain(`${token}:`);
  }
});

test("the app layer names a token, never a hex", () => {
  // One hex outside the core block is a colour that no theme can
  // change, and a colour no theme can change is the whole reason
  // this layer exists.
  const appLayer = css.slice(css.indexOf("--app-ground"));
  expect(appLayer).not.toMatch(/#[0-9a-fA-F]{3,8}/);
});

test("there is no dark theme", () => {
  // The app is light, and the decks draw it that way. A derived dark
  // theme nobody had approved used to apply from the system alone.
  expect(css).not.toContain("data-theme");
  expect(css).not.toMatch(/@media[^{]*prefers-color-scheme/);
  expect(css).not.toContain("-lift");
});
