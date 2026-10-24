import { Nav } from "./Nav";

/** The bar every screen wears, and the page title under it.
 *
 * On a desktop the brand, the destinations and the stamp share one
 * bordered bar. On a phone the destinations are a fixed pill at the
 * bottom, so the bar holds the brand and the stamp alone.
 *
 * The stamp is not a control. There is no manual refresh: a page load
 * already shows the freshest data the poller holds.
 */
export function Header({
  title,
  checkedAt,
}: {
  title: string;
  checkedAt?: string | null;
}) {
  return (
    <header>
      <div
        className="flex items-center gap-6 px-4 pt-4
                   md:border-app-edge md:border-b md:pb-3"
      >
        <span className="font-semibold">statusboard</span>
        {/* Fixed on a phone, so sitting in the bar costs nothing
            there and puts it in the bar on a desktop. */}
        <Nav />
        {checkedAt ? (
          <span className="ml-auto text-app-ink-3 text-xs">
            Checked {checkedAt}
          </span>
        ) : null}
      </div>
      <h1 className="mt-3 px-4 font-semibold text-2xl">{title}</h1>
    </header>
  );
}
