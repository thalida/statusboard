import { createFileRoute } from "@tanstack/react-router";
import { Shell } from "@/components/Shell";
import { Tabs } from "@/components/Tabs";
import { EVENT_TABS } from "@/lib/tabs";

export const Route = createFileRoute("/events/$id/affects")({
  component: Screen,
});

function Screen() {
  const { id } = Route.useParams();
  return (
    <Shell title="Event">
      <Tabs tabs={EVENT_TABS(id)} />
      <p>Affects arrives with the next plan.</p>
    </Shell>
  );
}
