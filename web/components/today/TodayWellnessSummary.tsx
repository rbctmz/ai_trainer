import type { SubjectiveWellness } from "@/lib/types";

const statusLabels: Record<SubjectiveWellness["status"], string> = {
  current: "Ответы за сегодня",
  stale: "Прошлая запись — за сегодня ответов нет",
  missing: "Ответов нет",
  unavailable: "Оценки недоступны",
};

/** Today-specific compact view; values and their interpretation stay server-owned. */
export function TodayWellnessSummary({ data }: { data?: SubjectiveWellness | null }) {
  if (!data) return null;
  const source = data.source === "intervals" ? "Intervals.icu" : "Источник не указан";
  return (
    <section aria-label="Самочувствие из Intervals.icu" className="rounded-card border border-surface-border bg-surface p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 className="text-base font-semibold text-ink">Самочувствие</h2>
        <p className="text-sm text-ink-soft">
          {statusLabels[data.status]}
          {data.date ? <> · <time dateTime={data.date}>{data.date}</time></> : " · Дата неизвестна"}
          {data.status === "stale" && data.age_days != null ? ` · ${data.age_days} дн. назад` : ""}
        </p>
      </div>
      {data.items.length ? (
        <dl className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {data.items.map((item) => (
            <div key={item.key} className="min-w-0 rounded-lg bg-surface-muted px-3 py-2">
              <dt className="break-words text-xs text-ink-soft">{item.label}</dt>
              <dd className="mt-0.5 break-words text-sm font-medium text-ink">
                {item.value_label || (item.state === "missing" ? "Нет данных" : item.state === "invalid" ? "Значение некорректно" : "Не указано")}
              </dd>
            </div>
          ))}
        </dl>
      ) : <p className="mt-3 text-sm text-ink-soft">Показатели самочувствия не предоставлены.</p>}
      <details className="mt-3 border-t border-surface-border pt-2">
        <summary className="cursor-pointer rounded text-xs text-ink-soft focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
          Об источнике данных
        </summary>
        <p className="mt-2 text-xs text-ink-soft">
          Источник: {source}. Время ответа неизвестно.
        </p>
      </details>
    </section>
  );
}
