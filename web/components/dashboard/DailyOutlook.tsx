import { DailyOutlookData } from "@/lib/types";

export function DailyOutlook({ data }: { data: DailyOutlookData }) {
  const border =
    data.tone === "warning"
      ? "border-l-tone-warning"
      : "border-l-tone-success";

  return (
    <div
      className={`rounded-card border border-surface-border bg-surface p-4 shadow-card border-l-4 ${border}`}
    >
      <div className="text-xs font-medium uppercase tracking-wide text-ink-faint mb-2">
        Сегодня
      </div>
      <p className="text-sm text-ink leading-relaxed">{data.text}</p>
    </div>
  );
}
