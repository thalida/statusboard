import { createFileRoute } from "@tanstack/react-router";
import { discoverSearch } from "@/lib/search";

export const Route = createFileRoute("/discover/")({
  validateSearch: discoverSearch,
  component: Discover,
});

function Discover() {
  const { tab } = Route.useSearch();
  return <main>{tab}</main>;
}
