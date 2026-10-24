/** What the deployment told the page at start.
 *
 * A Vite build inlines a VITE_ value, which would make the image
 * environment-specific. The entrypoint writes `config.js` instead, so
 * one image answers anywhere. See app/entrypoint.sh.
 */
declare global {
  interface Window {
    STATUSBOARD_CONFIG?: { apiUrl?: string };
  }
}

function apiUrl(): string {
  // config.js wins whenever it exists, which is every deployment.
  // VITE_API_URL is development only. bin/worktree-env.py reserves a
  // port the entrypoint cannot know, and the value never reaches the
  // image. localhost:8000 is the last resort, for a bare `vite dev`.
  const written =
    window.STATUSBOARD_CONFIG?.apiUrl ??
    import.meta.env.VITE_API_URL ??
    "http://localhost:8000";
  return written.replace(/\/$/, "");
}

export const config = { apiUrl: apiUrl() };
