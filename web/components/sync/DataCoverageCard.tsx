"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { dataSourceLabel } from "@/lib/sourceLabels";
import { DataCoverageResponse, DailyMetricCoverage } from "@/lib/types";

const METRIC_LABELS: Record<DailyMetricCoverage["key"], string> = {
  sleep_duration: "Длительность сна",
  sleep_score: "Оценка сна",
  hrv: "HRV",
  resting_hr: "Пульс покоя",
  steps: "Шаги",
};

export function DataCoverageCard() {
  const [days, setDays] = useState<30 | 90>(30);
  const { data, error, isLoading } = useSWR<DataCoverageResponse>(`/api/sync/coverage?days=${days}`, fetcher);

  return (
    <section className="rounded-card border border-surface-border bg-surface p-5 shadow-card">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-ink">Покрытие данных</h2>
          <p className="mt-1 text-xs text-ink-faint">
            Локальная инвентаризация Garmin Connect и Intervals.icu без обращения к провайдерам.
          </p>
        </div>
        <div className="flex rounded-lg border border-surface-border bg-surface-muted p-1">
          {([30, 90] as const).map((windowDays) => (
            <button
              key={windowDays}
              type="button"
              onClick={() => setDays(windowDays)}
              aria-pressed={days === windowDays}
              className={[
                "rounded-md px-3 py-1 text-xs font-medium transition",
                days === windowDays ? "bg-surface text-ink shadow-sm" : "text-ink-faint",
              ].join(" ")}
            >
              {windowDays} дней
            </button>
          ))}
        </div>
      </div>

      {isLoading ? <p className="mt-4 text-sm text-ink-faint">Считаю покрытие…</p> : null}
      {error ? (
        <p className="mt-4 text-sm text-tone-danger">Не удалось получить покрытие данных.</p>
      ) : null}

      {data ? (
        <div className="mt-4 space-y-5">
          <div className="rounded-xl border border-surface-border bg-surface-muted p-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">
                  Активности
                </p>
                <p className="mt-1 text-lg font-semibold text-ink">
                  {data.activities.canonical_count} за {data.window.days} дней
                </p>
              </div>
              <p className="text-xs text-ink-faint">
                Последняя: {formatDate(data.activities.latest_date)}
              </p>
            </div>
            <div className="mt-3 flex flex-wrap gap-2 text-xs text-ink-soft">
              <SourcePill label="Garmin Connect" count={data.activities.provider_link_counts.garmin} />
              <SourcePill label="Intervals.icu" count={data.activities.provider_link_counts.intervals} />
              {data.activities.unattributed_count > 0 ? (
                <SourcePill label="Источник не сохранён" count={data.activities.unattributed_count} />
              ) : null}
            </div>
            <p className="mt-2 text-[11px] text-ink-faint">
              Источники могут пересекаться: одна объединённая активность может иметь две связи.
            </p>
          </div>

          <div>
            <h3 className="text-sm font-semibold text-ink">Покрытие ежедневных сигналов</h3>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
              {data.daily_metrics.map((metric) => (
                <MetricCoverage key={metric.key} metric={metric} />
              ))}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function SourcePill({ label, count }: { label: string; count: number }) {
  return (
    <span className="rounded-full border border-surface-border bg-surface px-2.5 py-1">
      {label}: {count}
    </span>
  );
}

function MetricCoverage({ metric }: { metric: DailyMetricCoverage }) {
  const sources = Object.entries(metric.source_days);
  return (
    <div className="rounded-xl border border-surface-border p-3">
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-xs font-medium text-ink">{METRIC_LABELS[metric.key]}</p>
        <span className="text-sm font-semibold text-ink">{metric.coverage_pct}%</span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-muted">
        <div
          className="h-full rounded-full bg-accent"
          style={{ width: `${Math.min(100, metric.coverage_pct)}%` }}
        />
      </div>
      <p className="mt-2 text-[11px] text-ink-faint">
        {metric.observed_days} дней · пропущено {metric.missing_days}
      </p>
      <p className="mt-1 text-[11px] text-ink-faint">
        Последнее: {formatDate(metric.latest_date)}
      </p>
      {sources.length > 0 ? (
        <p className="mt-2 text-[11px] leading-4 text-ink-soft">
          {sources.map(([source, count]) => `${dataSourceLabel(source)} ${count}`).join(" · ")}
        </p>
      ) : null}
    </div>
  );
}

function formatDate(value: string | null): string {
  if (!value) return "нет данных";
  return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short", timeZone: "UTC" }).format(
    new Date(`${value}T00:00:00Z`),
  );
}
