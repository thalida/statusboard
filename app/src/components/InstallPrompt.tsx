import { useEffect, useRef, useState } from "react";

const VISITS = "statusboard.visits";
const DISMISSED = "statusboard.install-dismissed";

type InstallEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

export function InstallPrompt() {
  const visits = useRef(0);
  const counted = useRef(false);
  const [installEvent, setInstallEvent] = useState<InstallEvent>();
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (!counted.current) {
      counted.current = true;
      visits.current = Number(localStorage.getItem(VISITS) ?? 0) + 1;
      localStorage.setItem(VISITS, String(visits.current));
      setDismissed(localStorage.getItem(DISMISSED) === "true");
    }
    const capture = (event: Event) => {
      event.preventDefault();
      setInstallEvent(event as InstallEvent);
    };
    window.addEventListener("beforeinstallprompt", capture);
    return () => window.removeEventListener("beforeinstallprompt", capture);
  }, []);

  if (!installEvent || visits.current < 3 || dismissed) return null;

  return (
    <aside
      aria-label="Install Statusboard"
      className="fixed inset-x-4 bottom-24 z-50 mx-auto flex max-w-xl items-center justify-between gap-3 rounded-2xl border border-app-edge bg-app-card p-4 shadow-lg md:bottom-4"
    >
      <p>Install Statusboard for quick access.</p>
      <div className="flex shrink-0 gap-2">
        <button
          type="button"
          onClick={async () => {
            await installEvent.prompt();
            const choice = await installEvent.userChoice;
            if (choice.outcome === "accepted") {
              localStorage.setItem(DISMISSED, "true");
              setDismissed(true);
            }
            setInstallEvent(undefined);
          }}
          className="rounded-full bg-app-nav px-3 py-2 text-app-nav-ink"
        >
          Install
        </button>
        <button
          type="button"
          onClick={() => {
            localStorage.setItem(DISMISSED, "true");
            setDismissed(true);
          }}
          className="rounded-full border border-app-edge px-3 py-2"
        >
          Dismiss
        </button>
      </div>
    </aside>
  );
}
