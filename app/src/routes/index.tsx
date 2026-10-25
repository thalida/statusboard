import { createFileRoute } from "@tanstack/react-router";
import { useSyncExternalStore } from "react";
import { useGetMe } from "@/api/statusboard";
import { ComponentList } from "@/components/ComponentList";
import { FilterSelect } from "@/components/Filters";
import { LoadState } from "@/components/LoadState";
import { Shell } from "@/components/Shell";
import { Tabs } from "@/components/Tabs";
import { auth } from "@/lib/auth";
import { since } from "@/lib/duration";
import { useSeverityLabels } from "@/lib/meta";
import { useBoardPages, useComponentPages } from "@/lib/pagination";
import { boardSearch } from "@/lib/search";
import { HOME_TABS } from "@/lib/tabs";

export const Route = createFileRoute("/")({
  validateSearch: boardSearch,
  component: Board,
});

function Board() {
  const { severity, cursor } = Route.useSearch();
  const navigate = Route.useNavigate();
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
  const mine = useBoardPages(
    board ?? "",
    { status__severity: severity, cursor },
    Boolean(board),
  );
  const catalog = useComponentPages(
    { is_overall: true, status__severity: severity, cursor },
    !signedIn,
  );

  const list = signedIn ? mine : catalog;
  const rows = list.data?.pages.flatMap((page) => page.results ?? []) ?? [];
  const next = list.data?.pages.at(-1)?.next;
  const checked = list.data?.pages[0]?.aggregates?.oldest_refreshed_at;

  return (
    <Shell title="Home" checkedAt={checked ? `${since(checked)} ago` : null}>
      <Tabs tabs={HOME_TABS} />
      <div className="mb-4">
        <FilterSelect
          label="Severity"
          value={severity?.toString()}
          options={Object.entries(labels)
            .sort(([left], [right]) => Number(left) - Number(right))
            .map(([value, label]) => ({ value, label }))}
          onChange={(value) =>
            void navigate({
              search: (old) => ({
                ...old,
                severity: value === undefined ? undefined : Number(value),
                cursor: undefined,
              }),
            })
          }
        />
      </div>
      <LoadState
        loading={list.isLoading}
        error={list.isError}
        empty={
          list.data && rows.length === 0 ? "No components found." : undefined
        }
        onRetry={() => void list.refetch()}
      >
        {list.data ? (
          <ComponentList
            components={rows}
            next={next}
            loadingNext={list.isFetchingNextPage}
            onLoadMore={
              next
                ? async () => {
                    await list.fetchNextPage();
                    void navigate({
                      search: (old) => ({ ...old, cursor: next }),
                    });
                  }
                : undefined
            }
          />
        ) : null}
      </LoadState>
    </Shell>
  );
}
