import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/discover/add")({
  component: () => <main>add</main>,
});
