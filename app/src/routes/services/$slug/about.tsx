import { createFileRoute } from "@tanstack/react-router";
import { Shell } from "@/components/Shell";
import { Tabs } from "@/components/Tabs";
import { SERVICE_TABS } from "@/lib/tabs";

export const Route = createFileRoute("/services/$slug/about")({
  component: Screen,
});

function Screen() {
  const { slug } = Route.useParams();
  return (
    <Shell title="Service">
      <Tabs tabs={SERVICE_TABS(slug)} />
      <p>About arrives with the next plan.</p>
    </Shell>
  );
}
