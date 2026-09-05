// Task 4 fills this in. It throws so nothing can call the API before then.
export async function fetcher<T>(config: {
  url: string;
  method: string;
  params?: unknown;
  data?: unknown;
  // Orval sets this itself on a JSON request body. Task 4's real
  // fetcher merges in the auth header too.
  headers?: Record<string, string>;
  signal?: AbortSignal;
}): Promise<T> {
  throw new Error(
    `fetcher is not implemented yet: ${config.method} ${config.url}`,
  );
}
