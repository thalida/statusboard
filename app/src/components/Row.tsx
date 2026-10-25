import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Link } from "@tanstack/react-router";
import { MoreVertical, Plus } from "lucide-react";
import type { Component } from "@/api/model";
import { since } from "@/lib/duration";
import { severityTone, type Tone } from "@/lib/severity";

/** The classes each tone wears.
 *
 * Tailwind reads class names as literals. A template string like
 * `bg-${tone}/15` emits nothing, so every class is spelled here.
 */
const TONE: Record<Tone, { edge: string; fill: string; text: string }> = {
  ok: { edge: "border-app-edge", fill: "", text: "text-ok" },
  warn: { edge: "border-warn/30", fill: "bg-warn/15", text: "text-warn" },
  crit: { edge: "border-crit/30", fill: "bg-crit/15", text: "text-crit" },
  maint: { edge: "border-maint/30", fill: "bg-maint/15", text: "text-maint" },
  unknown: {
    edge: "border-unknown/30",
    fill: "bg-unknown/15",
    text: "text-unknown",
  },
};

/** One component, on every list that has them.
 *
 * The row carries its state as a tint and a coloured edge. There is
 * no dot: a dot that appeared on operational and nowhere else was the
 * odd one out.
 */
export function Row({
  component,
  label,
  showMark = false,
  onTrack,
}: {
  component: Component;
  label?: string;
  showMark?: boolean;
  onTrack?: (component: Component) => void;
}) {
  const tone = severityTone(component.status?.severity);
  const tinted = tone !== "ok";
  const classes = TONE[tone];
  // A rollup is its service. Its own page would be the same list
  // under a different header.
  const href = component.is_overall
    ? `/services/${component.service?.slug}`
    : `/components/${component.id}`;
  // The only third line, and only when the component sits under
  // another. A count or a tracking line described the row, not it.
  const parent = component.path?.at(-1)?.name;

  return (
    <div
      data-tone={tone}
      data-tinted={tinted}
      className={`relative min-w-0 rounded-2xl border bg-app-card p-3 ${classes.edge} ${classes.fill}`}
    >
      <Link to={href} className="block">
        <div className="flex items-start gap-2">
          {showMark ? <Mark component={component} /> : null}
          <div className="min-w-0 flex-1">
            <div className="truncate font-medium">{component.name}</div>
            <div className={`text-sm ${classes.text}`}>
              {label ?? "—"}
              {component.status?.started_at ? (
                <span className="ml-2 font-mono text-app-ink-3">
                  {since(component.status.started_at)}
                </span>
              ) : null}
            </div>
            {parent ? (
              <div className="truncate text-xs text-app-ink-3">{parent}</div>
            ) : null}
          </div>
        </div>
      </Link>

      {onTrack && component.is_tracked ? (
        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button
              type="button"
              aria-label="Row menu"
              className="absolute right-3 bottom-3 rounded-full border border-app-edge p-1"
            >
              <MoreVertical size={16} />
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              align="end"
              className="z-50 rounded-xl border border-app-edge bg-app-card p-1 shadow-lg"
            >
              <DropdownMenu.Item
                onSelect={() => onTrack(component)}
                className="cursor-pointer rounded-lg px-3 py-2 text-sm outline-none focus:bg-app-chip"
              >
                Stop tracking
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      ) : null}
      {onTrack && !component.is_tracked ? (
        <button
          type="button"
          aria-label="Track"
          onClick={() => onTrack(component)}
          className="absolute right-3 bottom-3 rounded-full border border-app-edge p-1"
        >
          <Plus size={16} />
        </button>
      ) : null}
    </div>
  );
}

function Mark({ component }: { component: Component }) {
  const logo = component.service?.logo;
  const name = component.service?.name ?? "";
  return logo ? (
    <img src={logo} alt="" className="size-6 rounded-full" />
  ) : (
    <span className="grid size-6 place-items-center rounded-full bg-app-chip text-xs">
      {name.charAt(0)}
    </span>
  );
}
