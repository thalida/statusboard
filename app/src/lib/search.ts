/** What a URL may say, per screen.
 *
 * A tab is a path, so these carry filters only. Every filter is
 * server-side, which is what makes a URL the whole of a screen's
 * state and a reload restore it.
 *
 * A value the API would refuse is dropped here, once, rather than by
 * each screen. Each schema takes the filters its own tab takes, so a
 * link cannot send one screen a parameter another screen owns.
 */

type Raw = Record<string, unknown>;

/** Drops the filters nobody set.
 *
 * A key set to undefined is still a key, and the router then asks
 * every link to carry a search object. An unset filter is absent.
 */
function set<T extends object>(filters: T) {
  return Object.fromEntries(
    Object.entries(filters).filter(([, value]) => value !== undefined),
  ) as { [K in keyof T]?: Exclude<T[K], undefined> };
}

function oneOf<T extends string>(values: readonly T[], fallback: T) {
  return (raw: unknown): T | undefined => {
    // An absent filter is not a defaulted one. It asks for
    // everything, so it stays absent.
    if (raw === undefined) return undefined;
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

const kind = oneOf(["incident", "maintenance"] as const, "incident");
const phase = oneOf(["open", "closed"] as const, "open");
const tracking = oneOf(["all", "tracked", "untracked"] as const, "all");

/** `/` — the board. */
export function boardSearch(raw: Raw) {
  return set({ severity: severity(raw.severity) });
}

/** `/updates` — every update across your board. */
export function updatesSearch(raw: Raw) {
  return set({
    service: text(raw.service),
    component: text(raw.component),
    kind: kind(raw.kind),
    phase: phase(raw.phase),
  });
}

/** `/discover` — one body, no tabs. */
export function discoverSearch(raw: Raw) {
  return set({ q: text(raw.q), severity: severity(raw.severity) });
}

/** `/services/$slug` — the components tab. */
export function serviceComponentsSearch(raw: Raw) {
  return set({
    severity: severity(raw.severity),
    tracking: tracking(raw.tracking),
  });
}

/** `/services/$slug/updates`. */
export function serviceUpdatesSearch(raw: Raw) {
  return set({
    component: text(raw.component),
    kind: kind(raw.kind),
    phase: phase(raw.phase),
  });
}

/** `/components/$id` — the same list one level down. */
export const componentComponentsSearch = serviceComponentsSearch;

/** `/components/$id/updates`. A component is the filter, so it takes none. */
export function componentUpdatesSearch(raw: Raw) {
  return set({ kind: kind(raw.kind), phase: phase(raw.phase) });
}
