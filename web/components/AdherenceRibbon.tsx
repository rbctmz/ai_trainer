"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { STATUS_META, adherenceDayLabel } from "@/lib/adherence";
import Link from "next/link";
import type {
  AdherenceDay,
  AdherenceDayStatus,
  AdherenceRibbonResponse,
  AdherenceWeek,
} from "@/lib/types";

// Shared «План vs факт» ribbon: one source consumed by BOTH the /adherence route
// (deep-link, out of the top nav since #253) and the «План vs факт» tab inside
// /planning (folded in #255). Statuses arrive READY from the API
// (models/adherence_ribbon.py) — the web never re-derives adherence itself.
export function AdherenceRibbon() {
  const { data, error, isLoading } = useSWR<AdherenceRibbonResponse>(
    "/api/adherence?weeks=4",
    fetcher,
  );

  return (
    <section>
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-semibold text-ink">План vs факт</h2>
        <span className="text-xs text-ink-faint">
          {data?.ribbon_rule_version ?? ""}
        </span>
      </div>
      <p className="mt-1 text-sm text-ink-soft">
        Как исполняется активный план: недельные сводки и лента последних недель
        по дням. Подтверждение матчей и корректировка — во вкладке
        «Скорректировать».
      </p>

      {isLoading ? (
        <p className="mt-6 text-sm text-ink-faint">Загрузка…</p>
      ) : error ? (
        <p className="mt-6 text-sm text-tone-danger">
          Не удалось загрузить ленту: {String(error)}
        </p>
      ) : !data?.has_plan ? (
        <p className="mt-6 text-sm text-ink-soft">
          Активного плана нет — лента появится после построения плана.
        </p>
      ) : (
        <>
          <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {data.weeks.map((week) => (
              <WeekCard key={week.week_start} week={week} />
            ))}
          </div>

          <div className="mt-6">
            <h3 className="text-sm font-semibold text-ink">Лента по дням</h3>
            <div className="mt-3 grid grid-cols-7 gap-1.5">
              {data.days.map((day) => (
                <DayCell key={day.date} day={day} />
              ))}
            </div>
            <div className="mt-4 flex flex-wrap gap-2 text-xs">
              {Object.entries(STATUS_META).map(([key, meta]) => (
                <span key={key} className={`rounded-full px-2 py-0.5 ${meta.chip}`}>
                  {meta.label}
                </span>
              ))}
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function WeekCard({ week }: { week: AdherenceWeek }) {
  const buckets = week.adherence ?? {};
  return (
    <div className="rounded-xl border border-surface-border bg-surface p-3">
      <div className="flex items-baseline justify-between">
        <span className="text-xs font-medium text-ink">
          Неделя {week.week_start.slice(8, 10)}.{week.week_start.slice(5, 7)}
        </span>
        <span className="text-xs text-ink-faint">
          {week.matched_sessions}/{week.planned_sessions} сессий
        </span>
      </div>
      <div className="mt-2 text-xs text-ink-soft">
        {Math.round(week.actual_tss)} / {Math.round(week.planned_tss)} TSS
        {week.unplanned_tss > 0
          ? ` · вне плана ${Math.round(week.unplanned_tss)}`
          : ""}
      </div>
      <div className="mt-2 flex flex-wrap gap-1">
        {Object.entries(buckets)
          .filter(([, count]) => count > 0)
          .map(([key, count]) => {
            const meta = STATUS_META[key as AdherenceDayStatus];
            return (
              <span
                key={key}
                className={`rounded-full px-1.5 py-0.5 text-[11px] ${meta ? meta.chip : "bg-surface-muted text-ink-faint"}`}
              >
                {meta ? meta.label : key} {count}
              </span>
            );
          })}
      </div>
      {week.missed_key_sessions.length > 0 ? (
        <div className="mt-2 text-[11px] text-tone-danger">
          Пропущены ключевые:{" "}
          {week.missed_key_sessions
            .map((item) => `${adherenceDayLabel(item.date)} (${item.role})`)
            .join(", ")}
        </div>
      ) : null}
    </div>
  );
}

function DayCell({ day }: { day: AdherenceDay }) {
  const meta = STATUS_META[day.status] ?? STATUS_META.rest;
  return (
    <Link
      href={`/planning?focus=${day.date}`}
      className={`rounded-lg p-2 text-center ${meta.chip}`}
      title={`${meta.label} · план ${Math.round(day.planned_tss)} TSS · факт ${Math.round(day.actual_tss)} TSS`}
    >
      <div className="text-[11px] font-medium">{adherenceDayLabel(day.date)}</div>
      <div className="mt-0.5 text-[11px]">
        {Math.round(day.actual_tss)}/{Math.round(day.planned_tss)}
      </div>
    </Link>
  );
}
