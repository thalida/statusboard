import { defineConfig } from "orval";

export default defineConfig({
  statusboard: {
    // The contract, not the running server. A generator that needed
    // the API up could not run in CI or in the image build.
    input: {
      target: "../docs/api/openapi.yaml",
      // A handful of parameter descriptions carry an unescaped comma in
      // flow-style YAML, which splits into a bogus extra property. That
      // fails strict spec validation. No name or type orval reads is
      // affected, so validation is off here rather than the contract.
      unsafeDisableValidation: true,
      override: {
        // `EventRef` is `type: object, nullable: true`. Orval emits
        // `export interface EventRef {...} | null`, which is not valid
        // TypeScript. The OpenAPI 3.1 form of the same schema generates
        // correctly, so this rewrites the parsed spec in memory. The
        // contract on disk is untouched.
        transformer: (spec) => {
          const eventRef = spec.components?.schemas?.EventRef;
          if (eventRef && "nullable" in eventRef) {
            delete eventRef.nullable;
            eventRef.type = ["object", "null"];
          }
          return spec;
        },
      },
    },
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
