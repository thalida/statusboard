/** What a URL may say, per screen.
 *
 * Every filter is server-side, so a URL is the whole of a screen's
 * state and a reload restores it. A value the API would refuse is
 * dropped here, once, rather than by each screen.
 */

type Raw = Record<string, unknown>;

function oneOf<T extends string>(values: readonly T[], fallback: T) {
  return (raw: unknown): T => {
    const text = String(raw ?? "");
    return (values as readonly string[]).includes(text)
      ? (text as T)
      : fallback;
  };
}

function severity(raw: unknown): number | undefined {
  const value = Number(raw);
  // Severity is 0 to 5, and 0 is a real value, so a falsy check
  // would silently drop the worst one.
  return Number.isInteger(value) && value >= 0 && value <= 5
    ? value
    : undefined;
}

function text(raw: unknown): string | undefined {
  const value = String(raw ?? "").trim();
  return value === "" ? undefined : value;
}

const homeTab = oneOf(["board", "updates"] as const, "board");
const discoverTab = oneOf(["components"] as const, "components");
const serviceTab = oneOf(
  ["components", "updates", "about"] as const,
  "components",
);
const componentTab = oneOf(["components", "updates"] as const, "components");
const eventTab = oneOf(["timeline", "affects", "about"] as const, "timeline");
const kind = oneOf(["incident", "maintenance"] as const, "incident");
const phase = oneOf(["open", "closed"] as const, "open");
const tracking = oneOf(["all", "tracked", "untracked"] as const, "all");

export function homeSearch(raw: Raw) {
  return {
    tab: homeTab(raw.tab),
    severity: severity(raw.severity),
    service: text(raw.service),
    component: text(raw.component),
    kind: raw.kind === undefined ? undefined : kind(raw.kind),
    phase: raw.phase === undefined ? undefined : phase(raw.phase),
  };
}

export function discoverSearch(raw: Raw) {
  return {
    tab: discoverTab(raw.tab),
    q: text(raw.q),
    severity: severity(raw.severity),
  };
}

export function serviceSearch(raw: Raw) {
  return {
    tab: serviceTab(raw.tab),
    severity: severity(raw.severity),
    tracking: raw.tracking === undefined ? undefined : tracking(raw.tracking),
    component: text(raw.component),
    kind: raw.kind === undefined ? undefined : kind(raw.kind),
    phase: raw.phase === undefined ? undefined : phase(raw.phase),
  };
}

export function componentSearch(raw: Raw) {
  // A component screen filters its own children, so it has no
  // component filter of its own to carry.
  const { component: _component, ...rest } = serviceSearch(raw);
  return { ...rest, tab: componentTab(raw.tab) };
}

export function eventSearch(raw: Raw) {
  return { tab: eventTab(raw.tab) };
}
