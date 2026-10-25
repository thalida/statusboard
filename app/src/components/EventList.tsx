import { Link } from "@tanstack/react-router";
import type { ServiceEvent } from "@/api/model";
import { useGetMeta } from "@/api/statusboard";
import { eventPhaseLabel } from "@/lib/meta";

export function EventList({
  events,
  next,
  loadingNext = false,
  onLoadMore,
}: {
  events: ServiceEvent[];
  next?: string | null;
  loadingNext?: boolean;
  onLoadMore?: () => void;
}) {
  const meta = useGetMeta(undefined, {
    query: { staleTime: Number.POSITIVE_INFINITY },
  });
  const enums = meta.data?.enums;
  return (
    <div>
      <ul className="grid gap-2">
        {events.map((event) => (
          <li key={event.id}>
            <Link
              to="/events/$id"
              params={{ id: event.id ?? "" }}
              className="block rounded-2xl border border-app-edge bg-app-card p-4"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <strong>{event.title}</strong>
                <span className="text-xs text-app-ink-3">
                  {enums?.event_kind?.[event.kind ?? ""]} ·{" "}
                  {eventPhaseLabel(enums, event.kind, event.phase)}
                </span>
              </div>
              <div className="mt-2 flex justify-between gap-2 text-sm text-app-ink-3">
                <span>{event.service?.name}</span>
                {event.starts_at ? (
                  <time dateTime={event.starts_at}>
                    {new Date(event.starts_at).toLocaleString()}
                  </time>
                ) : null}
              </div>
            </Link>
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
