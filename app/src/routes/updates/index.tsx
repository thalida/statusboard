import { createFileRoute, Link } from "@tanstack/react-router";
import { useSyncExternalStore } from "react";
import { useGetMe } from "@/api/statusboard";
import { EventFeed } from "@/components/EventFeed";
import { Shell } from "@/components/Shell";
import { Tabs } from "@/components/Tabs";
import { auth } from "@/lib/auth";
import { useEventPages } from "@/lib/pagination";
import { updatesSearch } from "@/lib/search";
import { HOME_TABS } from "@/lib/tabs";

export const Route = createFileRoute("/updates/")({
  validateSearch: updatesSearch,
  component: Updates,
});

function Updates() {
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  const signedIn = useSyncExternalStore(
    auth.subscribe,
    () => auth.tokens() !== null,
    () => false,
  );
  const me = useGetMe(undefined, { query: { enabled: signedIn } });
  const dashboard = me.data?.default_dashboard_id;
  const feed = useEventPages({ dashboard, ...search }, Boolean(dashboard));
  const count = feed.data?.pages[0]?.aggregates?.total;
  const tabs = HOME_TABS.map((tab) =>
    tab.label === "Updates" && count !== undefined
      ? { ...tab, badge: count }
      : tab,
  );

  return (
    <Shell title="Home">
      <Tabs tabs={tabs} />
      {!signedIn ? (
        <p>
          <Link className="underline" to="/signin">
            Sign in
          </Link>{" "}
          to see updates from your board.
        </p>
      ) : (
        <EventFeed
          params={{ dashboard, ...search }}
          feed={feed}
          onFilter={(name, value) =>
            void navigate({
              search: (old) => ({ ...old, [name]: value, cursor: undefined }),
            })
          }
          onTextFilter={(name, value) =>
            void navigate({
              search: (old) => ({ ...old, [name]: value, cursor: undefined }),
            })
          }
          onCursor={(cursor) =>
            void navigate({ search: (old) => ({ ...old, cursor }) })
          }
        />
      )}
    </Shell>
  );
}
