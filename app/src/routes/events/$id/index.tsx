import { createFileRoute } from "@tanstack/react-router";
import { EventScreen } from "@/components/EventScreen";
import { eventListSearch } from "@/lib/search";

export const Route = createFileRoute("/events/$id/")({
  validateSearch: eventListSearch,
  component: Screen,
});

function Screen() {
  const { id } = Route.useParams();
  const { cursor } = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <EventScreen
      id={id}
      tab="timeline"
      cursor={cursor}
      onCursor={(cursor) =>
        void navigate({ search: (old) => ({ ...old, cursor }) })
      }
    />
  );
}
