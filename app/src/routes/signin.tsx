import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/signin")({
  component: () => <main>signin</main>,
});
