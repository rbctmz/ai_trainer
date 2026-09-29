import type { ReadinessFreshness, TodayReadiness, TodayReadinessDriver } from "@/lib/types";
import { decisionText } from "./displayText";

const labels: Record<string, string> = {
  low: "Низкая готовность", limited: "Ограниченная готовность",
  ready: "Контролируемая готовность", strong: "Готов к работе",
  stale: "Данные требуют обновления", unknown: "Недостаточно данных",
};
function inputLabel(key: string): string {
  return ({ sleep: "Сон", sleep_score: "Сон", hrv: "Вариабельность пульса", rhr: "Пульс покоя", resting_hr: "Пульс покоя",
    tsb: "Баланс нагрузки", training_readiness: "Оценка Garmin" } as Record<string, string>)[key] ?? "Другой показатель";
}

// Issue #557: the browser only *labels* server-owned provenance values; it never
// derives freshness, scores or eligibility itself.
function observationDateLabel(driver: TodayReadinessDriver): string {
  switch (driver.observation_status) {
    case "confirmed_today":
      return "сегодня";
    case "outdated": {
      const date = driver.observation_as_of ? ` · ${driver.observation_as_of}` : "";
      if (driver.age_days === 1) return `вчера${date}`;
      if (typeof driver.age_days === "number" && driver.age_days > 1) {
        return `${driver.age_days} дн. назад${date}`;
      }
      return `не за сегодня${date}`;
    }
    case "invalid":
      return "некорректная дата измерения";
    default:
      return "дата измерения неизвестна";
  }
}

function freshnessSummary(freshness: ReadinessFreshness): string {
  const parts: string[] = [];
  const addInputs = (keys: string[], description: string) => {
    const primaryLabels = keys.filter((key) => key !== "training_readiness").map(inputLabel);
    if (primaryLabels.length > 0) parts.push(`${description}: ${primaryLabels.join(", ")}`);
  };
  addInputs(freshness.confirmed_today, "подтверждено сегодня");
  addInputs(freshness.outdated, "не за сегодня");
  addInputs(freshness.unverified, "дата неизвестна");
  addInputs(freshness.invalid, "некорректная дата");
  addInputs(freshness.missing, "нет данных");
  return parts.join(" · ");
}

const blockedReasonLabels: Record<string, string> = {
  no_confirmed_today_primary_recovery_measurement:
    "нет подтверждённого сегодняшнего первичного измерения (сон, HRV, пульс покоя)",
  no_intervention_eligible_factors: "нет ни одного пригодного измерения восстановления",
};


export function ReadinessIndicator({ readiness }: { readiness?: TodayReadiness | null }) {
  const value = readiness?.score;
  const valid = typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100;
  const provisional = Boolean(readiness?.is_provisional || readiness?.stale ||
    (readiness?.freshness && readiness.freshness.state !== "fresh"));
  const dateGaps = Boolean(readiness?.freshness &&
    (readiness.freshness.unverified.length || readiness.freshness.invalid.length || readiness.freshness.outdated.length));
  const freshness = provisional ? "Предварительно" : dateGaps ? "Часть дат не подтверждена" :
    readiness?.freshness?.state === "fresh" ? "Данные за сегодня" : "Актуальность данных не подтверждена";
  const label = valid ? labels[readiness?.status ?? "unknown"] ?? "Не определено" : "Нет оценки";
  const radius = 34;
  const circumference = 2 * Math.PI * radius;
  return (
    <div className="min-w-0">
      <h3 className="text-base font-semibold text-ink">Восстановление</h3>
      <div className="mt-3 rounded-lg bg-surface-muted p-3">
      <div className="flex items-center gap-3">
        <div className="relative h-16 w-16 shrink-0" role={valid ? "meter" : undefined}
          aria-label={valid ? "Восстановление" : undefined} aria-valuemin={valid ? 0 : undefined}
          aria-valuemax={valid ? 100 : undefined} aria-valuenow={valid ? value : undefined}
          aria-valuetext={valid ? `${value} из 100; ${label}; ${freshness}` : undefined}>
          <svg viewBox="0 0 80 80" className="h-full w-full -rotate-90" aria-hidden="true">
            <circle cx="40" cy="40" r={radius} fill="none" stroke="currentColor" strokeWidth="7" className="text-surface-border" />
            {valid ? <circle cx="40" cy="40" r={radius} fill="none" stroke="currentColor" strokeWidth="7"
              strokeLinecap="round" strokeDasharray={`${(value / 100) * circumference} ${circumference}`}
              className="text-accent" /> : null}
          </svg>
          <span className="absolute inset-0 flex flex-col items-center justify-center font-semibold tabular-nums text-ink">
            <span className="text-lg leading-tight">{valid ? Math.round(value) : "—"}</span>
            {valid ? <span className="text-[10px] font-normal leading-tight text-ink-soft">/100</span> : null}
          </span>
        </div>
        <div className="min-w-0">
          <p className="text-sm font-medium text-ink">{label}</p>
        </div>
      </div>
      <p className="mt-3 border-t border-surface-border pt-2 text-xs leading-relaxed text-ink-soft">{freshness}</p>
      </div>
    </div>
  );
}

export function ReadinessDetails({ readiness }: { readiness?: TodayReadiness | null }) {
  if (!readiness) return <p className="text-sm text-ink-soft">Данных для оценки восстановления нет.</p>;
  const drivers = readiness.drivers.length ? readiness.drivers : readiness.factors;
  const freshness = readiness.freshness;
  const sourceCompleteness = readiness.source_completeness;
  const hasPrimaryCount = typeof sourceCompleteness === "number" && Number.isFinite(sourceCompleteness) && sourceCompleteness >= 0 && sourceCompleteness <= 1;
  const presentPrimaryCount = hasPrimaryCount ? Math.round(sourceCompleteness * 3) : null;
  const primaryDrivers = drivers.filter((item) => item.key !== "training_readiness");
  const garminDriver = drivers.find((item) => item.key === "training_readiness");
  const garminEvidence = garminDriver?.evidence
    ? decisionText(String(garminDriver.evidence)).replace(/^Оценка Garmin\s*/i, "")
    : "";
  return (
    <div className="space-y-3 text-sm text-ink-soft">
      <h3 className="font-medium text-ink">Показатели восстановления</h3>
      <p className="rounded-lg bg-surface-muted p-3 text-ink">{presentPrimaryCount !== null
        ? `Основные измерения: ${presentPrimaryCount} из 3. Актуальность проверяется отдельно.`
        : "Наличие основных измерений не подтверждено. Актуальность проверяется отдельно."}</p>
      {readiness.freshness && readiness.freshness.state !== "fresh" ? (
        <div className="rounded-lg border border-tone-warning/30 bg-tone-warning/10 p-3">
          <p className="font-medium text-ink">{readiness.freshness.state === "data_gap"
            ? "Сегодняшнего измерения восстановления нет — оценка предварительная"
            : "Часть ночных измерений не подтверждена за сегодня"}</p>
          {readiness.freshness.blocked_reason ? <p className="mt-1">{blockedReasonLabels[readiness.freshness.blocked_reason] ?? "Недостаточно подтверждённых данных для изменения плана"}</p> : null}
        </div>
      ) : null}
      <ul className="divide-y divide-surface-border">
        {primaryDrivers.map((item, index) => {
          const driver = item as TodayReadinessDriver;
          const evidence = String(item.evidence ?? "");
          return evidence ? <li key={index} className="py-2.5">
            <p>{driver.key === "tsb" ? `Расчётный показатель: ${decisionText(evidence)}` : decisionText(evidence)}</p>
            <p className="mt-1 text-xs text-ink-soft">{observationDateLabel(driver)}</p>
          </li> : null;
        })}
      </ul>
      {garminDriver?.evidence ? <p className="rounded-lg border border-surface-border p-3">Дополнительная оценка Garmin{garminEvidence ? `: ${garminEvidence}` : ""}<span className="mt-1 block text-xs">{observationDateLabel(garminDriver as TodayReadinessDriver)}</span></p> : null}
      {readiness.tsb?.tsb != null && !drivers.some((item) => item.key === "tsb") ? (
        <p>Расчётный баланс нагрузки (TSB): {readiness.tsb.tsb}; базовая нагрузка (CTL): {readiness.tsb.ctl ?? "—"}; окно {readiness.tsb.window_days} дн.</p>
      ) : null}
      {readiness.freshness ? <p className="text-xs">{freshnessSummary(readiness.freshness)}</p> : null}
    </div>
  );
}
