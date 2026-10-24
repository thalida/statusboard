import { createFileRoute } from "@tanstack/react-router";
import { homeSearch } from "@/lib/search";

export const Route = createFileRoute("/")({
  validateSearch: homeSearch,
  component: Home,
});

function Home() {
  const { tab } = Route.useSearch();
  return <main>{tab}</main>;
}
