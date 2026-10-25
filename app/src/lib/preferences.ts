const SUGGESTED_KEY = "statusboard.suggested-services";
const listeners = new Set<() => void>();

function notify() {
  for (const listener of listeners) listener();
}

export const suggestedServices = {
  read(): boolean {
    return localStorage.getItem(SUGGESTED_KEY) !== "false";
  },

  write(enabled: boolean) {
    localStorage.setItem(SUGGESTED_KEY, String(enabled));
    notify();
  },

  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};
