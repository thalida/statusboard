import { useInfiniteQuery } from "@tanstack/react-query";
import type {
  GetCatalogComponentsParams,
  GetDashboardsUuidComponentsParams,
  GetEventsParams,
} from "@/api/model";
import {
  getCatalogComponents,
  getDashboardsUuidComponents,
  getEvents,
  getEventsUuidUpdates,
} from "@/api/statusboard";

export function useComponentPages(
  params: GetCatalogComponentsParams,
  enabled = true,
) {
  const { cursor, ...filters } = params;
  return useInfiniteQuery({
    queryKey: ["/catalog/components/", filters],
    initialPageParam: cursor,
    queryFn: ({ pageParam, signal }) =>
      getCatalogComponents({ ...filters, cursor: pageParam }, signal),
    getNextPageParam: (page) => page.next ?? undefined,
    enabled,
  });
}

export function useBoardPages(
  id: string,
  params: GetDashboardsUuidComponentsParams,
  enabled = true,
) {
  const { cursor, ...filters } = params;
  return useInfiniteQuery({
    queryKey: ["/dashboards/", id, "components/", filters],
    initialPageParam: cursor,
    queryFn: ({ pageParam, signal }) =>
      getDashboardsUuidComponents(
        id,
        { ...filters, cursor: pageParam },
        signal,
      ),
    getNextPageParam: (page) => page.next ?? undefined,
    enabled: Boolean(id) && enabled,
  });
}

export function useEventPages(params: GetEventsParams, enabled = true) {
  const { cursor, ...filters } = params;
  return useInfiniteQuery({
    queryKey: ["/events/", filters],
    initialPageParam: cursor,
    queryFn: ({ pageParam, signal }) =>
      getEvents({ ...filters, cursor: pageParam }, signal),
    getNextPageParam: (page) => page.next ?? undefined,
    enabled,
  });
}

export function useEventUpdatePages(
  id: string,
  cursor?: string,
  enabled = true,
) {
  return useInfiniteQuery({
    queryKey: ["/events/", id, "updates/"],
    initialPageParam: cursor,
    queryFn: ({ pageParam, signal }) =>
      getEventsUuidUpdates(id, { cursor: pageParam }, signal),
    getNextPageParam: (page) => page.next ?? undefined,
    enabled,
  });
}
