"use client";

import type { CoachDecision, CoachDecisionType } from "@/lib/types";

const badgeClass: Record<CoachDecisionType, string> = {
  Push: "border-tone-success/30 bg-tone-success/10 text-tone-success",
  Moderate: "border-tone-warning/30 bg-tone-warning/10 text-tone-warning",
  Recovery: "border-tone-danger/30 bg-tone-danger/10 text-tone-danger",
  Monitor: "border-surface-border bg-surface-muted text-ink-soft",
};

// Agent Log v2 (issue #501): human labels for trigger / scope / outcome.
// "unknown" = metadata was not captured (legacy rows) — shown, never invented.
const triggerLabels: Record<string, string> = {
  coach_request: "Запрос коуча",
  scheduled_check: "Плановая проверка",
  provider_sync: "Синхронизация данных",
  settings_change: "Изменение настроек",
  proposal_approved: "Подтверждено предложение",
  manual: "Вручную",
  unknown: "Запуск не зафиксирован",
};

const scopeLabels: Record<string, string> = {
  today: "Сегодня",
  week: "Ближайшая неделя",
  plan: "Весь план",
  unknown: "Зона не зафиксирована",
};

const outcomeLabels: Record<string, string> = {
  applied: "Применено",
  proposed: "Предложено",
  no_change: "Без изменений",
  rejected: "Отклонено",
  failed: "Ошибка",
  rolled_back: "Откат",
  unknown: "Исход не зафиксирован",
};

const outcomeTone: Record<string, string> = {
  applied: "border-tone-success/30 bg-tone-success/10 text-tone-success",
  proposed: "border-accent/30 bg-accent/10 text-accent",
  no_change: "border-surface-border bg-surface-muted text-ink-soft",
  rejected: "border-tone-warning/30 bg-tone-warning/10 text-tone-warning",
  failed: "border-tone-danger/30 bg-tone-danger/10 text-tone-danger",
  rolled_back: "border-tone-warning/30 bg-tone-warning/10 text-tone-warning",
  unknown: "border-surface-border bg-surface-muted text-ink-faint",
};

const neutralChip =
  "border border-surface-border bg-surface-muted px-1.5 py-px text-[11px] text-ink-faint";

// Sentinel mirror of models/coach_decisions.py::NO_REVISIT_REQUIRED. A NULL
// revisit_reason means the metadata predates Agent Log v2 (not captured).
const NO_REVISIT_REQUIRED = "no_revisit_required";

function label(map: Record<string, string>, value: string | null | undefined): string {
  if (value) return map[value] ?? value;
  return map.unknown ?? "Не зафиксировано";
}

function RevisitNote({ decision }: { decision: CoachDecision }) {
  const { revisit_at, revisit_reason } = decision;
  if (!revisit_at && !revisit_reason) return null;
  if (revisit_reason === NO_REVISIT_REQUIRED) {
    return <span className={neutralChip}>Пересмотр не требуется</span>;
  }
  if (revisit_reason && revisit_at) {
    return (
      <span className={neutralChip}>
        Пересмотр: {revisit_reason} (до {String(revisit_at).slice(0, 10)})
      </span>
    );
  }
  if (revisit_reason) {
    return <span className={neutralChip}>Пересмотр: {revisit_reason}</span>;
  }
  return <span className={neutralChip}>Пересмотр: {String(revisit_at).slice(0, 10)}</span>;
}

export function DecisionEntry({ decision }: { decision: CoachDecision }) {
  const count = decision.count ?? 1;
  const isRepeated = count > 1 && decision.first_time && decision.first_time !== decision.time;
  // Pre-#501 API payloads omit the v2 keys entirely; such rows show no chips
  // instead of a fabricated "unknown" (the backend normalizes legacy rows).
  const hasAgentLogV2 =
    decision.trigger !== undefined ||
    decision.scope !== undefined ||
    decision.outcome !== undefined;
  const outcomeToneClass = outcomeTone[decision.outcome ?? "unknown"] ?? outcomeTone.unknown;
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
        {hasAgentLogV2 ? (
          <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
            <span className={neutralChip}>{label(triggerLabels, decision.trigger)}</span>
            <span className={neutralChip}>{label(scopeLabels, decision.scope)}</span>
            <span
              className={`inline-flex rounded-full border px-1.5 py-px text-[11px] font-medium ${outcomeToneClass}`}
            >
              {label(outcomeLabels, decision.outcome)}
            </span>
            <RevisitNote decision={decision} />
          </div>
        ) : null}
        {isRepeated ? (
          <p className="text-xs text-ink-faint">
            Повторялось с {decision.first_time} по {decision.time}
          </p>
        ) : null}
      </div>
    </div>
  );
}
