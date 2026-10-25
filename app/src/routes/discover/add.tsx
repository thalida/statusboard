import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import {
  usePostCatalogImport,
  usePostCatalogRequests,
} from "@/api/statusboard";
import { Shell } from "@/components/Shell";

export const Route = createFileRoute("/discover/add")({ component: AddByUrl });

function AddByUrl() {
  const [url, setUrl] = useState("");
  const [message, setMessage] = useState<"added" | "requested" | "error">();
  const [service, setService] = useState<{ slug?: string; name?: string }>();
  const add = usePostCatalogImport();
  const request = usePostCatalogRequests();

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(undefined);
    setService(undefined);
    try {
      const imported = await add.mutateAsync({
        data: { status_page_url: url },
      });
      setService(imported);
      setMessage("added");
    } catch (error) {
      const message =
        error && typeof error === "object" && "message" in error
          ? String(error.message)
          : "";
      if (message.includes("404")) {
        try {
          await request.mutateAsync({ data: { url } });
          setMessage("requested");
        } catch {
          setMessage("error");
        }
      } else {
        setMessage("error");
      }
    }
  }

  return (
    <Shell title="Add by URL">
      <p className="mb-4 max-w-xl text-app-ink-2">
        Add a service status page to the catalog.
      </p>
      <form onSubmit={submit} className="grid max-w-xl gap-3">
        <label htmlFor="status-page-url">Status page URL</label>
        <input
          id="status-page-url"
          type="url"
          required
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          placeholder="https://status.example.com"
          className="rounded-xl border border-app-edge bg-app-card px-3 py-2"
        />
        <button
          type="submit"
          disabled={add.isPending || request.isPending}
          className="w-fit rounded-full bg-app-nav px-4 py-2 text-app-nav-ink"
        >
          Add status page
        </button>
      </form>
      {message === "added" ? (
        <p role="status" className="mt-4">
          {service?.slug ? (
            <Link
              className="underline"
              to="/services/$slug"
              params={{ slug: service.slug }}
            >
              {service.name ?? "Service"} is in the catalog.
            </Link>
          ) : (
            "The service is in the catalog."
          )}
        </p>
      ) : null}
      {message === "requested" ? (
        <p role="status" className="mt-4">
          Thanks. We’ll review that status page.
        </p>
      ) : null}
      {message === "error" ? (
        <p role="alert" className="mt-4">
          We couldn’t add that URL. Check it and try again.
        </p>
      ) : null}
    </Shell>
  );
}
