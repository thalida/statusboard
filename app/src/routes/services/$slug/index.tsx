import { createFileRoute } from "@tanstack/react-router";
import { ServiceScreen } from "@/components/ServiceScreen";
import { serviceComponentsSearch } from "@/lib/search";

export const Route = createFileRoute("/services/$slug/")({
  validateSearch: serviceComponentsSearch,
  component: Screen,
});

function Screen() {
  const { slug } = Route.useParams();
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <ServiceScreen
      slug={slug}
      tab="components"
      componentParams={{
        status__severity: search.severity,
        tracking: search.tracking,
        cursor: search.cursor,
      }}
      eventParams={{}}
      onComponentCursor={(cursor) =>
        void navigate({ search: (old) => ({ ...old, cursor }) })
      }
      onComponentFilter={(name, value) =>
        void navigate({
          search: (old) => ({
            ...old,
            severity:
              name === "severity"
                ? value === undefined
                  ? undefined
                  : Number(value)
                : old.severity,
            tracking:
              name === "tracking"
                ? (value as ReturnType<
                    typeof serviceComponentsSearch
                  >["tracking"])
                : old.tracking,
            cursor: undefined,
          }),
        })
      }
      onEventFilter={() => {}}
    />
  );
}
