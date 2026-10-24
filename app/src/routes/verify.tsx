import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/verify")({
  validateSearch: (raw: Record<string, unknown>) => ({
    token: String(raw.token ?? ""),
  }),
  component: () => <main>verify</main>,
});
