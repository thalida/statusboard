import { createFileRoute } from "@tanstack/react-router";
import { Shell } from "@/components/Shell";
import { Tabs } from "@/components/Tabs";
import { componentComponentsSearch } from "@/lib/search";
import { COMPONENT_TABS } from "@/lib/tabs";

export const Route = createFileRoute("/components/$id/")({
  validateSearch: componentComponentsSearch,
  component: Screen,
});

function Screen() {
  const { id } = Route.useParams();
  return (
    <Shell title="Component">
      <Tabs tabs={COMPONENT_TABS(id)} />
      <p>Components arrives with the next plan.</p>
    </Shell>
  );
}
