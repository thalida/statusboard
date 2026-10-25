import { auth } from "./auth";
import { fetcher } from "./fetcher";

beforeEach(() => {
  auth.signOut();
  vi.restoreAllMocks();
});

test("a 401 refreshes once and retries", async () => {
  // A rotating access token expires mid-session. Without the retry
  // every screen would bounce a signed-in reader to the sign-in page.
  auth.signIn({ access: "old", refresh: "r" });
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      calls.push(url);
      if (url.endsWith("/auth/refresh/")) {
        return new Response(JSON.stringify({ access: "new", refresh: "r2" }), {
          status: 200,
        });
      }
      if (calls.filter((c) => c.endsWith("/me/")).length === 1) {
        return new Response("", { status: 401 });
      }
      return new Response(JSON.stringify({ email: "a@b.c" }), { status: 200 });
    }),
  );

  const body = await fetcher<{ email: string }>({ url: "/me/", method: "GET" });

  expect(body.email).toBe("a@b.c");
  expect(calls.filter((c) => c.endsWith("/auth/refresh/"))).toHaveLength(1);
  expect(auth.tokens()?.access).toBe("new");
});

test("a second 401 signs the reader out rather than looping", async () => {
  // A refresh token can be revoked or expired. Retrying forever
  // would hammer the API from every open tab.
  auth.signIn({ access: "old", refresh: "r" });
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response("", { status: 401 })),
  );

  await expect(fetcher({ url: "/me/", method: "GET" })).rejects.toThrow();
  expect(auth.tokens()).toBeNull();
});

test("a signed-out read carries no header", async () => {
  // The catalog is public. Sending an empty Authorization header
  // would make every anonymous read a 401.
  const seen: RequestInit[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url: string, init: RequestInit) => {
      seen.push(init);
      return new Response(JSON.stringify({}), { status: 200 });
    }),
  );

  await fetcher({ url: "/catalog/components/", method: "GET" });

  const headers = new Headers(seen[0]?.headers);
  expect(headers.has("Authorization")).toBe(false);
});

test("an accepted response can have no body", async () => {
  // The API accepts requests with 202 and sends no JSON body.
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(null, { status: 202 })),
  );

  await expect(
    fetcher({
      url: "/catalog/requests/",
      method: "POST",
      data: { url: "https://example.test" },
    }),
  ).resolves.toBeUndefined();
});
