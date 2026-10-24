/** Brand and the refresh stamp on one row, the page title on the next.
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
    <header className="px-4 pt-4">
      <div className="flex items-baseline justify-between">
        <span className="font-semibold">statusboard</span>
        {checkedAt ? (
          <span className="text-xs text-app-ink-3">Checked {checkedAt}</span>
        ) : null}
      </div>
      <h1 className="mt-3 text-2xl font-semibold">{title}</h1>
    </header>
  );
}
