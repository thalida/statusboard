/** Which colour a severity carries.
 *
 * `/meta/` publishes the labels, so nothing here spells one. The
 * tone is the only thing a client decides, because it is a design
 * fact rather than a data one.
 */
export type Tone = "ok" | "warn" | "crit" | "maint" | "unknown";

export function severityTone(severity: number | undefined): Tone {
  switch (severity) {
    case 0:
    case 1:
      return "crit";
    case 2:
      return "warn";
    case 3:
      return "unknown";
    case 4:
      return "maint";
    case 5:
      return "ok";
    default:
      // A row with no status reads as unknown. The provider was
      // unreachable, which is severity 3's own meaning.
      return "unknown";
  }
}
