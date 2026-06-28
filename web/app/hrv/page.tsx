"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { HrvSummary } from "@/lib/types";

export default function HrvPage() {
  const { data, error, isLoading } = useSWR<HrvSummary>(
    "/api/hrv/summary?days=30",
    fetcher,
    { refreshInterval: 5 * 60 * 1000 },
  );

  return (
    <main className="space-y-5">
      <h1 className="text-2xl font-bold text-ink">Анализ HRV</h1>

      {isLoading ? <div className="h-40 animate-pulse rounded-card bg-surface" /> : null}
      {error ? <ErrorCard /> : null}
      {data && !data.has_data ? <NoData /> : null}

      {data?.has_data && data.latest && data.baseline ? (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Metric label="RMSSD сегодня" value={`${data.latest.rmssd}`} unit="мс" />
            <Metric
              label="Восстановление"
              value={
                data.latest.recovery_score != null
                  ? `${data.latest.recovery_score}`
                  : "—"
              }
              unit={data.latest.recovery_score != null ? "%" : ""}
            />
            <Metric label="Базовая линия" value={`${data.baseline.rmssd}`} unit="мс" />
          </div>

          <div className="rounded-card border border-surface-border bg-surface p-5 shadow-card">
            <div className="mb-3 flex items-baseline justify-between">
              <span className="text-xs font-medium uppercase tracking-wide text-ink-faint">
                Тренд RMSSD · {data.trend.length} дн.
              </span>
              <span className="text-xs text-ink-faint">{data.latest.recovery_info}</span>
            </div>
            <Sparkline
              points={data.trend.map((t) => t.rmssd)}
              baseline={data.baseline.rmssd}
            />
          </div>

          <div className="rounded-card border border-surface-border bg-surface p-5 shadow-card">
            <div className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-faint">
              Сигналы
            </div>
            <ul className="space-y-2">
              {data.signals.map((s, i) => (
                <li key={i} className="flex items-center gap-2 text-sm">
                  <span
                    className={`h-2 w-2 rounded-full ${
                      s.severity === "warning"
                        ? "bg-tone-warning"
                        : s.severity === "success"
                          ? "bg-tone-success"
                          : "bg-ink-faint"
                    }`}
                  />
                  <span className="text-ink">{s.label}</span>
                </li>
              ))}
            </ul>
          </div>
        </>
      ) : null}
    </main>
  );
}

function Metric({ label, value, unit }: { label: string; value: string; unit: string }) {
  return (
    <div className="rounded-card border border-surface-border bg-surface p-4 shadow-card">
      <div className="text-xs font-medium uppercase tracking-wide text-ink-faint">
        {label}
      </div>
      <div className="mt-1 text-2xl font-bold text-ink">
        {value}
        <span className="ml-1 text-sm font-normal text-ink-faint">{unit}</span>
      </div>
    </div>
  );
}

// Lightweight inline trend chart — keeps the bundle dependency-free.
// (Recharts can replace this later per the spec without changing the API.)
function Sparkline({ points, baseline }: { points: number[]; baseline: number }) {
  const w = 640;
  const h = 140;
  const pad = 8;
  if (points.length < 2) {
    return <div className="text-sm text-ink-faint">Недостаточно точек для графика.</div>;
  }
  const all = [...points, baseline];
  const min = Math.min(...all);
  const max = Math.max(...all);
  const span = max - min || 1;
  const x = (i: number) => pad + (i * (w - 2 * pad)) / (points.length - 1);
  const y = (v: number) => h - pad - ((v - min) / span) * (h - 2 * pad);

  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(p)}`).join(" ");
  const baseY = y(baseline);

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full" preserveAspectRatio="none">
      <line
        x1={pad}
        x2={w - pad}
        y1={baseY}
        y2={baseY}
        stroke="#94A3B8"
        strokeWidth={1}
        strokeDasharray="4 4"
      />
      <path d={path} fill="none" stroke="#3B82F6" strokeWidth={2} />
      {points.map((p, i) => (
        <circle key={i} cx={x(i)} cy={y(p)} r={2.5} fill="#3B82F6" />
      ))}
    </svg>
  );
}

function ErrorCard() {
  return (
    <div className="rounded-card border border-red-200 bg-red-50 p-4 text-sm text-tone-danger">
      Не удалось загрузить HRV. Запущен ли API на :8000?
    </div>
  );
}

function NoData() {
  return (
    <div className="rounded-card border border-surface-border bg-surface p-6 text-center shadow-card">
      <div className="text-lg font-semibold text-ink">Нет данных HRV</div>
      <p className="mt-1 text-sm text-ink-soft">Синхронизируйте Garmin, чтобы увидеть тренд восстановления.</p>
    </div>
  );
}
