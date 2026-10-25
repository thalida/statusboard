import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState, useSyncExternalStore } from "react";
import { useDeleteMe, useGetMe, usePostAuthLogout } from "@/api/statusboard";
import { LoadState } from "@/components/LoadState";
import { Shell } from "@/components/Shell";
import { auth } from "@/lib/auth";
import { suggestedServices } from "@/lib/preferences";

export const Route = createFileRoute("/settings/")({ component: Settings });

function Settings() {
  const navigate = useNavigate();
  const signedIn = useSyncExternalStore(
    auth.subscribe,
    () => auth.tokens() !== null,
    () => false,
  );
  const me = useGetMe(undefined, { query: { enabled: signedIn } });
  const logout = usePostAuthLogout();
  const removeAccount = useDeleteMe({
    mutation: {
      onSuccess: () => {
        auth.signOut();
        void navigate({ to: "/" });
      },
    },
  });
  const [confirmDelete, setConfirmDelete] = useState(false);
  const showSuggested = useSyncExternalStore(
    suggestedServices.subscribe,
    suggestedServices.read,
    () => true,
  );

  function signOut() {
    logout.mutate(undefined, {
      onSettled: () => {
        auth.signOut();
        void navigate({ to: "/" });
      },
    });
  }

  return (
    <Shell title="Settings">
      {!signedIn ? (
        <p>
          <Link className="underline" to="/signin">
            Sign in
          </Link>{" "}
          to manage your account.
        </p>
      ) : (
        <LoadState
          loading={me.isLoading}
          error={me.isError}
          onRetry={() => void me.refetch()}
        >
          {me.data ? (
            <div className="grid max-w-xl gap-4">
              <section className="rounded-2xl border border-app-edge bg-app-card p-4">
                <h2 className="font-semibold">Suggested services</h2>
                <p className="mt-2 text-sm text-app-ink-3">
                  Show recommended components when Discover has no search.
                </p>
                <label className="mt-3 flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={showSuggested}
                    onChange={(event) =>
                      suggestedServices.write(event.target.checked)
                    }
                  />
                  Show suggestions in Discover
                </label>
              </section>
              <section className="rounded-2xl border border-app-edge bg-app-card p-4">
                <h2 className="font-semibold">Account</h2>
                <p className="mt-2">{me.data.email}</p>
                <button
                  type="button"
                  onClick={signOut}
                  className="mt-4 rounded-full border border-app-edge px-4 py-2"
                  disabled={logout.isPending}
                >
                  Sign out
                </button>
                {!confirmDelete ? (
                  <button
                    type="button"
                    onClick={() => setConfirmDelete(true)}
                    className="ml-2 mt-4 rounded-full border border-crit/30 px-4 py-2 text-crit"
                  >
                    Delete account
                  </button>
                ) : (
                  <div role="alert" className="mt-4 rounded-xl bg-app-chip p-3">
                    <p>Delete your account and stop tracking its components?</p>
                    <button
                      type="button"
                      onClick={() => removeAccount.mutate()}
                      disabled={removeAccount.isPending}
                      className="mt-3 rounded-full bg-crit px-4 py-2 text-white"
                    >
                      Confirm deletion
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmDelete(false)}
                      className="ml-2 rounded-full border border-app-edge px-4 py-2"
                    >
                      Keep account
                    </button>
                  </div>
                )}
                {removeAccount.isError ? (
                  <p role="alert" className="mt-3">
                    Account deletion failed. Try again.
                  </p>
                ) : null}
              </section>
            </div>
          ) : null}
        </LoadState>
      )}
    </Shell>
  );
}
