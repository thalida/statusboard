import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router";
import { render } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { queryClient } from "./routes/__root";
import { routeTree } from "./routeTree.gen";

/** Renders children inside a memory router.
 *
 * `Link` reads the router from context. A component holding one
 * cannot render in a test without this.
 */
export function routerWrapper({ children }: { children: ReactNode }) {
  const root = createRootRoute({ component: () => <>{children}</> });
  const router = createRouter({
    routeTree: root,
    history: createMemoryHistory({ initialEntries: ["/"] }),
  });
  return <RouterProvider router={router} />;
}

/** The router wrapper, with a query client around it.
 *
 * Each call builds its own client. A cache shared between tests lets
 * one test answer another's request.
 */
export function appWrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: {
      // A retry turns a 500 into a timeout rather than a failure.
      queries: { retry: false, staleTime: 0, gcTime: 0 },
    },
  });
  return (
    <QueryClientProvider client={client}>
      {routerWrapper({ children })}
    </QueryClientProvider>
  );
}

/** A handler answering 500 for one path, whatever the query string. */
export function errorHandlerFor(path: string) {
  return http.get(`*${path}`, () => new HttpResponse(null, { status: 500 }));
}

/** Renders the real route tree at one path.
 *
 * A screen reads its search parameters from its own route. Rendering
 * the component alone leaves `useSearch` empty, and the screen then
 * renders its default branch rather than the one under test.
 */
export function renderRoute(path: string) {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [path] }),
  });
  queryClient.clear();
  return render(<RouterProvider router={router} />);
}
