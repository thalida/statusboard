import { createFileRoute } from "@tanstack/react-router";
import { Shell } from "@/components/Shell";
import { Tabs } from "@/components/Tabs";
import { componentUpdatesSearch } from "@/lib/search";
import { COMPONENT_TABS } from "@/lib/tabs";

export const Route = createFileRoute("/components/$id/updates")({
  validateSearch: componentUpdatesSearch,
  component: Screen,
});

function Screen() {
  const { id } = Route.useParams();
  return (
    <Shell title="Component">
      <Tabs tabs={COMPONENT_TABS(id)} />
      <p>Updates arrives with the next plan.</p>
    </Shell>
  );
}
