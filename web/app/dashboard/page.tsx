"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { DashboardResponse } from "@/lib/types";
import { StatusRow } from "@/components/dashboard/StatusRow";
import { TodayCard } from "@/components/dashboard/TodayCard";
import { WeekCard } from "@/components/dashboard/WeekCard";
import { WeekStrip } from "@/components/dashboard/WeekStrip";

export default function DashboardPage() {
  const { data, error, isLoading } = useSWR<DashboardResponse>(
    "/api/dashboard/summary",
    fetcher,
    { refreshInterval: 5 * 60 * 1000 }, // revalidate every 5 min (per spec)
  );

  return (
    <main className="space-y-5">
      <header className="flex items-baseline justify-between">
        <h1 className="text-2xl font-bold text-ink">Дашборд</h1>
        {data?.summary ? (
          <span className="text-sm text-ink-faint">
            {data.summary.today.date}
          </span>
        ) : null}
      </header>

      {isLoading ? <SkeletonState /> : null}

      {error ? (
        <div className="rounded-card border border-red-200 bg-red-50 p-4 text-sm text-tone-danger">
          Не удалось загрузить данные. Запущен ли API на :8000?
        </div>
      ) : null}

      {data && !data.has_data ? (
        <div className="rounded-card border border-surface-border bg-surface p-6 text-center shadow-card">
          <div className="text-lg font-semibold text-ink">Нет данных</div>
          <p className="mt-1 text-sm text-ink-soft">
            Синхронизируйте Garmin или включите демо-режим, чтобы увидеть метрики.
          </p>
        </div>
      ) : null}

      {data?.summary ? (
        <>
          <StatusRow today={data.summary.today} />
          <div className="grid gap-4 sm:grid-cols-2">
            <TodayCard
              workout={data.summary.workout}
              today={data.summary.today}
            />
            <WeekCard week={data.summary.week} plan={data.summary.plan} />
          </div>
          <WeekStrip days={data.summary.next_days} />
        </>
      ) : null}
    </main>
  );
}

function SkeletonState() {
  return (
    <div className="space-y-3">
      <div className="h-20 animate-pulse rounded-card bg-surface" />
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="h-40 animate-pulse rounded-card bg-surface" />
        <div className="h-40 animate-pulse rounded-card bg-surface" />
      </div>
    </div>
  );
}
