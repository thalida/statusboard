import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useRef } from "react";
import { usePostAuthVerify } from "@/api/statusboard";
import { Shell } from "@/components/Shell";
import { auth } from "@/lib/auth";

export const Route = createFileRoute("/verify/")({
  validateSearch: (raw: Record<string, unknown>) => ({
    token: String(raw.token ?? ""),
  }),
  component: Verify,
});

function Verify() {
  const { token } = Route.useSearch();
  const navigate = useNavigate();
  const spent = useRef(false);
  const verify = usePostAuthVerify({
    mutation: {
      // A link is single use. A retry would spend a token the first
      // attempt already consumed.
      retry: false,
      onSuccess: (pair) => {
        auth.signIn(pair);
        navigate({ to: "/" });
      },
    },
  });

  // The mutation is held in a ref so the effect depends on the token
  // alone. A new object every render would re-run it.
  const mutate = useRef(verify.mutate);
  mutate.current = verify.mutate;

  useEffect(() => {
    // The guard, not the dependency array, is what makes this run
    // once. StrictMode invokes an effect twice in development.
    if (!token || spent.current) return;
    spent.current = true;
    mutate.current({ data: { token } });
  }, [token]);

  if (!token) {
    return (
      <Shell title="Sign in">
        <p>That link is missing its token.</p>
      </Shell>
    );
  }
  if (verify.isError) {
    return (
      <Shell title="Sign in">
        <p>That link is no longer valid. Ask for another.</p>
      </Shell>
    );
  }
  return (
    <Shell title="Signing you in">
      <p>One moment.</p>
    </Shell>
  );
}
