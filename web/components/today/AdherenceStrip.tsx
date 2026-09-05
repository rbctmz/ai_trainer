"use client";

import Link from "next/link";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { STATUS_META } from "@/lib/adherence";
import type { AdherenceRibbonResponse } from "@/lib/types";

/** Компактная 7-дневная строка «план vs факт» для /today (Issue #228).
 *
 * Статусы дней приезжают готовыми из /api/adherence — строка ничего не
 * пере-выводит, только раскрашивает и ведёт на полную ленту /adherence.
 */
export function AdherenceStrip() {
  const { data } = useSWR<AdherenceRibbonResponse>(
    "/api/adherence?weeks=1",
    fetcher,
  );
  if (!data?.has_plan || !data.days.length) return null;

  return (
    <section className="rounded-card border border-surface-border bg-surface p-4 shadow-card">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-ink">Неделя · план vs факт</h2>
        <Link href="/adherence" className="text-xs text-ink-faint underline">
          вся лента
        </Link>
      </div>
      <div className="mt-3 grid grid-cols-7 gap-1">
        {data.days.map((day) => {
          const meta = STATUS_META[day.status] ?? STATUS_META.rest;
          return (
            <div
              key={day.date}
              className={`rounded-md px-1 py-1.5 text-center text-[10px] ${meta.chip}`}
              title={`${day.date} · ${meta.label} · план ${Math.round(day.planned_tss)} TSS · факт ${Math.round(day.actual_tss)} TSS = сопоставлено ${Math.round(day.matched_actual_tss)} + вне плана ${Math.round(day.unplanned_tss)}`}
            >
              {day.date.slice(8, 10)}
            </div>
          );
        })}
      </div>
    </section>
  );
}
