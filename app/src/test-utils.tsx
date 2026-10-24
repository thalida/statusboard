import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router";
import type { ReactNode } from "react";

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
