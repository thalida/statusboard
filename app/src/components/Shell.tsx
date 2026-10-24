import type { ReactNode } from "react";
import { Header } from "./Header";

export function Shell({
  title,
  checkedAt,
  children,
}: {
  title: string;
  checkedAt?: string | null;
  children: ReactNode;
}) {
  return (
    <div className="mx-auto min-h-dvh max-w-5xl pb-24 md:pb-8">
      {/* pb-24 clears the phone's bottom pill. Without it the last
          row sits under the nav. */}
      <Header title={title} checkedAt={checkedAt} />
      <main className="px-4 py-4">{children}</main>
    </div>
  );
}
