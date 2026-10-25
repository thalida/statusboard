import { Link } from "@tanstack/react-router";
import type { EventUpdate } from "@/api/model";
import { useGetEventsUuid, useGetMeta } from "@/api/statusboard";
import { ComponentList } from "@/components/ComponentList";
import { LoadState } from "@/components/LoadState";
import { Shell } from "@/components/Shell";
import { Tabs } from "@/components/Tabs";
import { eventPhaseLabel } from "@/lib/meta";
import { useComponentPages, useEventUpdatePages } from "@/lib/pagination";
import { EVENT_TABS } from "@/lib/tabs";

export function EventScreen({
  id,
  tab,
  cursor,
  onCursor,
}: {
  id: string;
  tab: "timeline" | "affects" | "about";
  cursor?: string;
  onCursor?: (cursor: string) => void;
}) {
  const eventQuery = useGetEventsUuid(id);
  const event = eventQuery.data;
  const timeline = useEventUpdatePages(id, cursor, tab === "timeline");
  const affects = useComponentPages(
    { event: id, ordering: "status_page_order", cursor },
    tab === "affects",
  );
  const meta = useGetMeta(undefined, {
    query: { staleTime: Number.POSITIVE_INFINITY },
  });
  const tabs = EVENT_TABS(id).map((item) => {
    if (item.label !== "Affects" || event?.affected_count === undefined)
      return item;
    return { ...item, badge: event.affected_count };
  });

  return (
    <Shell title={event?.title ?? "Event"}>
      <Tabs tabs={tabs} />
      <LoadState
        loading={eventQuery.isLoading}
        error={eventQuery.isError}
        onRetry={() => void eventQuery.refetch()}
      >
        {event ? (
          <>
            <div className="mb-4 rounded-2xl border border-app-edge bg-app-card p-4">
              <p className="text-sm text-app-ink-3">
                {meta.data?.enums?.event_kind?.[event.kind ?? ""]} ·{" "}
                {eventPhaseLabel(meta.data?.enums, event.kind, event.phase)}
              </p>
              <p className="mt-2">
                <Link
                  to="/services/$slug"
                  params={{ slug: event.service?.slug ?? "" }}
                  className="underline"
                >
                  {event.service?.name}
                </Link>
              </p>
              {event.starts_at ? (
                <time
                  className="mt-2 block text-sm text-app-ink-3"
                  dateTime={event.starts_at}
                >
                  Started {new Date(event.starts_at).toLocaleString()}
                </time>
              ) : null}
            </div>
            {tab === "timeline" ? (
              <LoadState
                loading={timeline.isLoading}
                error={timeline.isError}
                empty={
                  timeline.data?.pages.every((page) => !page.results?.length)
                    ? "No updates yet."
                    : undefined
                }
                onRetry={() => void timeline.refetch()}
              >
                {timeline.data ? (
                  <Timeline
                    updates={timeline.data.pages.flatMap(
                      (page) => page.results ?? [],
                    )}
                    kind={event.kind}
                    next={timeline.data.pages.at(-1)?.next}
                    loadingNext={timeline.isFetchingNextPage}
                    onLoadMore={
                      timeline.data.pages.at(-1)?.next
                        ? async () => {
                            const next = timeline.data?.pages.at(-1)?.next;
                            if (!next) return;
                            await timeline.fetchNextPage();
                            onCursor?.(next);
                          }
                        : undefined
                    }
                  />
                ) : null}
              </LoadState>
            ) : null}
            {tab === "affects" ? (
              <LoadState
                loading={affects.isLoading}
                error={affects.isError}
                empty={
                  affects.data &&
                  affects.data.pages.flatMap((page) => page.results ?? [])
                    .length === 0
                    ? "No components were affected."
                    : undefined
                }
                onRetry={() => void affects.refetch()}
              >
                {affects.data ? (
                  <ComponentList
                    components={affects.data.pages.flatMap(
                      (page) => page.results ?? [],
                    )}
                    next={affects.data.pages.at(-1)?.next}
                    loadingNext={affects.isFetchingNextPage}
                    onLoadMore={
                      affects.data.pages.at(-1)?.next
                        ? async () => {
                            const next = affects.data?.pages.at(-1)?.next;
                            if (!next) return;
                            await affects.fetchNextPage();
                            onCursor?.(next);
                          }
                        : undefined
                    }
                  />
                ) : null}
              </LoadState>
            ) : null}
            {tab === "about" ? (
              <dl className="grid max-w-xl gap-4 rounded-2xl border border-app-edge bg-app-card p-4">
                <div>
                  <dt className="text-xs text-app-ink-3">Kind</dt>
                  <dd>
                    {meta.data?.enums?.event_kind?.[event.kind ?? ""] ??
                      event.kind}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-app-ink-3">Phase</dt>
                  <dd>
                    {eventPhaseLabel(meta.data?.enums, event.kind, event.phase)}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-app-ink-3">Detected by</dt>
                  <dd>
                    {meta.data?.enums?.event_source?.[
                      event.detected_by ?? ""
                    ] ?? event.detected_by}
                  </dd>
                </div>
                {event.ends_at ? (
                  <div>
                    <dt className="text-xs text-app-ink-3">Ended</dt>
                    <dd>{new Date(event.ends_at).toLocaleString()}</dd>
                  </div>
                ) : null}
              </dl>
            ) : null}
          </>
        ) : null}
      </LoadState>
    </Shell>
  );
}

function Timeline({
  updates,
  kind,
  next,
  loadingNext,
  onLoadMore,
}: {
  updates: EventUpdate[];
  kind?: string;
  next?: string | null;
  loadingNext: boolean;
  onLoadMore?: () => void;
}) {
  const meta = useGetMeta(undefined, {
    query: { staleTime: Number.POSITIVE_INFINITY },
  });
  return (
    <div>
      <ol className="grid gap-3">
        {updates.map((update) => (
          <li
            key={`${update.posted_at}-${update.phase}-${update.body}`}
            className="rounded-2xl border border-app-edge bg-app-card p-4"
          >
            {update.posted_at ? (
              <time
                className="text-xs text-app-ink-3"
                dateTime={update.posted_at}
              >
                {new Date(update.posted_at).toLocaleString()}
              </time>
            ) : null}
            <p className="mt-2">{update.body}</p>
            <p className="mt-2 text-xs text-app-ink-3">
              {eventPhaseLabel(meta.data?.enums, kind, update.phase)} ·{" "}
              {meta.data?.enums?.event_source?.[update.source ?? ""] ??
                update.source}
            </p>
          </li>
        ))}
      </ol>
      {next ? (
        <button
          type="button"
          onClick={onLoadMore}
          disabled={loadingNext}
          className="mt-4 rounded-full border border-app-edge px-4 py-2"
        >
          {loadingNext ? "Loading…" : "Load more"}
        </button>
      ) : null}
    </div>
  );
}
