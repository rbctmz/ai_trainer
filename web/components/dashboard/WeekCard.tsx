import { PlanCard, WeekLoad } from "@/lib/types";

export function WeekCard({ week, plan }: { week: WeekLoad; plan: PlanCard }) {
  const pct =
    week.planned_tss > 0
      ? Math.min(100, Math.round((week.actual_tss / week.planned_tss) * 100))
      : week.actual_tss > 0
        ? 100
        : 0;

  return (
    <div className="rounded-card border border-surface-border bg-surface p-5 shadow-card">
      <div className="flex items-baseline justify-between">
        <div className="text-xs font-medium uppercase tracking-wide text-ink-faint">
          Неделя
        </div>
        <div className="text-xs font-medium text-ink-soft">{week.status}</div>
      </div>

      <div className="mt-2 flex items-baseline gap-1">
        <span className="text-2xl font-bold text-ink">{week.actual_tss}</span>
        <span className="text-sm text-ink-faint">
          / {week.planned_tss} план · TSS
        </span>
      </div>

      <div className="mt-3 h-2 overflow-hidden rounded-full bg-surface-muted">
        <div
          className="h-full rounded-full bg-tone-neutral transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="mt-2 flex justify-between text-xs text-ink-faint">
        <span>осталось {week.remaining_tss}</span>
        <span>прогноз {week.forecast_tss}</span>
      </div>

      <div className="mt-4 border-t border-surface-border pt-3">
        <div className="text-sm font-semibold text-ink">{plan.title}</div>
        {plan.subtitle ? (
          <div className="text-xs text-ink-soft">{plan.subtitle}</div>
        ) : null}
      </div>
    </div>
  );
}
