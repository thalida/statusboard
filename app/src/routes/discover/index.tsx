import { createFileRoute, Link } from "@tanstack/react-router";
import { useState, useSyncExternalStore } from "react";
import { ComponentList } from "@/components/ComponentList";
import { LoadState } from "@/components/LoadState";
import { Shell } from "@/components/Shell";
import { useSeverityLabels } from "@/lib/meta";
import { useComponentPages } from "@/lib/pagination";
import { suggestedServices } from "@/lib/preferences";
import { discoverSearch } from "@/lib/search";

export const Route = createFileRoute("/discover/")({
  validateSearch: discoverSearch,
  component: Discover,
});

function Discover() {
  const { q, severity, cursor } = Route.useSearch();
  const [query, setQuery] = useState(q ?? "");
  const navigate = Route.useNavigate();
  const labels = useSeverityLabels();
  const showSuggested = useSyncExternalStore(
    suggestedServices.subscribe,
    suggestedServices.read,
    () => true,
  );
  const list = useComponentPages(
    { q, status__severity: severity, cursor },
    Boolean(q) || showSuggested,
  );
  const components =
    list.data?.pages.flatMap((page) => page.results ?? []) ?? [];
  const next = list.data?.pages.at(-1)?.next;

  return (
    <Shell title="Discover">
      <div className="mb-4 flex justify-end">
        <Link
          to="/discover/add"
          className="rounded-full border border-app-edge px-4 py-2"
        >
          Add by URL
        </Link>
      </div>
      <form
        className="mb-4 flex flex-wrap gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void navigate({
            search: (old) => ({
              ...old,
              q: query || undefined,
              cursor: undefined,
            }),
          });
        }}
      >
        <label className="sr-only" htmlFor="discover-query">
          Search components
        </label>
        <input
          id="discover-query"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search services and components"
          className="min-w-0 flex-1 rounded-xl border border-app-edge bg-app-card px-3 py-2"
        />
        <button
          className="rounded-full bg-app-nav px-4 py-2 text-app-nav-ink"
          type="submit"
        >
          Search
        </button>
        <label className="sr-only" htmlFor="discover-severity">
          Severity
        </label>
        <select
          id="discover-severity"
          aria-label="Severity"
          value={severity ?? ""}
          onChange={(event) =>
            void navigate({
              search: (old) => ({
                ...old,
                severity: event.target.value
                  ? Number(event.target.value)
                  : undefined,
                cursor: undefined,
              }),
            })
          }
          className="rounded-xl border border-app-edge bg-app-card px-3 py-2"
        >
          <option value="">All severities</option>
          {Object.entries(labels)
            .sort(([left], [right]) => Number(left) - Number(right))
            .map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
        </select>
      </form>
      <p className="mb-3 text-sm text-app-ink-3">Smart</p>
      {!q && !showSuggested ? (
        <p>Search for a service or component to see matches.</p>
      ) : (
        <LoadState
          loading={list.isLoading}
          error={list.isError}
          empty={
            list.data && components.length === 0
              ? "No components found."
              : undefined
          }
          onRetry={() => void list.refetch()}
        >
          {list.data ? (
            <ComponentList
              components={components}
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
      )}
    </Shell>
  );
}
