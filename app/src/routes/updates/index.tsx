import { createFileRoute } from "@tanstack/react-router";
import { Shell } from "@/components/Shell";
import { Tabs } from "@/components/Tabs";
import { updatesSearch } from "@/lib/search";
import { HOME_TABS } from "@/lib/tabs";

export const Route = createFileRoute("/updates/")({
  validateSearch: updatesSearch,
  component: Updates,
});

function Updates() {
  return (
    <Shell title="Home">
      <Tabs tabs={HOME_TABS} />
      <p>Updates arrives with the next plan.</p>
    </Shell>
  );
}
