"use client";

import Link from "next/link";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { adherenceDayLabel, STATUS_META } from "@/lib/adherence";
import type { AdherenceRibbonResponse } from "@/lib/types";

/** Краткая сводка за неделю и доступные с клавиатуры/касанием детали каждого дня. */
export function AdherenceStrip() {
  const { data } = useSWR<AdherenceRibbonResponse>(
    "/api/adherence?weeks=1",
    fetcher,
  );
  if (!data?.has_plan || !data.days.length) return null;

  const week = data.weeks[0];
  return (
    <section
      aria-labelledby="today-week-title"
      className="rounded-card border border-surface-border bg-surface p-4 shadow-card"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="today-week-title" className="text-sm font-semibold text-ink">
          Неделя · план и факт
        </h2>
        <Link href="/adherence" className="text-xs text-ink-soft underline">
          вся лента
        </Link>
      </div>

      {week ? (
        <p className="mt-2 text-sm text-ink-soft">
          Сопоставлено занятий: {week.matched_sessions} из {week.planned_sessions}
          {" · "}план {Math.round(week.planned_tss)} TSS
          {" · "}по плану выполнено {Math.round(week.actual_tss)} TSS
          {week.unplanned_tss > 0
            ? ` · вне плана ${Math.round(week.unplanned_tss)} TSS`
            : ""}
        </p>
      ) : null}

      <ul className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-7">
        {data.days.map((day) => {
          const meta = STATUS_META[day.status] ?? STATUS_META.unknown;
          return (
            <li
              key={day.date}
              className="min-w-0 rounded-md border border-surface-border p-2"
            >
              <div className="text-xs font-medium text-ink">
                {adherenceDayLabel(day.date)}
              </div>
              <div className={`mt-1 text-xs font-medium ${meta.chip}`}>
                {meta.label}
              </div>
              <details className="mt-2 text-xs">
                <summary className="cursor-pointer rounded-sm text-ink-soft underline decoration-dotted underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent">
                  План и факт
                </summary>
                <dl className="mt-2 space-y-1 text-ink-soft">
                  <div className="flex justify-between gap-2">
                    <dt>План</dt>
                    <dd>{Math.round(day.planned_tss)} TSS</dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt>Факт по плану</dt>
                    <dd>{Math.round(day.matched_actual_tss)} TSS</dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt>Вне плана</dt>
                    <dd>{Math.round(day.unplanned_tss)} TSS</dd>
                  </div>
                  <div className="flex justify-between gap-2 border-t border-surface-border pt-1 font-medium text-ink">
                    <dt>Всего факт</dt>
                    <dd>{Math.round(day.actual_tss)} TSS</dd>
                  </div>
                </dl>
              </details>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
