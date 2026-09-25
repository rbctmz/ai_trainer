"use client";

import Link from "next/link";
import type { TodayDecisionStory, TodayReadiness } from "@/lib/types";
import { decisionText } from "./displayText";

type NextAction = TodayDecisionStory["next_action"];
const actionNames: Record<string, string> = {
  follow_plan: "План остаётся без изменений",
  inspect_evidence: "Перед тренировкой нужно уточнение",
  confirm_match: "Уточните, какая тренировка выполнена",
  review_proposal: "Есть предложение изменить план",
  sync_or_wait: "Нужны свежие данные",
  open_planning: "Начните с плана тренировок",
};
const statusNames: Record<string, string> = {
  ready: "Нормальная", optimal: "Оптимальная", reduced: "Сниженная", low: "Низкая",
  critical: "Критически низкая", unknown: "Не определена", data_gap: "Недостаточно данных",
  matched: "Выполненная тренировка связана с планом", partial: "Выполнена часть тренировки",
  needs_confirmation: "Нужно уточнить связь с планом", unmatched: "Выполнение не найдено",
};
const freshnessNames: Record<string, string> = {
  current: "Актуальные данные", stale: "Данные устарели", unknown: "Актуальность не подтверждена",
  missing: "Нет данных", unavailable: "Данные недоступны",
};
function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}
function dateLabel(value: string): string {
  const date = new Date(`${value}T12:00:00`);
  return Number.isNaN(date.getTime()) ? "Дата неизвестна" : date.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
}
function EvidenceRow({ item }: { item: Record<string, unknown> }) {
  const kind = text(item.kind) ?? "unknown";
  const label = ({ session: "Выполнение тренировки", readiness: "Оценка восстановления", subjective_wellness: "Самооценка травмы" } as Record<string, string>)[kind] ?? "Данные";
  const status = text(item.status);
  const detail = text(item.value_label) ?? (status ? statusNames[status] ?? "Оценка не определена" : null);
  const source = ({ intervals: "Intervals.icu", garmin: "Garmin", canonical_snapshot: "Сводная оценка восстановления", session_projection: "План и загруженные активности" } as Record<string, string>)[String(item.source)] ?? "Источник не указан";
  const date = text(item.observation_date);
  const freshness = freshnessNames[String(item.freshness)] ?? "Актуальность не подтверждена";
  return (
    <li className="min-w-0 border-t border-surface-border py-3 first:border-0">
      <div className="flex flex-wrap justify-between gap-x-4 gap-y-1">
        <p className="font-medium text-ink">{label}</p>
        {detail ? <p className="text-ink-soft">{detail}</p> : null}
      </div>
      <p className="mt-1 text-xs text-ink-faint">{source} · {date ? dateLabel(date) : "Дата неизвестна"} · {freshness}</p>
    </li>
  );
}

export function TodayDecisionStoryCompact({ nextAction, onExpand }: { nextAction: NextAction; onExpand: () => void }) {
  return (
    <section aria-label="Решение на сегодня" className="min-w-0 rounded-card border border-surface-border bg-surface p-5 shadow-card">
      <h2 className="text-xl font-semibold text-ink">{actionNames[nextAction.kind] ?? "Решение на сегодня"}</h2>
      <p className="mt-2 break-words text-sm leading-relaxed text-ink-soft">{decisionText(nextAction.summary)}</p>
      <button type="button" onClick={onExpand} className="mt-3 text-sm font-medium text-accent">Показать тренировку и объяснение</button>
    </section>
  );
}

export function TodayDecisionStoryFull({ story, nextAction, readiness }: { story: TodayDecisionStory; nextAction: NextAction; readiness?: TodayReadiness | null }) {
  // Deduplicate only identical explanations; distinct server facts and caveats survive.
  const explanations = Array.from(new Set([
    nextAction.summary, story.interpretation.summary, story.recommendation.summary,
  ].map(decisionText).filter(Boolean))).filter((value, index, all) =>
    !all.some((other, otherIndex) => otherIndex !== index && other.length > value.length && other.includes(value)),
  );
  const completed = story.fact.completion_status === "complete" || story.fact.completion_status === "incomplete";
  const actualLoad = story.fact.actual.load_tss;
  const drivers = readiness?.drivers.length ? readiness.drivers : readiness?.factors ?? [];
  return (
    <section aria-label="Решение на сегодня" className="min-w-0 rounded-card border border-surface-border bg-surface p-5 shadow-card sm:p-6">
      <p className="text-xs font-semibold uppercase tracking-wide text-ink-faint">Решение на сегодня</p>
      <h2 className="mt-2 text-xl font-semibold leading-snug text-ink sm:text-2xl">{actionNames[nextAction.kind] ?? "Следующий шаг"}</h2>
      <div className="mt-3 space-y-2 text-sm leading-relaxed text-ink-soft">
        {explanations.map((value) => <p key={value} className="break-words">{value}</p>)}
      </div>
      {completed ? (
        <p className="mt-3 text-sm text-ink-soft">
          {story.fact.completion_status === "complete" ? "Тренировка выполнена." : "Тренировка выполнена частично."}
          {actualLoad != null ? ` Фактическая нагрузка: ${actualLoad} TSS.` : " Нагрузка выполненной тренировки неизвестна."}
        </p>
      ) : null}
      {nextAction.kind === "confirm_match" && nextAction.enabled ? (
        <Link href={story.fact.session_id ? `/planning?session_id=${encodeURIComponent(story.fact.session_id)}` : "/planning"} className="mt-4 inline-block rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-foreground">Уточнить выполненную тренировку</Link>
      ) : null}
      <details className="mt-4 border-t border-surface-border pt-3">
        <summary className="cursor-pointer text-sm font-medium text-accent">На каких данных основано</summary>
        {drivers.length > 0 ? (
          <div className="mt-4 text-sm text-ink-soft">
            <h3 className="font-medium text-ink">Что входит в оценку восстановления</h3>
            <ul className="mt-2 list-disc space-y-1 pl-5">
              {drivers.map((driver, index) => driver.evidence ? <li key={index}>{decisionText(String(driver.evidence))}</li> : null)}
            </ul>
          </div>
        ) : null}
        <ul className="mt-2 text-sm">{story.evidence.map((item, index) => <EvidenceRow key={index} item={item} />)}</ul>
      </details>
    </section>
  );
}
