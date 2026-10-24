import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createRootRoute, Outlet } from "@tanstack/react-router";

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
});
