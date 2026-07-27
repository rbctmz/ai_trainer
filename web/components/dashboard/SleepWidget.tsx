"use client";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { SleepSummary } from "@/lib/types";
import { InfoTip } from "@/components/ui/Tooltip";
import { MiniBars } from "@/components/ui/MiniBars";

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
  const recentTrend = (data?.trend ?? []).slice(-10);

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
          <span className="flex items-center gap-1 text-sm text-ink-soft mb-0.5">
            оценка {score} · {scoreSourceLabel(latest?.score_source)}
            <InfoTip metric="sleep_score" />
          </span>
        )}
      </div>
      {latest?.stages_available && latest.stages && (
        <div className="mt-2 flex gap-3 text-[11px] text-ink-faint">
          {latest.stages.deep  != null && <span>Глуб {latest.stages.deep}ч</span>}
          {latest.stages.rem   != null && <span>REM {latest.stages.rem}ч</span>}
          {latest.stages.light != null && <span>Лёгк {latest.stages.light}ч</span>}
        </div>
      )}
      {recentTrend.length >= 2 && (
        <div className="mt-4">
          <div className="mb-1.5 text-[11px] text-ink-faint">
            Последние {recentTrend.length} дн.
          </div>
          <MiniBars
            values={recentTrend.map((t) => t.hours)}
            labels={recentTrend.map((t) => t.date)}
            unit=" ч"
            height="h-14"
          />
        </div>
      )}
    </div>
  );
}

function scoreSourceLabel(source?: string) {
  if (source === "intervals") return "Intervals.icu";
  if (source === "garmin") return "Garmin";
  if (source === "derived") return "расчётная";
  if (source === "demo") return "демо";
  return "источник не сохранён";
}
