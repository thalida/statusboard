import type { ReactNode } from "react";

export function LoadState({
  loading,
  error,
  empty,
  onRetry,
  children,
}: {
  loading: boolean;
  error: boolean;
  empty?: string;
  onRetry?: () => void;
  children?: ReactNode;
}) {
  if (loading) return <p role="status">Loading…</p>;
  if (error) {
    return (
      <div role="alert">
        <p>Can't reach statusboard.</p>
        {onRetry ? (
          <button type="button" onClick={onRetry} className="mt-3 underline">
            Retry
          </button>
        ) : null}
      </div>
    );
  }
  if (empty) return <p>{empty}</p>;
  return children;
}
