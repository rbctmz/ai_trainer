"use client";

import type { CoachDecision, CoachDecisionType } from "@/lib/types";

const badgeClass: Record<CoachDecisionType, string> = {
  Push: "border-tone-success/30 bg-tone-success/10 text-tone-success",
  Moderate: "border-tone-warning/30 bg-tone-warning/10 text-tone-warning",
  Recovery: "border-tone-danger/30 bg-tone-danger/10 text-tone-danger",
  Monitor: "border-surface-border bg-surface-muted text-ink-soft",
};

export function DecisionEntry({ decision }: { decision: CoachDecision }) {
  const count = decision.count ?? 1;
  const isRepeated = count > 1 && decision.first_time && decision.first_time !== decision.time;
  return (
    <div className="flex gap-3 border-b border-surface-border py-3 last:border-0">
      <div className="w-12 shrink-0 pt-0.5 text-sm tabular-nums text-ink-faint">
        {decision.time || "--:--"}
      </div>
      <div className="min-w-0 flex-1 space-y-1">
        <span
          className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold ${badgeClass[decision.decision_type]}`}
        >
          {decision.decision_type}
        </span>
        {count > 1 ? (
          <span className="ml-2 inline-flex rounded-full border border-surface-border bg-surface-muted px-2 py-0.5 text-xs text-ink-soft">
            ×{count}
          </span>
        ) : null}
        <p className="text-sm leading-6 text-ink">{decision.reason}</p>
        {isRepeated ? (
          <p className="text-xs text-ink-faint">
            Повторялось с {decision.first_time} по {decision.time}
          </p>
        ) : null}
      </div>
    </div>
  );
}
