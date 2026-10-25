import { createFileRoute } from "@tanstack/react-router";
import { ComponentScreen } from "@/components/ComponentScreen";
import { componentComponentsSearch } from "@/lib/search";

export const Route = createFileRoute("/components/$id/")({
  validateSearch: componentComponentsSearch,
  component: Screen,
});

function Screen() {
  const { id } = Route.useParams();
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <ComponentScreen
      id={id}
      tab="components"
      severity={search.severity}
      tracking={search.tracking}
      cursor={search.cursor}
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
                    typeof componentComponentsSearch
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
