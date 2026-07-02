"use client";

import type { CoachDecision, CoachDecisionType } from "@/lib/types";

const badgeClass: Record<CoachDecisionType, string> = {
  Push: "border-tone-success/30 bg-tone-success/10 text-tone-success",
  Moderate: "border-tone-warning/30 bg-tone-warning/10 text-tone-warning",
  Recovery: "border-tone-danger/30 bg-tone-danger/10 text-tone-danger",
  Monitor: "border-surface-border bg-surface-muted text-ink-soft",
};

export function DecisionEntry({ decision }: { decision: CoachDecision }) {
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
        <p className="text-sm leading-6 text-ink">{decision.reason}</p>
      </div>
    </div>
  );
}
