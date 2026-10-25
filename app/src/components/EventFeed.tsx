import { useEffect, useState } from "react";
import type { GetEventsParams } from "@/api/model";
import { useGetMeta } from "@/api/statusboard";
import { EventList } from "@/components/EventList";
import { FilterSelect } from "@/components/Filters";
import { LoadState } from "@/components/LoadState";
import type { useEventPages } from "@/lib/pagination";

export function EventFeed({
  params,
  feed,
  onFilter,
  onTextFilter,
  textFields = ["service", "component"],
  onCursor,
}: {
  params: GetEventsParams;
  feed: ReturnType<typeof useEventPages>;
  onFilter?: (name: "kind" | "phase", value?: string) => void;
  onTextFilter?: (name: "service" | "component", value?: string) => void;
  textFields?: Array<"service" | "component">;
  onCursor?: (cursor: string) => void;
}) {
  const meta = useGetMeta(undefined, {
    query: { staleTime: Number.POSITIVE_INFINITY },
  });
  const enums = meta.data?.enums;
  const [service, setService] = useState(params.service ?? "");
  const [component, setComponent] = useState(params.component ?? "");
  const events = feed.data?.pages.flatMap((page) => page.results ?? []) ?? [];
  const next = feed.data?.pages.at(-1)?.next;
  const total = feed.data?.pages[0]?.aggregates?.total ?? 0;
  useEffect(() => {
    setService(params.service ?? "");
    setComponent(params.component ?? "");
  }, [params.service, params.component]);

  return (
    <>
      {onFilter ? (
        <div className="mb-4 flex flex-wrap gap-3">
          <FilterSelect
            label="Kind"
            value={params.kind}
            options={Object.entries(enums?.event_kind ?? {}).map(
              ([value, label]) => ({ value, label }),
            )}
            onChange={(value) => onFilter("kind", value)}
          />
          <FilterSelect
            label="Phase"
            value={params.phase}
            options={Object.entries(enums?.event_phase_state ?? {}).map(
              ([value, label]) => ({ value, label }),
            )}
            onChange={(value) => onFilter("phase", value)}
          />
        </div>
      ) : null}
      {onTextFilter ? (
        <form
          className="mb-4 flex flex-wrap gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (textFields.includes("service")) {
              onTextFilter("service", service || undefined);
            }
            if (textFields.includes("component")) {
              onTextFilter("component", component || undefined);
            }
          }}
        >
          {textFields.includes("service") ? (
            <>
              <label className="sr-only" htmlFor="service-filter">
                Service
              </label>
              <input
                id="service-filter"
                value={service}
                onChange={(event) => setService(event.target.value)}
                placeholder="Service slug"
                className="rounded-xl border border-app-edge bg-app-card px-3 py-2"
              />
            </>
          ) : null}
          {textFields.includes("component") ? (
            <>
              <label className="sr-only" htmlFor="component-filter">
                Component
              </label>
              <input
                id="component-filter"
                value={component}
                onChange={(event) => setComponent(event.target.value)}
                placeholder="Component ID"
                className="min-w-0 rounded-xl border border-app-edge bg-app-card px-3 py-2"
              />
            </>
          ) : null}
          <button
            type="submit"
            className="rounded-full border border-app-edge px-4 py-2"
          >
            Filter
          </button>
        </form>
      ) : null}
      <p className="mb-3 text-sm text-app-ink-3">Updates {total}</p>
      <LoadState
        loading={feed.isLoading}
        error={feed.isError}
        empty={
          feed.data && events.length === 0 ? "No updates found." : undefined
        }
        onRetry={() => void feed.refetch()}
      >
        {feed.data ? (
          <EventList
            events={events}
            next={next}
            loadingNext={feed.isFetchingNextPage}
            onLoadMore={
              next
                ? async () => {
                    await feed.fetchNextPage();
                    onCursor?.(next);
                  }
                : undefined
            }
          />
        ) : null}
      </LoadState>
    </>
  );
}
