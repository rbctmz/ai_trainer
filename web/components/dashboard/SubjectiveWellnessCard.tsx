import type { SubjectiveWellness } from "@/lib/types";

/** Provider labels and freshness come from the shared API projection. */
export function SubjectiveWellnessCard({ data }: { data?: SubjectiveWellness | null }) {
  if (!data) return null;
  const status = data.status === "current"
    ? "За сегодня"
    : data.status === "stale"
      ? "Прошлая запись — за сегодня ответов нет"
      : data.status === "unavailable"
        ? "Не удалось получить оценки"
        : "Оценок нет";
  return (
    <section aria-label="Самочувствие из Intervals.icu" className="rounded-card border border-surface-border bg-surface p-4">
      <h2 className="text-base font-semibold text-ink">Самочувствие из Intervals.icu</h2>
      <p className="mt-1 text-sm text-ink-soft">
        {status}{data.date ? <> · <time dateTime={data.date}>{data.date}</time></> : null}
      </p>
      {data.items.length > 0 ? (
        <dl className="mt-3 grid gap-x-5 gap-y-3 sm:grid-cols-2">
          {data.items.map((item) => (
            <div key={item.key}>
              <dt className="text-xs text-ink-faint">{item.label}</dt>
              <dd className="text-sm text-ink">{item.value_label}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      <p className="mt-3 text-xs text-ink-faint">
        Дневные оценки из источника. Время ответа не известно.
      </p>
    </section>
  );
}
