import { createFileRoute } from "@tanstack/react-router";
import { ComponentScreen } from "@/components/ComponentScreen";
import { componentUpdatesSearch } from "@/lib/search";

export const Route = createFileRoute("/components/$id/updates")({
  validateSearch: componentUpdatesSearch,
  component: Screen,
});

function Screen() {
  const { id } = Route.useParams();
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <ComponentScreen
      id={id}
      tab="updates"
      eventParams={{
        kind: search.kind,
        phase: search.phase,
        cursor: search.cursor,
      }}
      onEventCursor={(cursor) =>
        void navigate({ search: (old) => ({ ...old, cursor }) })
      }
      onComponentFilter={() => {}}
      onEventFilter={(name, value) =>
        void navigate({
          search: (old) => ({ ...old, [name]: value, cursor: undefined }),
        })
      }
    />
  );
}
