import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useQueryClient } from "@tanstack/react-query";
import { MoreVertical, Plus } from "lucide-react";
import type { Component } from "@/api/model";
import {
  useDeleteDashboardsUuidComponentsComponentId,
  useGetMe,
  usePostDashboardsUuidComponents,
} from "@/api/statusboard";
import { Row } from "@/components/Row";
import { auth } from "@/lib/auth";
import { useSeverityLabels } from "@/lib/meta";

export function ComponentList({
  components,
  next,
  loadingNext = false,
  onLoadMore,
}: {
  components: Component[];
  next?: string | null;
  loadingNext?: boolean;
  onLoadMore?: () => void;
}) {
  const track = useTrackComponent();
  const labels = useSeverityLabels();
  return (
    <div>
      <ul className="grid gap-2 md:grid-cols-[repeat(auto-fill,minmax(212px,1fr))]">
        {components.map((component) => (
          <li key={component.id} className="min-w-0">
            <Row
              component={component}
              label={labels[String(component.status?.severity)]}
              showMark
              onTrack={track && component.id ? track : undefined}
            />
          </li>
        ))}
      </ul>
      {next && onLoadMore ? (
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

export function TrackComponentButton({ component }: { component: Component }) {
  const track = useTrackComponent();
  if (!track || !component.id) return null;
  if (component.is_tracked) {
    return (
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <button
            type="button"
            aria-label="Service tracking menu"
            className="rounded-full border border-app-edge p-2"
          >
            <MoreVertical size={16} />
          </button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            align="end"
            className="z-50 rounded-xl border border-app-edge bg-app-card p-1 shadow-lg"
          >
            <DropdownMenu.Item
              onSelect={() => track(component)}
              className="cursor-pointer rounded-lg px-3 py-2 text-sm outline-none focus:bg-app-chip"
            >
              Stop tracking service
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
    );
  }
  return (
    <button
      type="button"
      aria-label="Track service"
      onClick={() => track(component)}
      className="rounded-full border border-app-edge p-2"
    >
      <Plus size={16} />
    </button>
  );
}

function useTrackComponent() {
  const queryClient = useQueryClient();
  const signedIn = auth.tokens() !== null;
  const me = useGetMe(undefined, { query: { enabled: signedIn } });
  const dashboard = me.data?.default_dashboard_id;
  const add = usePostDashboardsUuidComponents({
    mutation: { onSuccess: () => queryClient.invalidateQueries() },
  });
  const remove = useDeleteDashboardsUuidComponentsComponentId({
    mutation: { onSuccess: () => queryClient.invalidateQueries() },
  });

  if (!dashboard) return undefined;
  return (component: Component) => {
    if (!component.id) return;
    if (component.is_tracked) {
      remove.mutate({ uuid: dashboard, componentId: component.id });
    } else {
      add.mutate({
        uuid: dashboard,
        data: { component_id: component.id },
      });
    }
  };
}
