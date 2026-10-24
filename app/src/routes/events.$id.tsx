import { createFileRoute } from "@tanstack/react-router";
import { eventSearch } from "@/lib/search";

export const Route = createFileRoute("/events/$id")({
  validateSearch: eventSearch,
  component: Event,
});

function Event() {
  const { tab } = Route.useSearch();
  return <main>{tab}</main>;
}
