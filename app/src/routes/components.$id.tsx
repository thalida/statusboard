import { createFileRoute } from "@tanstack/react-router";
import { componentSearch } from "@/lib/search";

export const Route = createFileRoute("/components/$id")({
  validateSearch: componentSearch,
  component: ComponentScreen,
});

function ComponentScreen() {
  const { tab } = Route.useSearch();
  return <main>{tab}</main>;
}
