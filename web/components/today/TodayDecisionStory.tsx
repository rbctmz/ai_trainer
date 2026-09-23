"use client";

import type { TodayDecisionStory } from "@/lib/types";

type NextAction = TodayDecisionStory["next_action"];

const evidenceNames: Record<string, string> = {
  session: "Сессия",
  readiness: "Готовность",
  subjective_wellness: "Самооценка травмы",
};

const completionNames: Record<TodayDecisionStory["fact"]["completion_status"], string> = {
  complete: "выполнено",
  incomplete: "не полностью выполнено",
  needs_confirmation: "нужно подтвердить сопоставление",
  not_observed: "данных о выполнении нет",
};

function visibleValue(value: unknown): string | null {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return null;
}

function EvidenceRow({ item }: { item: Record<string, unknown> }) {
  const kind = visibleValue(item.kind) ?? "unknown";
  const label = evidenceNames[kind] ?? "Данные";
  const detail = visibleValue(item.value_label) ?? visibleValue(item.status);
  const source = visibleValue(item.source);
  const date = visibleValue(item.observation_date);
  const freshness = visibleValue(item.freshness);
  const revision = visibleValue(item.ref);

  return (
    <li className="min-w-0 rounded-lg bg-surface-muted p-3 text-sm">
      <p className="font-medium text-ink">{label}</p>
      {detail ? <p className="mt-1 text-ink-soft">{detail}</p> : null}
      <p className="mt-1 break-words text-xs text-ink-faint">
        {[
          source ? `источник: ${source}` : null,
          date ? `наблюдение: ${date}` : null,
          freshness ? `свежесть: ${freshness}` : null,
          revision ? `ссылка: ${revision}` : null,
        ]
          .filter(Boolean)
          .join(" · ")}
      </p>
    </li>
  );
}

export function TodayDecisionStoryCompact({
  nextAction,
  onExpand,
}: {
  nextAction: NextAction;
  onExpand: () => void;
}) {
  return (
    <section
      aria-labelledby="today-decision-compact-title"
      className="min-w-0 rounded-card border border-surface-border bg-surface p-4 shadow-card"
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-ink-faint">
        Сегодня · следующий шаг
      </p>
      <h2 id="today-decision-compact-title" className="mt-1 break-words text-base font-semibold text-ink">
        {nextAction.summary}
      </h2>
      <button
        type="button"
        onClick={onExpand}
        className="mt-3 text-sm font-medium text-accent"
      >
        Развернуть брифинг
      </button>
    </section>
  );
}

export function TodayDecisionStoryFull({
  story,
  nextAction,
}: {
  story: TodayDecisionStory;
  nextAction: NextAction;
}) {
  const planName = visibleValue(story.fact.plan.name) ?? "Сессия не указана";
  const plannedLoad = visibleValue(story.fact.plan.load_tss);
  const actualLoad = visibleValue(story.fact.actual.load_tss);
  const loadDelta = visibleValue(story.fact.deviation.load_delta_tss);
  const hasAttributedFact = !["not_observed", "needs_confirmation"].includes(
    story.fact.completion_status,
  );
  const versions = Object.entries(story.interpretation.rule_versions)
    .map(([key, value]) => [key, visibleValue(value)] as const)
    .filter((entry): entry is readonly [string, string] => entry[1] !== null);

  return (
    <section
      aria-labelledby="today-decision-title"
      className="min-w-0 rounded-card border border-surface-border bg-surface p-4 shadow-card"
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-ink-faint">
        Сегодня · решение
      </p>
      <h2 id="today-decision-title" className="mt-1 text-lg font-semibold text-ink">
        Следующее действие
      </h2>
      <p className="mt-1 break-words text-sm text-ink">{nextAction.summary}</p>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div className="min-w-0 rounded-lg bg-surface-muted p-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-faint">Что известно</h3>
          <p className="mt-1 break-words text-sm font-medium text-ink">{planName}</p>
          <p className="mt-1 text-xs text-ink-soft">
            План: {plannedLoad ? `${plannedLoad} TSS` : "нагрузка неизвестна"}
            {" · "}Факт: {hasAttributedFact
              ? actualLoad ? `${actualLoad} TSS` : "нагрузка неизвестна"
              : "нет подтверждённых данных"}
          </p>
          <p className="mt-1 text-xs text-ink-faint">
            Выполнение: {completionNames[story.fact.completion_status]}
            {hasAttributedFact && loadDelta ? ` · отклонение: ${loadDelta} TSS` : ""}
          </p>
        </div>
        <div className="min-w-0 rounded-lg bg-surface-muted p-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-faint">Почему</h3>
          <p className="mt-1 break-words text-sm text-ink-soft">{story.interpretation.summary}</p>
        </div>
      </div>

      <div className="mt-3 border-t border-surface-border pt-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-faint">Рекомендация</h3>
        <p className="mt-1 break-words text-sm text-ink-soft">{story.recommendation.summary}</p>
      </div>

      <details className="mt-3 border-t border-surface-border pt-3">
        <summary className="cursor-pointer text-sm font-medium text-accent">
          Доказательства и версии правил
        </summary>
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">
          {story.evidence.map((item, index) => (
            <EvidenceRow key={`${String(item.kind ?? "evidence")}-${index}`} item={item} />
          ))}
        </ul>
        <p className="mt-3 break-words text-xs text-ink-faint">
          Версия истории: {story.schema_version}
          {versions.map(([key, value]) => ` · ${key}: ${value}`).join("")}
        </p>
      </details>
    </section>
  );
}
