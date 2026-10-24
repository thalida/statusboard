import { useGetMeta } from "@/api/statusboard";

/** The labels every screen renders, fetched once at app start.
 *
 * `/meta/` publishes the 0 to 5 severity map, so a label change ships
 * without touching a serializer or a screen.
 *
 * This is the one query cached forever. It is deployment-wide
 * configuration rather than status, so the no-stale-cache rule does
 * not apply to it.
 */
export function useSeverityLabels(): Record<string, string> {
  const { data } = useGetMeta(undefined, {
    query: {
      staleTime: Number.POSITIVE_INFINITY,
      gcTime: Number.POSITIVE_INFINITY,
    },
  });
  return data?.enums?.severity ?? {};
}
