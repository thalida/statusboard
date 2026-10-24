import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createRootRoute, Outlet } from "@tanstack/react-router";
import { Shell } from "@/components/Shell";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // There is no offline mode. A cached board would answer
      // yesterday's question, which is worse than saying nothing.
      staleTime: 0,
      gcTime: 0,
      retry: 1,
      refetchOnWindowFocus: true,
    },
  },
});

export const Route = createRootRoute({
  component: () => (
    <QueryClientProvider client={queryClient}>
      <Outlet />
    </QueryClientProvider>
  ),
  notFoundComponent: NotFound,
});

/** Every URL no route matches.
 *
 * On the root, so one screen covers them all: a typo, a dead link,
 * and a parent path like `/services` that names no page. It wears the
 * shell, because the way back is the nav.
 */
function NotFound() {
  return (
    <Shell title="Not found">
      <p>That page doesn't exist.</p>
    </Shell>
  );
}
