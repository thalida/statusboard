type Option = { value: string; label: string };

export function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value?: string;
  options: Option[];
  onChange: (value?: string) => void;
}) {
  return (
    <label className="grid gap-1 text-xs text-app-ink-2">
      {label}
      <select
        aria-label={label}
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value || undefined)}
        className="rounded-xl border border-app-edge bg-app-card px-3 py-2 text-sm text-app-ink"
      >
        <option value="">All</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
