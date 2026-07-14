"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type {
  RecoveryAnalyticsResponse,
  RecoveryCohort,
  RecoveryMaturity,
} from "@/lib/types";

const MATURITY: Record<RecoveryMaturity, { label: string; note: string }> = {
  collection_only: {
    label: "Сбор данных",
    note: "Нужно не менее 10 сопоставимых эпизодов — кривая пока не строится.",
  },
  early_signal: {
    label: "Ранний сигнал",
    note: "Показаны медиана и межквартильный диапазон; это ещё не рекомендация.",
  },
  exploratory: {
    label: "Исследовательский паттерн",
    note: "Добавлен интервал по недельным кластерам; причинность не установлена.",
  },
  shadow_pattern: {
    label: "Теневой паттерн",
    note: "Наблюдение накоплено минимум на 30 эпизодах и 8 неделях.",
  },
};

export default function RecoveryPage() {
  const { data, error, isLoading } = useSWR<RecoveryAnalyticsResponse>(
    "/api/recovery-analytics",
    fetcher,
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected =
    data?.registry.find((cohort) => cohort.cohort_id === selectedId) ??
    data?.registry[0] ??
    null;

  return (
    <main className="space-y-5">
      <header>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-bold text-ink">Персональное восстановление</h1>
          <span className="rounded-full bg-accent/10 px-2 py-0.5 text-xs font-medium text-accent">
            shadow
          </span>
        </div>
        <p className="mt-1 text-sm text-ink-soft">
          Как менялась ваша утренняя готовность после сопоставимых тренировочных стимулов.
        </p>
      </header>

      {isLoading ? <div className="h-48 animate-pulse rounded-card bg-surface" /> : null}
      {error ? (
        <section className="rounded-card border border-tone-danger/30 bg-tone-danger/10 p-4 text-sm text-tone-danger">
          Не удалось загрузить аналитику восстановления. Проверьте, что ./run_web.sh запущен.
        </section>
      ) : null}

      {data ? (
        <>
          <EvidenceCard data={data} />

          {data.registry.length === 0 ? (
            <section className="rounded-card border border-surface-border bg-surface p-6 text-center shadow-card">
              <h2 className="text-lg font-semibold text-ink">Идёт сбор данных</h2>
              <p className="mt-1 text-sm text-ink-soft">
                После синхронизаций появятся prospective-снимки готовности. Эпизоды войдут
                в анализ только при доказанном плане-факте и достаточной временной точности.
              </p>
            </section>
          ) : (
            <section className="rounded-card border border-surface-border bg-surface p-5 shadow-card">
              <h2 className="text-sm font-semibold text-ink">Сопоставимые когорты</h2>
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                {data.registry.map((cohort) => (
                  <button
                    key={cohort.cohort_id}
                    type="button"
                    onClick={() => setSelectedId(cohort.cohort_id)}
                    className={`rounded-lg border p-3 text-left transition ${
                      selected?.cohort_id === cohort.cohort_id
                        ? "border-accent bg-accent/5"
                        : "border-surface-border bg-surface-muted hover:border-accent/50"
                    }`}
                  >
                    <div className="font-medium text-ink">{cohortTitle(cohort)}</div>
                    <div className="mt-1 text-xs text-ink-faint">
                      n={cohort.n} · {cohort.distinct_weeks} нед. · {MATURITY[cohort.maturity].label}
                    </div>
                  </button>
                ))}
              </div>
            </section>
          )}

          {selected ? <CohortCard cohort={selected} /> : null}

          <details className="rounded-card border border-surface-border bg-surface p-4 shadow-card">
            <summary className="cursor-pointer text-sm font-medium text-ink">
              Исключения и научные ограничения
            </summary>
            <div className="mt-3 space-y-2 text-sm text-ink-soft">
              <p>{data.guardrails.message}</p>
              <p>
                Исключено эпизодов: {data.coverage.excluded}; backfill отдельно: {data.coverage.backfilled_excluded}.
              </p>
              {Object.entries(data.coverage.exclusion_counts).map(([reason, count]) => (
                <p key={reason}>• {reason}: {count}</p>
              ))}
              <p className="text-xs text-ink-faint">
                Правила: {data.rule_version} · bootstrap: {data.bootstrap_rule_version}
              </p>
            </div>
          </details>
        </>
      ) : null}
    </main>
  );
}

function EvidenceCard({ data }: { data: RecoveryAnalyticsResponse }) {
  const maturity = MATURITY[data.maturity];
  return (
    <section className="rounded-card border border-surface-border bg-surface p-5 shadow-card">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-ink">Надёжность наблюдений</h2>
          <p className="mt-1 text-sm text-ink-soft">{maturity.note}</p>
        </div>
        <span className="rounded-full bg-surface-muted px-2.5 py-1 text-xs font-medium text-ink-soft">
          {maturity.label}
        </span>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Metric label="Снимков" value={data.snapshot_coverage.total} />
        <Metric label="Надёжных" value={data.snapshot_coverage.eligible} />
        <Metric label="Дней" value={data.snapshot_coverage.distinct_days} />
        <Metric label="Эпизодов" value={data.coverage.eligible} />
      </div>
    </section>
  );
}

function CohortCard({ cohort }: { cohort: RecoveryCohort }) {
  const meta = MATURITY[cohort.maturity];
  return (
    <section className="rounded-card border border-surface-border bg-surface p-5 shadow-card">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold text-ink">{cohortTitle(cohort)}</h2>
          <p className="mt-1 text-sm text-ink-soft">{meta.note}</p>
        </div>
        <span className="text-xs text-ink-faint">n={cohort.n} · {cohort.distinct_weeks} нед.</span>
      </div>
      {!cohort.publishable ? (
        <div className="mt-4 rounded-lg bg-surface-muted p-4 text-sm text-ink-soft">
          Идёт сбор данных: до первого раннего сигнала осталось {Math.max(0, 10 - cohort.n)} эпизодов.
        </div>
      ) : (
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          {cohort.points.map((point) => (
            <div key={point.day} className="rounded-lg bg-surface-muted p-3">
              <div className="text-xs font-medium uppercase tracking-wide text-ink-faint">D+{point.day}</div>
              <div className="mt-1 text-xl font-bold text-ink">
                {point.median == null ? "—" : `${point.median > 0 ? "+" : ""}${point.median}`}
              </div>
              <div className="text-xs text-ink-faint">
                readiness · n={point.n_observed} · пропущено {point.missing}
              </div>
              {point.q1 != null && point.q3 != null ? (
                <div className="mt-1 text-xs text-ink-soft">IQR {point.q1}…{point.q3}</div>
              ) : null}
              {point.interval ? (
                <div className="text-xs text-ink-soft">интервал {point.interval.low}…{point.interval.high}</div>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg bg-surface-muted p-3">
      <div className="text-xs text-ink-faint">{label}</div>
      <div className="mt-0.5 text-xl font-bold text-ink">{value}</div>
    </div>
  );
}

function cohortTitle(cohort: RecoveryCohort): string {
  const value = cohort.dimensions;
  return [value.stimulus_family, value.sport, value.load_bucket, value.adherence].join(" · ");
}
