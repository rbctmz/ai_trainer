import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { SleepSummary } from "@/lib/types";

export function SleepWidget({ className = "" }: { className?: string }) {
  const { data, isLoading } = useSWR<SleepSummary>(
    "/api/sleep/summary",
    fetcher,
  );

  if (isLoading) {
    return (
      <div className={`rounded-card border border-surface-border bg-surface p-4 shadow-card animate-pulse h-24 ${className}`} />
    );
  }

  const latest = data?.latest;
  const hours = latest?.hours;
  const score = latest?.score;

  const hoursColor =
    hours == null ? "text-ink-faint"
    : hours >= 7   ? "text-tone-success"
    : hours >= 5.5 ? "text-tone-warning"
    :                "text-tone-danger";

  return (
    <div className={`rounded-card border border-surface-border bg-surface p-4 shadow-card ${className}`}>
      <div className="text-xs font-medium uppercase tracking-wide text-ink-faint mb-1">
        Сон
      </div>
      <div className="flex items-end gap-3">
        <span className={`text-2xl font-bold ${hoursColor}`}>
          {hours != null ? `${hours} ч` : "—"}
        </span>
        {score != null && (
          <span className="text-sm text-ink-soft mb-0.5">оценка {score}</span>
        )}
      </div>
      {latest?.stages && (
        <div className="mt-2 flex gap-3 text-[11px] text-ink-faint">
          {latest.stages.deep  != null && <span>Глуб {latest.stages.deep}ч</span>}
          {latest.stages.rem   != null && <span>REM {latest.stages.rem}ч</span>}
          {latest.stages.light != null && <span>Лёгк {latest.stages.light}ч</span>}
        </div>
      )}
    </div>
  );
}
