import type { SubjectiveWellness, TodayReadiness } from "@/lib/types";
import { ReadinessIndicator, ReadinessDetails } from "./ReadinessSummary";
import { TodayWellnessSummary } from "./TodayWellnessSummary";

export function TodayStateSummary({ readiness, wellness }: {
  readiness?: TodayReadiness | null;
  wellness?: SubjectiveWellness | null;
}) {
  return <section aria-label="Состояние сегодня" className="rounded-card border border-surface-border bg-surface p-4 sm:p-5">
    <h2 className="text-base font-semibold text-ink">Состояние сегодня</h2>
    <div className="mt-4 grid items-start gap-4 md:grid-cols-[200px_minmax(0,1fr)]">
      <ReadinessIndicator readiness={readiness} />
      {wellness ? <TodayWellnessSummary data={wellness} embedded /> : <p className="text-sm text-ink-soft">Ответов о самочувствии нет.</p>}
    </div>
    <details className="mt-4 border-t border-surface-border pt-3">
      <summary className="cursor-pointer rounded text-sm font-medium text-ink underline underline-offset-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">Подробнее о состоянии</summary>
      <p className="mt-3 text-xs text-ink-soft">Восстановление — расчётная оценка системы. Самочувствие — ваши ответы.</p>
      <div className="mt-4"><ReadinessDetails readiness={readiness} /></div>
      {wellness ? <p className="mt-3 text-xs text-ink-soft">Источник самооценки: {wellness.source === "intervals" ? "Intervals.icu" : "не указан"}. Время ответа неизвестно.</p> : null}
    </details>
  </section>;
}
