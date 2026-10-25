import { createFileRoute } from "@tanstack/react-router";
import { EventScreen } from "@/components/EventScreen";

export const Route = createFileRoute("/events/$id/about")({
  component: () => <EventScreen id={Route.useParams().id} tab="about" />,
});
