"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import type { TodayDecisionStory, TodayReadiness } from "@/lib/types";
import { decisionText, workoutLabel } from "./displayText";
import { ReadinessIndicator, ReadinessDetails } from "./ReadinessSummary";

type NextAction = TodayDecisionStory["next_action"];
const actionNames: Record<string, string> = {
  inspect_evidence: "Нужно уточнить данные",
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

// Only the known no-intervention boilerplate moves into disclosure. Other
// supplied messages and symptom caveats remain visible, including legacy payloads.
function actionNotice(nextAction: NextAction): string {
  if (nextAction.kind !== "follow_plan") return decisionText(nextAction.summary);
  const notice = nextAction.summary.replace(
    /Готовность \w+ \([\d.]+\/100\) не противоречит сессиям ближайших \d+ дн\. — вмешательство не требуется\./g, "",
  ).replace(/^Следуйте текущему плану(?: с учётом доступных данных)?\.\s*/, "").trim();
  if (!notice && nextAction.caveat === "no_current_injury_response") {
    return "Свежего ответа о травме нет; это не подтверждение отсутствия симптомов.";
  }
  return decisionText(notice);
}

export function TodayDecisionStoryCompact({ nextAction, readiness, sessionName, onExpand }: {
  nextAction: NextAction;
  readiness?: TodayReadiness | null;
  sessionName?: string;
  onExpand: () => void;
}) {
  const notice = actionNotice(nextAction);
  return (
    <section aria-label="Сводка на сегодня" className="min-w-0 rounded-card border border-surface-border bg-surface p-5 shadow-card">
      <div className="grid gap-4 sm:grid-cols-[1fr_160px]">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-ink-soft">Сегодня по плану</p>
          <h2 className="mt-2 text-xl font-semibold text-ink">{sessionName ? workoutLabel(sessionName) : "План на сегодня"}</h2>
          {notice ? <p className="mt-3 text-sm leading-relaxed text-ink-soft">{notice}</p> : null}
          <button type="button" onClick={onExpand} className="mt-4 text-sm font-medium text-accent">Показать тренировку и показатели</button>
        </div>
        <ReadinessIndicator readiness={readiness} />
      </div>
    </section>
  );
}

export function TodayDecisionStoryFull({ story, nextAction, readiness, workout }: {
  story: TodayDecisionStory;
  nextAction: NextAction;
  readiness?: TodayReadiness | null;
  workout?: ReactNode;
}) {
  const notice = actionNotice(nextAction);
  const needsAttention = nextAction.kind !== "follow_plan";
  const explanations = Array.from(new Set([
    nextAction.summary, story.interpretation.summary, story.recommendation.summary,
  ].map(decisionText).filter(Boolean))).filter((value, index, all) =>
    !all.some((other, otherIndex) => otherIndex !== index && other.length > value.length && other.includes(value)),
  );
  const detailExplanations = Array.from(new Set(explanations
    .map((value) => notice ? value.replace(notice, "").trim() : value)
    .filter(Boolean)));
  const completed = story.fact.completion_status === "complete" || story.fact.completion_status === "incomplete";
  const actualLoad = story.fact.actual.load_tss;
  return (
    <section aria-label="Сводка на сегодня" className="min-w-0 rounded-card border border-surface-border bg-surface p-5 shadow-card sm:p-6">
      {needsAttention ? (
        <div className="mb-5 rounded-xl border border-tone-warning/30 bg-tone-warning/10 p-4">
          <h2 className="text-lg font-semibold text-ink">{actionNames[nextAction.kind] ?? "Требуется внимание"}</h2>
          {notice ? <p className="mt-2 break-words text-sm leading-relaxed text-ink-soft">{notice}</p> : null}
          {nextAction.kind === "confirm_match" && nextAction.enabled ? (
            <Link href={story.fact.session_id ? `/planning?session_id=${encodeURIComponent(story.fact.session_id)}` : "/planning"} className="mt-3 inline-block rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-foreground">Уточнить выполненную тренировку</Link>
          ) : null}
        </div>
      ) : notice ? <p className="mb-4 text-sm leading-relaxed text-ink-soft">{notice}</p> : null}
      <div className="grid items-start gap-5 sm:grid-cols-[1fr_160px]">
        <div className="min-w-0">{workout}</div>
        <ReadinessIndicator readiness={readiness} />
      </div>
      {completed ? (
        <p className="mt-3 text-sm text-ink-soft">
          {story.fact.completion_status === "complete" ? "Тренировка выполнена." : "Тренировка выполнена частично."}
          {actualLoad != null ? ` Фактическая нагрузка: ${actualLoad} TSS.` : " Нагрузка выполненной тренировки неизвестна."}
        </p>
      ) : null}
      <details className="mt-5 border-t border-surface-border pt-3">
        <summary className="cursor-pointer text-sm font-medium text-accent">Показатели и объяснение</summary>
        <div className="mt-4"><ReadinessDetails readiness={readiness} /></div>
        {detailExplanations.length > 0 ? <div className="mt-4 border-t border-surface-border pt-3 text-sm leading-relaxed text-ink-soft">
          <h3 className="font-medium text-ink">Объяснение системы</h3>
          {detailExplanations.map((value) => <p key={value} className="mt-2 break-words">{value}</p>)}
        </div> : null}
        <ul className="mt-2 text-sm">{story.evidence.map((item, index) => <EvidenceRow key={index} item={item} />)}</ul>
      </details>
    </section>
  );
}
