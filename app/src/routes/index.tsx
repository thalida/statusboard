import { createFileRoute } from "@tanstack/react-router";
import { useSyncExternalStore } from "react";
import {
  useGetCatalogComponents,
  useGetDashboardsUuidComponents,
  useGetMe,
} from "@/api/statusboard";
import { Row } from "@/components/Row";
import { Shell } from "@/components/Shell";
import { Tabs } from "@/components/Tabs";
import { auth } from "@/lib/auth";
import { since } from "@/lib/duration";
import { useSeverityLabels } from "@/lib/meta";
import { boardSearch } from "@/lib/search";
import { HOME_TABS } from "@/lib/tabs";

export const Route = createFileRoute("/")({
  validateSearch: boardSearch,
  component: Board,
});

function Board() {
  const { severity } = Route.useSearch();
  const signedIn = useSyncExternalStore(
    auth.subscribe,
    () => auth.tokens() !== null,
    () => false,
  );
  const labels = useSeverityLabels();
  const me = useGetMe(undefined, { query: { enabled: signedIn } });
  const board = me.data?.default_dashboard_id;

  // Signed in it is your board. Signed out it is one row per
  // service, which is the same row narrowed to the rollups.
  const mine = useGetDashboardsUuidComponents(
    board ?? "",
    { status__severity: severity },
    { query: { enabled: Boolean(board) } },
  );
  const catalog = useGetCatalogComponents(
    { is_overall: true, status__severity: severity },
    { query: { enabled: !signedIn } },
  );

  const list = signedIn ? mine : catalog;
  const checked = list.data?.aggregates?.oldest_refreshed_at;

  return (
    <Shell title="Home" checkedAt={checked ? `${since(checked)} ago` : null}>
      <Tabs tabs={HOME_TABS} />
      {list.isError ? (
        <Unreachable onRetry={() => list.refetch()} />
      ) : (
        <ul className="grid gap-2 md:grid-cols-[repeat(auto-fill,minmax(212px,1fr))]">
          {(list.data?.results ?? []).map((component) => (
            <li key={component.id}>
              <Row
                component={component}
                label={labels[String(component.status?.severity)]}
                showMark
              />
            </li>
          ))}
        </ul>
      )}
    </Shell>
  );
}

function Unreachable({ onRetry }: { onRetry: () => void }) {
  return (
    <>
      <p>Can't reach statusboard.</p>
      <button type="button" onClick={onRetry} className="mt-3 underline">
        Retry
      </button>
    </>
  );
}
