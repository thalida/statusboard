import type { GetCatalogComponentsParams, GetEventsParams } from "@/api/model";
import { useGetCatalogServicesSlug, useGetMeta } from "@/api/statusboard";
import {
  ComponentList,
  TrackComponentButton,
} from "@/components/ComponentList";
import { EventFeed } from "@/components/EventFeed";
import { FilterSelect } from "@/components/Filters";
import { LoadState } from "@/components/LoadState";
import { Shell } from "@/components/Shell";
import { Tabs } from "@/components/Tabs";
import { useSeverityLabels } from "@/lib/meta";
import { useComponentPages, useEventPages } from "@/lib/pagination";
import { SERVICE_TABS } from "@/lib/tabs";

export function ServiceScreen({
  slug,
  tab,
  componentParams,
  eventParams,
  onComponentFilter,
  onEventFilter,
  onEventTextFilter,
  onComponentCursor,
  onEventCursor,
}: {
  slug: string;
  tab: "components" | "updates" | "about";
  componentParams: GetCatalogComponentsParams & { tracking?: string };
  eventParams: GetEventsParams;
  onComponentFilter: (name: "severity" | "tracking", value?: string) => void;
  onEventFilter: (name: "kind" | "phase", value?: string) => void;
  onEventTextFilter?: (value?: string) => void;
  onComponentCursor?: (cursor: string) => void;
  onEventCursor?: (cursor: string) => void;
}) {
  const serviceQuery = useGetCatalogServicesSlug(slug);
  const components = useComponentPages(
    {
      service: slug,
      is_overall: false,
      ordering: "status_page_order",
      status__severity: componentParams.status__severity,
      cursor: componentParams.cursor,
      is_tracked:
        componentParams.tracking === "tracked"
          ? true
          : componentParams.tracking === "untracked"
            ? false
            : undefined,
    },
    tab === "components",
  );
  const events = useEventPages({ ...eventParams, service: slug });
  const meta = useGetMeta(undefined, {
    query: { staleTime: Number.POSITIVE_INFINITY },
  });
  const labels = useSeverityLabels();
  const service = serviceQuery.data;
  const overall = service?.overall_component;
  const eventCount = events.data?.pages[0]?.aggregates?.total;
  const componentRows =
    components.data?.pages.flatMap((page) => page.results ?? []) ?? [];
  const nextComponents = components.data?.pages.at(-1)?.next;
  const tabs = SERVICE_TABS(slug).map((item) =>
    item.label === "Updates" && eventCount !== undefined
      ? { ...item, badge: eventCount }
      : item,
  );

  return (
    <Shell title={service?.name ?? "Service"}>
      <Tabs tabs={tabs} />
      <LoadState
        loading={serviceQuery.isLoading}
        error={serviceQuery.isError}
        onRetry={() => void serviceQuery.refetch()}
      >
        {service ? (
          <>
            <div className="mb-4 flex items-center justify-between rounded-2xl border border-app-edge bg-app-card p-4">
              <div>
                <p>
                  {labels[String(overall?.status?.severity)] ??
                    "Status unavailable"}
                  {overall?.status?.started_at
                    ? ` · ${new Date(overall.status.started_at).toLocaleString()}`
                    : ""}
                </p>
                <p className="mt-1 text-sm text-app-ink-3">
                  {service.component_count ?? 0} components ·{" "}
                  {service.tracked_component_count ?? 0} tracked
                </p>
              </div>
              {overall ? <TrackComponentButton component={overall} /> : null}
            </div>
            {tab === "components" ? (
              <>
                <div className="mb-4 flex flex-wrap gap-3">
                  <FilterSelect
                    label="Severity"
                    value={componentParams.status__severity?.toString()}
                    options={Object.entries(labels)
                      .sort(([left], [right]) => Number(left) - Number(right))
                      .map(([value, label]) => ({ value, label }))}
                    onChange={(value) => onComponentFilter("severity", value)}
                  />
                  <FilterSelect
                    label="Tracking"
                    value={componentParams.tracking}
                    options={[
                      { value: "tracked", label: "Tracked" },
                      { value: "untracked", label: "Untracked" },
                    ]}
                    onChange={(value) => onComponentFilter("tracking", value)}
                  />
                </div>
                <p className="mb-3 text-sm text-app-ink-3">Smart</p>
                <LoadState
                  loading={components.isLoading}
                  error={components.isError}
                  empty={
                    components.data && componentRows.length === 0
                      ? "No components found."
                      : undefined
                  }
                  onRetry={() => void components.refetch()}
                >
                  {components.data ? (
                    <ComponentList
                      components={componentRows}
                      next={nextComponents}
                      loadingNext={components.isFetchingNextPage}
                      onLoadMore={
                        nextComponents
                          ? async () => {
                              await components.fetchNextPage();
                              onComponentCursor?.(nextComponents);
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
                onTextFilter={(_name, value) => onEventTextFilter?.(value)}
                textFields={["component"]}
                onCursor={onEventCursor}
              />
            ) : null}
            {tab === "about" ? (
              <dl className="grid max-w-xl gap-4 rounded-2xl border border-app-edge bg-app-card p-4">
                <AboutRow
                  label="Website"
                  value={service.homepage_url}
                  href={service.homepage_url}
                />
                <AboutRow
                  label="Status page"
                  value={service.status_page?.url}
                  href={service.status_page?.url}
                />
                <AboutRow
                  label="Provider"
                  value={
                    meta.data?.enums?.status_page_provider?.[
                      service.status_page?.provider ?? ""
                    ]
                  }
                />
              </dl>
            ) : null}
          </>
        ) : null}
      </LoadState>
    </Shell>
  );
}

function AboutRow({
  label,
  value,
  href,
}: {
  label: string;
  value?: string | null;
  href?: string | null;
}) {
  return (
    <div>
      <dt className="text-xs text-app-ink-3">{label}</dt>
      <dd>
        {value && href ? (
          <a className="underline" href={href} target="_blank" rel="noreferrer">
            {value}
          </a>
        ) : (
          (value ?? "—")
        )}
      </dd>
    </div>
  );
}
