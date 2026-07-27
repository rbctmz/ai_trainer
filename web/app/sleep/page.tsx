"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { SleepSummary } from "@/lib/types";
import { MiniBars } from "@/components/ui/MiniBars";

export default function SleepPage() {
  const { data, error, isLoading } = useSWR<SleepSummary>(
    "/api/sleep/summary?days=30",
    fetcher,
    { refreshInterval: 5 * 60 * 1000 },
  );

  return (
    <main className="space-y-5">
      <h1 className="text-2xl font-bold text-ink">Анализ сна</h1>

      {isLoading ? <div className="h-40 animate-pulse rounded-card bg-surface" /> : null}
      {error ? (
        <div className="rounded-card border border-tone-danger/30 bg-tone-danger/10 p-4 text-sm text-tone-danger">
          Не удалось загрузить данные сна. Проверьте, что ./run_web.sh запущен.
        </div>
      ) : null}
      {data && !data.has_data ? <NoData /> : null}

      {data?.has_data && data.latest ? (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Metric
              label="Сон"
              value={data.latest.hours != null ? `${data.latest.hours}` : "—"}
              unit="ч"
              detail={sourceLabel(data.latest.duration_source)}
            />
            <Metric
              label="Оценка"
              value={data.latest.score != null ? `${data.latest.score}` : "—"}
              unit="/100"
              detail={scoreSourceLabel(data.latest.score_source)}
            />
            <Metric
              label="Эффективность"
              value={data.latest.efficiency != null ? `${data.latest.efficiency}` : "—"}
              unit="%"
              detail={efficiencySourceLabel(data.latest.efficiency_source)}
            />
            <Metric
              label="Пробуждения"
              value={data.latest.awakenings != null ? `${data.latest.awakenings}` : "—"}
              unit=""
            />
          </div>

          {data.latest.awake_minutes != null ? (
            <div className="text-xs text-ink-faint">
              Бодрствование в окне сна: {data.latest.awake_minutes} мин
            </div>
          ) : null}

          {data.latest.stages_available ? (
            <Stages stages={data.latest.stages} total={data.latest.hours} />
          ) : null}

          <div className="rounded-card border border-surface-border bg-surface p-5 shadow-card">
            <div className="mb-3 flex items-baseline justify-between">
              <span className="text-xs font-medium uppercase tracking-wide text-ink-faint">
                Длительность сна · {data.trend.length} дн.
              </span>
              {data.averages ? (
                <span className="text-xs text-ink-faint">
                  среднее {data.averages.hours ?? "—"} ч · оценка {data.averages.score ?? "—"}
                </span>
              ) : null}
            </div>
            <MiniBars
              values={data.trend.map((t) => t.hours)}
              labels={data.trend.map((t) => t.date)}
              unit=" ч"
              height="h-32"
            />
          </div>
        </>
      ) : null}
    </main>
  );
}

function Stages({
  stages,
  total,
}: {
  stages: { deep: number | null; light: number | null; rem: number | null };
  total: number | null;
}) {
  const segs = [
    { key: "deep", label: "Глубокий", val: stages.deep ?? 0, color: "#1E40AF" },
    { key: "rem", label: "REM", val: stages.rem ?? 0, color: "#7C3AED" },
    { key: "light", label: "Лёгкий", val: stages.light ?? 0, color: "#60A5FA" },
  ];
  const sum = segs.reduce((a, s) => a + s.val, 0) || total || 1;
  return (
    <div className="rounded-card border border-surface-border bg-surface p-5 shadow-card">
      <div className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-faint">
        Фазы последней ночи
      </div>
      <div className="flex h-3 overflow-hidden rounded-full bg-surface-muted">
        {segs.map((s) => (
          <div
            key={s.key}
            style={{ width: `${(s.val / sum) * 100}%`, background: s.color }}
            title={`${s.label}: ${s.val} ч`}
          />
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-4 text-xs text-ink-soft">
        {segs.map((s) => (
          <span key={s.key} className="flex items-center gap-1.5">
            <span className="h-2 w-3 rounded" style={{ background: s.color }} />
            {s.label}: {s.val} ч
          </span>
        ))}
      </div>
    </div>
  );
}

function scoreSourceLabel(source: string) {
  if (source === "intervals") return "Intervals.icu";
  if (source === "garmin") return "Garmin";
  if (source === "derived") return "расчётная";
  if (source === "demo") return "демо";
  if (source === "mixed") return "смешанные источники";
  return "источник не сохранён";
}

function sourceLabel(source: string) {
  if (source === "intervals") return "Intervals.icu";
  if (source === "garmin") return "Garmin";
  if (source === "demo") return "демо";
  if (source === "mixed") return "смешанные источники";
  return "источник не сохранён";
}

function efficiencySourceLabel(source: string) {
  if (source === "derived_awake_time") return "по времени бодрствования";
  if (source === "derived_sleep_window") return "по окну сна";
  if (source === "demo") return "демо";
  if (source === "unavailable") return "нет исходных данных";
  return "источник не сохранён";
}

function Metric({
  label,
  value,
  unit,
  detail,
}: {
  label: string;
  value: string;
  unit: string;
  detail?: string;
}) {
  return (
    <div className="rounded-card border border-surface-border bg-surface p-4 shadow-card">
      <div className="text-xs font-medium uppercase tracking-wide text-ink-faint">{label}</div>
      <div className="mt-1 text-2xl font-bold text-ink">
        {value}
        <span className="ml-1 text-sm font-normal text-ink-faint">{unit}</span>
      </div>
      {detail ? <div className="mt-1 text-[11px] text-ink-faint">{detail}</div> : null}
    </div>
  );
}

function NoData() {
  return (
    <div className="rounded-card border border-surface-border bg-surface p-6 text-center shadow-card">
      <div className="text-lg font-semibold text-ink">Нет данных сна</div>
      <p className="mt-1 text-sm text-ink-soft">Подключите источник данных, чтобы увидеть анализ сна.</p>
    </div>
  );
}
