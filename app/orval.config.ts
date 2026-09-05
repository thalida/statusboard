import { defineConfig } from "orval";

export default defineConfig({
  statusboard: {
    // The contract, not the running server. A generator that needed
    // the API up could not run in CI or in the image build.
    input: "../docs/api/openapi.yaml",
    output: {
      target: "./src/api/statusboard.ts",
      schemas: "./src/api/model",
      client: "react-query",
      httpClient: "axios",
      mode: "split",
      mock: true,
      override: {
        // Every call goes through one place, so the token, the base
        // URL and the refresh live once.
        mutator: { path: "./src/lib/fetcher.ts", name: "fetcher" },
        query: { useSuspenseQuery: false },
      },
    },
    hooks: { afterAllFilesWrite: "node_modules/.bin/biome check --write" },
  },
});
