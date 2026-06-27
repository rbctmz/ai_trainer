import { TodayState, Tone } from "@/lib/types";

const toneStyles: Record<Tone, { bar: string; chip: string; text: string }> = {
  danger: { bar: "bg-tone-danger", chip: "bg-red-50 text-tone-danger", text: "text-tone-danger" },
  warning: { bar: "bg-tone-warning", chip: "bg-amber-50 text-tone-warning", text: "text-tone-warning" },
  success: { bar: "bg-tone-success", chip: "bg-emerald-50 text-tone-success", text: "text-tone-success" },
  neutral: { bar: "bg-tone-neutral", chip: "bg-blue-50 text-tone-neutral", text: "text-tone-neutral" },
};

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-card border border-surface-border bg-surface p-4 shadow-card">
      <div className="text-xs font-medium uppercase tracking-wide text-ink-faint">
        {label}
      </div>
      <div className="mt-1 text-2xl font-bold text-ink">{value}</div>
    </div>
  );
}

export function StatusRow({ today }: { today: TodayState }) {
  const tone = toneStyles[today.tone] ?? toneStyles.neutral;
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <div
        className={`col-span-2 overflow-hidden rounded-card border border-surface-border bg-surface p-4 shadow-card`}
      >
        <div className="flex items-center gap-2">
          <span className={`h-2.5 w-2.5 rounded-full ${tone.bar}`} />
          <span className="text-xs font-medium uppercase tracking-wide text-ink-faint">
            Состояние
          </span>
        </div>
        <div className={`mt-1 text-2xl font-bold ${tone.text}`}>
          {today.state_label}
        </div>
      </div>
      <Metric label="Readiness" value={`${today.readiness}`} />
      <Metric label="TSB" value={`${today.tsb}`} />
      <Metric label="CTL" value={`${today.ctl}`} />
      <Metric label="HRV" value={today.hrv != null ? `${today.hrv}` : "—"} />
    </div>
  );
}
