import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { usePostAuthMagicLink } from "@/api/statusboard";
import { Shell } from "@/components/Shell";

export const Route = createFileRoute("/signin")({ component: SignIn });

function SignIn() {
  const [email, setEmail] = useState("");
  const request = usePostAuthMagicLink();

  // Always 202, even for an unknown address. So there is one screen
  // after this, and it does not say whether the account exists.
  if (request.isSuccess) {
    return (
      <Shell title="Check your email">
        <p>If that address has an account, a sign-in link is on its way.</p>
      </Shell>
    );
  }

  return (
    <Shell title="Sign in">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          request.mutate({ data: { email } });
        }}
        className="grid max-w-sm gap-3"
      >
        <label htmlFor="email">Keep track of what matters</label>
        <input
          id="email"
          type="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@example.com"
          className="rounded-xl border border-app-edge bg-app-card px-3 py-2"
        />
        <button
          type="submit"
          disabled={request.isPending}
          className="rounded-full bg-app-nav px-4 py-2 text-app-nav-ink"
        >
          Email me a sign-in link
        </button>
        <p className="text-app-ink-3 text-xs">
          No password. We'll bring you back to where you were.
        </p>
      </form>
    </Shell>
  );
}
