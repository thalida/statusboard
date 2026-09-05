import type { TokenPair } from "@/api/model";

const KEY = "statusboard.refresh";

/** The pair, and who to tell when it changes.
 *
 * The access token stays in memory. It is the credential worth
 * stealing, and it lives fifteen minutes. The refresh token has to
 * survive a reload, so it is in local storage, which a strict CSP is
 * what makes acceptable.
 */
let access: string | undefined;
const listeners = new Set<() => void>();

function announce() {
  for (const listener of listeners) listener();
}

export const auth = {
  tokens(): { access?: string; refresh: string } | null {
    const refresh = localStorage.getItem(KEY);
    return refresh ? { access, refresh } : null;
  },

  signIn(pair: TokenPair) {
    // No schema in the contract is required, so refresh can be
    // missing. A pair without one cannot start a session.
    if (!pair.refresh)
      throw new Error("signIn: the pair carries no refresh token");
    access = pair.access;
    localStorage.setItem(KEY, pair.refresh);
    announce();
  },

  signOut() {
    access = undefined;
    localStorage.removeItem(KEY);
    announce();
  },

  /** Drop the access token and keep the session. For tests, and for a
   * reload, which loses it anyway. */
  forgetAccessToken() {
    access = undefined;
  },

  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};
