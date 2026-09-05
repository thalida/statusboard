import { auth } from "./auth";

beforeEach(() => {
  localStorage.clear();
  auth.signOut();
});

test("the access token never reaches local storage", () => {
  // It is the credential a script would want. Only the refresh
  // survives a reload, and only because a session has to.
  auth.signIn({ access: "a", refresh: "r" });
  expect(JSON.stringify(localStorage)).not.toContain("a");
  expect(JSON.stringify(localStorage)).toContain("r");
});

test("a reload keeps the session and loses the access token", () => {
  // The refresh is what a reload spends to get a new access token.
  auth.signIn({ access: "a", refresh: "r" });
  auth.forgetAccessToken();
  expect(auth.tokens()?.access).toBeUndefined();
  expect(auth.tokens()?.refresh).toBe("r");
});

test("signing out clears both", () => {
  auth.signIn({ access: "a", refresh: "r" });
  auth.signOut();
  expect(auth.tokens()).toBeNull();
  expect(localStorage.length).toBe(0);
});
