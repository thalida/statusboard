import { Link } from "@tanstack/react-router";
import { Compass, House, LogIn, Settings } from "lucide-react";
import { useSyncExternalStore } from "react";
import { auth } from "@/lib/auth";

/** Three destinations, in a pill on a phone and a bar on a desktop.
 *
 * The phone pill is fixed to the bottom, so Header can hold this in
 * its bar and only the desktop reads it there.
 *
 * A destination is an outlined pill on a desktop, and filled while it
 * is the one you are on. A filled shape means one thing in this app,
 * which is the screen you are reading.
 *
 * Every icon is Lucide. The Figma marks are filled and Lucide is
 * stroked, and one nav cannot carry two weights.
 */
export function Nav() {
  const signedIn = useSyncExternalStore(
    auth.subscribe,
    () => auth.tokens() !== null,
    () => false,
  );

  const third = signedIn
    ? { to: "/settings", label: "Settings", Icon: Settings }
    : { to: "/signin", label: "Sign in", Icon: LogIn };

  const items = [
    { to: "/", label: "Home", Icon: House },
    { to: "/discover", label: "Discover", Icon: Compass },
    third,
  ] as const;

  return (
    <nav
      className="fixed inset-x-4 bottom-4 flex justify-around rounded-full
                 bg-app-nav px-2 py-2 text-app-nav-ink
                 md:static md:inset-auto md:justify-start md:gap-1 md:rounded-none
                 md:bg-transparent md:px-0 md:py-0 md:text-app-ink"
    >
      {items.map(({ to, label, Icon }) => (
        <Link
          key={to}
          to={to}
          className="flex flex-col items-center gap-1 px-4 py-1 text-xs
                     md:flex-row md:gap-2 md:rounded-full md:border
                     md:border-app-edge md:px-3 md:py-1 md:text-sm"
          activeProps={{
            className:
              "font-semibold md:border-app-nav md:bg-app-nav md:text-app-nav-ink",
          }}
        >
          <Icon size={20} aria-hidden />
          {label}
        </Link>
      ))}
    </nav>
  );
}
