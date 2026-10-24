import { Link } from "@tanstack/react-router";

/** A tabbed screen's tabs.
 *
 * A tab is a path, so each is a link the router marks active. The
 * header stays put and only the body below swaps, which is the
 * decks' rule for a tabbed screen.
 */
export function Tabs({
  tabs,
}: {
  tabs: readonly { to: string; label: string }[];
}) {
  return (
    <nav aria-label="Tabs" className="mb-3 flex gap-2">
      {tabs.map(({ to, label }) => (
        <Link
          key={to}
          to={to}
          // An inactive tab is outlined and the active one fills, the
          // same rule the destinations use.
          className="rounded-full border border-app-edge px-3 py-1 text-sm"
          activeProps={{
            className: "border-app-nav bg-app-nav text-app-nav-ink",
          }}
          activeOptions={{ exact: true }}
        >
          {label}
        </Link>
      ))}
    </nav>
  );
}
