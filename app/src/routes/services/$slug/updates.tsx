import { createFileRoute } from "@tanstack/react-router";
import { ServiceScreen } from "@/components/ServiceScreen";
import { serviceUpdatesSearch } from "@/lib/search";

export const Route = createFileRoute("/services/$slug/updates")({
  validateSearch: serviceUpdatesSearch,
  component: Screen,
});

function Screen() {
  const { slug } = Route.useParams();
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <ServiceScreen
      slug={slug}
      tab="updates"
      componentParams={{}}
      eventParams={{
        service: slug,
        component: search.component,
        kind: search.kind,
        phase: search.phase,
        cursor: search.cursor,
      }}
      onEventCursor={(cursor) =>
        void navigate({ search: (old) => ({ ...old, cursor }) })
      }
      onEventTextFilter={(value) =>
        void navigate({
          search: (old) => ({ ...old, component: value, cursor: undefined }),
        })
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
