import { createFileRoute } from "@tanstack/react-router";
import { Shell } from "@/components/Shell";
import { Tabs } from "@/components/Tabs";
import { serviceComponentsSearch } from "@/lib/search";
import { SERVICE_TABS } from "@/lib/tabs";

export const Route = createFileRoute("/services/$slug/")({
  validateSearch: serviceComponentsSearch,
  component: Screen,
});

function Screen() {
  const { slug } = Route.useParams();
  return (
    <Shell title="Service">
      <Tabs tabs={SERVICE_TABS(slug)} />
      <p>Components arrives with the next plan.</p>
    </Shell>
  );
}
