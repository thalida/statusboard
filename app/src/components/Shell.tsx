import type { ReactNode } from "react";
import { Header } from "./Header";
import { Nav } from "./Nav";

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
      <Header title={title} checkedAt={checkedAt} />
      {/* pb-24 above clears the phone's bottom pill. Without it the
          last row sits under the nav. */}
      <main className="px-4 py-4">{children}</main>
      <Nav />
    </div>
  );
}
