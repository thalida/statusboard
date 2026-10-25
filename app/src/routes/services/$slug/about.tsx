import { createFileRoute } from "@tanstack/react-router";
import { ServiceScreen } from "@/components/ServiceScreen";

export const Route = createFileRoute("/services/$slug/about")({
  component: Screen,
});

function Screen() {
  const { slug } = Route.useParams();
  return (
    <ServiceScreen
      slug={slug}
      tab="about"
      componentParams={{}}
      eventParams={{}}
      onComponentFilter={() => {}}
      onEventFilter={() => {}}
    />
  );
}
