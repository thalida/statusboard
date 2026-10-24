import { createFileRoute } from "@tanstack/react-router";
import { Shell } from "@/components/Shell";
import { discoverSearch } from "@/lib/search";

export const Route = createFileRoute("/discover/")({
  validateSearch: discoverSearch,
  component: () => (
    <Shell title="Discover">
      <p>Discover arrives with the next plan.</p>
    </Shell>
  ),
});
