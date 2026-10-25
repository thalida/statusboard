import { Link } from "@tanstack/react-router";
import type { GetEventsParams } from "@/api/model";
import { useGetCatalogComponentsUuid } from "@/api/statusboard";
import { ComponentList } from "@/components/ComponentList";
import { EventFeed } from "@/components/EventFeed";
import { FilterSelect } from "@/components/Filters";
import { LoadState } from "@/components/LoadState";
import { Shell } from "@/components/Shell";
import { Tabs } from "@/components/Tabs";
import { useSeverityLabels } from "@/lib/meta";
import { useComponentPages, useEventPages } from "@/lib/pagination";
import { COMPONENT_TABS } from "@/lib/tabs";

export function ComponentScreen({
  id,
  tab,
  severity,
  tracking,
  cursor,
  eventParams,
  onComponentFilter,
  onEventFilter,
  onComponentCursor,
  onEventCursor,
}: {
  id: string;
  tab: "components" | "updates";
  severity?: number;
  tracking?: string;
  cursor?: string;
  eventParams: GetEventsParams;
  onComponentFilter: (name: "severity" | "tracking", value?: string) => void;
  onEventFilter: (name: "kind" | "phase", value?: string) => void;
  onComponentCursor?: (cursor: string) => void;
  onEventCursor?: (cursor: string) => void;
}) {
  const detail = useGetCatalogComponentsUuid(id);
  const component = detail.data;
  const descendants = useComponentPages(
    {
      ancestor: id,
      ordering: "status_page_order",
      cursor,
      status__severity: severity,
      is_tracked:
        tracking === "tracked"
          ? true
          : tracking === "untracked"
            ? false
            : undefined,
    },
    tab === "components",
  );
  const events = useEventPages({ ...eventParams, component: id });
  const labels = useSeverityLabels();
  const tabs = COMPONENT_TABS(id).map((item) =>
    item.label === "Updates" &&
    events.data?.pages[0]?.aggregates?.total !== undefined
      ? { ...item, badge: events.data.pages[0].aggregates.total }
      : item,
  );
  const rows =
    descendants.data?.pages.flatMap((page) => page.results ?? []) ?? [];
  const next = descendants.data?.pages.at(-1)?.next;

  return (
    <Shell title={component?.name ?? "Component"}>
      <Tabs tabs={tabs} />
      <LoadState
        loading={detail.isLoading}
        error={detail.isError}
        onRetry={() => void detail.refetch()}
      >
        {component ? (
          <>
            <nav
              aria-label="Breadcrumb"
              className="mb-3 flex gap-2 text-sm text-app-ink-3"
            >
              {component.service ? (
                <Link
                  className="underline"
                  to="/services/$slug"
                  params={{ slug: component.service.slug ?? "" }}
                >
                  {component.service.name}
                </Link>
              ) : null}
              {component.path?.map((node) =>
                node.is_overall && component.service?.slug ? (
                  <Link
                    key={node.id}
                    to="/services/$slug"
                    params={{ slug: component.service.slug }}
                    className="underline"
                  >
                    {node.name}
                  </Link>
                ) : node.id ? (
                  <Link
                    key={node.id}
                    to="/components/$id"
                    params={{ id: node.id }}
                    className="underline"
                  >
                    {node.name}
                  </Link>
                ) : (
                  <span key={node.name}>{node.name}</span>
                ),
              )}
            </nav>
            <p className="mb-4 rounded-2xl border border-app-edge bg-app-card p-4">
              {labels[String(component.status?.severity)] ??
                "Status unavailable"}
              {component.status?.started_at
                ? ` · ${new Date(component.status.started_at).toLocaleString()}`
                : ""}
            </p>
            {tab === "components" ? (
              <>
                <div className="mb-4 flex flex-wrap gap-3">
                  <FilterSelect
                    label="Severity"
                    value={severity?.toString()}
                    options={Object.entries(labels)
                      .sort(([left], [right]) => Number(left) - Number(right))
                      .map(([value, label]) => ({ value, label }))}
                    onChange={(value) => onComponentFilter("severity", value)}
                  />
                  <FilterSelect
                    label="Tracking"
                    value={tracking}
                    options={[
                      { value: "tracked", label: "Tracked" },
                      { value: "untracked", label: "Untracked" },
                    ]}
                    onChange={(value) => onComponentFilter("tracking", value)}
                  />
                </div>
                <p className="mb-3 text-sm text-app-ink-3">Smart</p>
                <LoadState
                  loading={descendants.isLoading}
                  error={descendants.isError}
                  empty={
                    descendants.data && rows.length === 0
                      ? "No components found."
                      : undefined
                  }
                  onRetry={() => void descendants.refetch()}
                >
                  {descendants.data ? (
                    <ComponentList
                      components={rows}
                      next={next}
                      loadingNext={descendants.isFetchingNextPage}
                      onLoadMore={
                        next
                          ? async () => {
                              await descendants.fetchNextPage();
                              onComponentCursor?.(next);
                            }
                          : undefined
                      }
                    />
                  ) : null}
                </LoadState>
              </>
            ) : null}
            {tab === "updates" ? (
              <EventFeed
                params={eventParams}
                feed={events}
                onFilter={(name, value) => onEventFilter(name, value)}
                onCursor={onEventCursor}
              />
            ) : null}
          </>
        ) : null}
      </LoadState>
    </Shell>
  );
}
