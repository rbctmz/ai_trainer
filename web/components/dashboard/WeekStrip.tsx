import { DayStatus, NextDay } from "@/lib/types";

const statusStyles: Record<DayStatus, string> = {
  today: "border-tone-neutral ring-1 ring-tone-neutral",
  planned: "border-surface-border",
  done: "border-tone-success bg-tone-success/10",
  rest: "border-surface-border bg-surface-muted",
  empty: "border-dashed border-surface-border",
};

export function WeekStrip({ days }: { days: NextDay[] }) {
  const todayIso = new Date().toISOString().slice(0, 10);
  return (
    <div>
      <div className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-faint">
        Ближайшие 7 дней
      </div>
      <div className="grid grid-cols-4 gap-2 sm:grid-cols-7">
        {days.map((d) => {
          const isToday = d.date === todayIso;
          const style = isToday ? statusStyles.today : statusStyles[d.status];
          return (
            <div
              key={d.date}
              className={`rounded-xl border bg-surface p-2.5 text-center shadow-card ${style}`}
            >
              <div className="text-[11px] font-medium text-ink-faint">
                {d.label}
              </div>
              <div className="mt-1 text-base font-bold text-ink">
                {d.tss > 0 ? d.tss : "—"}
              </div>
              <div className="truncate text-[11px] text-ink-soft">{d.sport}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
