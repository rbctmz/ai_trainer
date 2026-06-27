import { TodayState, WorkoutCard } from "@/lib/types";

export function TodayCard({
  workout,
  today,
}: {
  workout: WorkoutCard;
  today: TodayState;
}) {
  const overreached = today.tsb < -20;
  return (
    <div className="rounded-card border border-surface-border bg-surface p-5 shadow-card">
      <div className="text-xs font-medium uppercase tracking-wide text-ink-faint">
        Сегодня
      </div>
      <div className="mt-1 text-lg font-semibold text-ink">{workout.title}</div>
      {workout.subtitle ? (
        <div className="mt-1 text-sm text-ink-soft">{workout.subtitle}</div>
      ) : null}

      {overreached ? (
        <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-tone-danger">
          TSB {today.tsb} — высокая усталость. Осторожнее с интенсивностью.
        </div>
      ) : null}

      <button
        className="mt-4 w-full rounded-lg bg-ink px-4 py-2.5 text-sm font-medium text-white transition hover:bg-ink/90"
        type="button"
      >
        {workout.button}
      </button>
    </div>
  );
}
