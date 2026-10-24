import { createFileRoute } from "@tanstack/react-router";
import { serviceSearch } from "@/lib/search";

export const Route = createFileRoute("/services/$slug")({
  validateSearch: serviceSearch,
  component: Service,
});

function Service() {
  const { tab } = Route.useSearch();
  return <main>{tab}</main>;
}
