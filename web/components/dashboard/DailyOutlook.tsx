import { DailyOutlookData } from "@/lib/types";

const TONE_BORDER: Record<DailyOutlookData["tone"], string> = {
  danger: "border-l-tone-danger",
  warning: "border-l-tone-warning",
  neutral: "border-l-tone-neutral",
  success: "border-l-tone-success",
};

export function DailyOutlook({ data }: { data: DailyOutlookData }) {
  const border = TONE_BORDER[data.tone] ?? "border-l-tone-neutral";

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
