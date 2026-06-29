import { RaceProjectionData } from "@/lib/types";

export function RaceProjection({ data }: { data: RaceProjectionData }) {
  const statusColor =
    data.status === "on_track" ? "text-tone-success" : "text-tone-warning";
  const tsbColor =
    data.fresh_for_race ? "text-tone-success" : "text-tone-warning";

  return (
    <div className="rounded-card border border-surface-border bg-surface p-4 shadow-card">
      <div className="text-xs font-medium uppercase tracking-wide text-ink-faint mb-2">
        К старту · {data.days_to_race} дн
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <div className="text-[11px] text-ink-faint">CTL на финише</div>
          <div className="text-xl font-bold text-ink">{data.projected_ctl}</div>
        </div>
        <div>
          <div className="text-[11px] text-ink-faint">TSB на старте</div>
          <div className={`text-xl font-bold ${tsbColor}`}>
            {data.projected_tsb > 0 ? "+" : ""}{data.projected_tsb}
          </div>
        </div>
      </div>
      <div className={`mt-2 text-xs font-medium ${statusColor}`}>{data.label}</div>
    </div>
  );
}
