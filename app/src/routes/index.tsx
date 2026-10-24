import { createFileRoute } from "@tanstack/react-router";
import { useSyncExternalStore } from "react";
import {
  useGetCatalogComponents,
  useGetDashboardsUuidComponents,
  useGetMe,
} from "@/api/statusboard";
import { Row } from "@/components/Row";
import { Shell } from "@/components/Shell";
import { auth } from "@/lib/auth";
import { since } from "@/lib/duration";
import { useSeverityLabels } from "@/lib/meta";
import { homeSearch } from "@/lib/search";

export const Route = createFileRoute("/")({
  validateSearch: homeSearch,
  component: Home,
});

function Home() {
  const { tab, severity } = Route.useSearch();
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

  if (list.isError) return <Unreachable onRetry={() => list.refetch()} />;

  const rows = list.data?.results ?? [];
  const checked = list.data?.aggregates?.oldest_refreshed_at;

  return (
    <Shell title="Home" checkedAt={checked ? `${since(checked)} ago` : null}>
      {tab === "board" ? (
        <ul className="grid gap-2 md:grid-cols-[repeat(auto-fill,minmax(212px,1fr))]">
          {rows.map((component) => (
            <li key={component.id}>
              <Row
                component={component}
                label={labels[String(component.status?.severity)]}
                showMark
              />
            </li>
          ))}
        </ul>
      ) : (
        <p>Updates arrives with the next plan.</p>
      )}
    </Shell>
  );
}

function Unreachable({ onRetry }: { onRetry: () => void }) {
  return (
    <Shell title="Home">
      <p>Can't reach statusboard.</p>
      <button type="button" onClick={onRetry} className="mt-3 underline">
        Retry
      </button>
    </Shell>
  );
}
