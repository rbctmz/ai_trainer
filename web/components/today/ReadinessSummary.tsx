import type { ReadinessFreshness, TodayReadiness, TodayReadinessDriver } from "@/lib/types";
import { decisionText } from "./displayText";

const labels: Record<string, string> = {
  ready: "Нормальное", optimal: "Оптимальное", reduced: "Снижено", low: "Низкое",
  critical: "Критически низкое", unknown: "Не определено", data_gap: "Недостаточно данных",
};
function inputLabel(key: string): string {
  return ({ sleep: "Сон", sleep_score: "Сон", hrv: "Вариабельность пульса", rhr: "Пульс покоя",
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
  if (freshness.confirmed_today.length > 0) {
    parts.push(`подтверждено сегодня: ${freshness.confirmed_today.map(inputLabel).join(", ")}`);
  }
  if (freshness.outdated.length > 0) {
    parts.push(`не за сегодня: ${freshness.outdated.map(inputLabel).join(", ")}`);
  }
  if (freshness.unverified.length > 0) {
    parts.push(`дата неизвестна: ${freshness.unverified.map(inputLabel).join(", ")}`);
  }
  if (freshness.invalid.length > 0) {
    parts.push(`некорректная дата: ${freshness.invalid.map(inputLabel).join(", ")}`);
  }
  if (freshness.missing.length > 0) {
    parts.push(`нет данных: ${freshness.missing.map(inputLabel).join(", ")}`);
  }
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
    readiness?.freshness?.state === "fresh" ? "Данные за сегодня" : "Свежесть не подтверждена";
  const label = valid ? labels[readiness?.status ?? "unknown"] ?? "Не определено" : "Нет оценки";
  return (
    <div className="min-w-0 rounded-xl bg-surface-muted/60 p-4">
      <p className="text-sm font-medium text-ink-soft">Восстановление</p>
      <div className="mt-1 flex items-baseline gap-1.5">
        <span className="text-3xl font-semibold tabular-nums text-ink">{valid ? Math.round(value) : "—"}</span>
        {valid ? <span className="text-xs text-ink-soft">/ 100</span> : null}
      </div>
      {valid ? (
        <div role="meter" aria-label="Восстановление" aria-valuemin={0} aria-valuemax={100}
          aria-valuenow={value} aria-valuetext={`${value} из 100; ${label}; ${freshness}`}
          className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-border">
          <div className="h-full rounded-full bg-accent" style={{ width: `${value}%` }} />
        </div>
      ) : null}
      <p className="mt-2 text-sm text-ink">{label}</p>
      {valid ? <p className="mt-1 text-xs leading-snug text-ink-soft">{freshness}</p> : null}
    </div>
  );
}

export function ReadinessDetails({ readiness }: { readiness?: TodayReadiness | null }) {
  if (!readiness) return <p className="text-sm text-ink-soft">Данных для оценки восстановления нет.</p>;
  const drivers = readiness.drivers.length ? readiness.drivers : readiness.factors;
  return (
    <div className="space-y-3 text-sm text-ink-soft">
      <h3 className="font-medium text-ink">Показатели восстановления</h3>
      {readiness.freshness && readiness.freshness.state !== "fresh" ? (
        <div className="rounded-lg border border-tone-warning/30 bg-tone-warning/10 p-3">
          <p className="font-medium text-ink">{readiness.freshness.state === "data_gap"
            ? "Сегодняшнего измерения восстановления нет — оценка предварительная"
            : "Часть ночных измерений не подтверждена за сегодня"}</p>
          {readiness.freshness.blocked_reason ? <p className="mt-1">{blockedReasonLabels[readiness.freshness.blocked_reason] ?? "Недостаточно подтверждённых данных для изменения плана"}</p> : null}
        </div>
      ) : null}
      <ul className="divide-y divide-surface-border">
        {drivers.map((item, index) => {
          const driver = item as TodayReadinessDriver;
          const evidence = String(item.evidence ?? "");
          return evidence ? <li key={index} className="py-2.5">
            <p>{decisionText(evidence)}</p>
            <p className="mt-1 text-xs text-ink-soft">{observationDateLabel(driver)}</p>
          </li> : null;
        })}
      </ul>
      {readiness.tsb?.tsb != null && !drivers.some((item) => item.key === "tsb") ? (
        <p>Баланс нагрузки (TSB): {readiness.tsb.tsb}; базовая нагрузка (CTL): {readiness.tsb.ctl ?? "—"}; окно {readiness.tsb.window_days} дн.</p>
      ) : null}
      {readiness.freshness ? <p className="text-xs">{freshnessSummary(readiness.freshness)}</p> : null}
      {readiness.source_completeness != null ? <p className="text-xs">Полнота данных: {Math.round(readiness.source_completeness * 100)}%. Это не оценка их свежести.</p> : null}
    </div>
  );
}
