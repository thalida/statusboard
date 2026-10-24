/** Which tabs each screen has, and in which order.
 *
 * A tab is a path, so a screen and its tabs are declared together.
 * The first is the one a bare screen path shows.
 */
export const HOME_TABS = [
  { to: "/", label: "Board" },
  { to: "/updates", label: "Updates" },
] as const;

export const SERVICE_TABS = (slug: string) =>
  [
    { to: `/services/${slug}`, label: "Components" },
    { to: `/services/${slug}/updates`, label: "Updates" },
    { to: `/services/${slug}/about`, label: "About" },
  ] as const;

export const COMPONENT_TABS = (id: string) =>
  [
    { to: `/components/${id}`, label: "Components" },
    { to: `/components/${id}/updates`, label: "Updates" },
  ] as const;

export const EVENT_TABS = (id: string) =>
  [
    { to: `/events/${id}`, label: "Timeline" },
    { to: `/events/${id}/affects`, label: "Affects" },
    { to: `/events/${id}/about`, label: "About" },
  ] as const;
