"use client";

import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { fetcher, isDemo, postJSON, setDemo } from "@/lib/api";
import { DashboardResponse, DashboardWidgets, SyncResult } from "@/lib/types";
import { StatusRow } from "@/components/dashboard/StatusRow";
import { TodayCard } from "@/components/dashboard/TodayCard";
import { WeekCard } from "@/components/dashboard/WeekCard";
import { WeekStrip } from "@/components/dashboard/WeekStrip";
import { DailyOutlook } from "@/components/dashboard/DailyOutlook";
import { TrainingScore } from "@/components/dashboard/TrainingScore";
import { SleepWidget } from "@/components/dashboard/SleepWidget";
import { RaceProjection } from "@/components/dashboard/RaceProjection";

export default function DashboardPage() {
  const { data, error, isLoading, mutate } = useSWR<DashboardResponse>(
    "/api/dashboard/summary",
    fetcher,
    { refreshInterval: 5 * 60 * 1000 },
  );

  const { data: widgets } = useSWR<DashboardWidgets>(
    data?.has_data ? "/api/dashboard/widgets" : null,
    fetcher,
    { refreshInterval: 5 * 60 * 1000 },
  );

  return (
    <main className="space-y-5">
      <header className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-ink">Дашборд</h1>
        <div className="flex items-center gap-3">
          {data?.summary ? (
            <span className="text-sm text-ink-faint">{data.summary.today.date}</span>
          ) : null}
          <SyncButton onDone={() => mutate()} />
        </div>
      </header>

      {isLoading ? <SkeletonState /> : null}

      {error ? (
        <div className="rounded-card border border-red-200 bg-red-50 p-4 text-sm text-tone-danger">
          Не удалось загрузить данные. Запущен ли API на :8000?
        </div>
      ) : null}

      {data && !data.has_data ? <Onboarding /> : null}

      {data?.summary ? (
        <>
          <StatusRow today={data.summary.today} />

          {widgets?.daily_outlook && (
            <DailyOutlook data={widgets.daily_outlook} />
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <TodayCard
              workout={data.summary.workout}
              today={data.summary.today}
            />
            <WeekCard week={data.summary.week} plan={data.summary.plan} />
          </div>

          <WeekStrip days={data.summary.next_days} />

          {widgets && (
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-4">
                <SleepWidget />
                {widgets.race_projection && (
                  <RaceProjection data={widgets.race_projection} />
                )}
              </div>
              <TrainingScore data={widgets.training_score} />
            </div>
          )}
        </>
      ) : null}
    </main>
  );
}

function SyncButton({ onDone }: { onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const { mutate } = useSWRConfig();

  async function sync() {
    setBusy(true);
    setMsg(null);
    try {
      const r = await postJSON<SyncResult>("/api/sync", {});
      setMsg(r.title || "Готово");
      onDone();
      mutate(() => true); // refresh all SWR keys
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Ошибка синхронизации");
    } finally {
      setBusy(false);
      setTimeout(() => setMsg(null), 6000);
    }
  }

  return (
    <div className="flex items-center gap-2">
      {msg ? <span className="hidden text-xs text-ink-faint sm:inline">{msg}</span> : null}
      <button
        type="button"
        onClick={sync}
        disabled={busy}
        className="rounded-lg border border-surface-border px-3 py-1.5 text-sm font-medium text-ink-soft transition hover:bg-surface-muted disabled:opacity-50"
        title="Синхронизировать с Garmin Connect"
      >
        {busy ? "Синхронизирую…" : "🔄 Синк"}
      </button>
    </div>
  );
}

function Onboarding() {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function tryDemo() {
    setBusy(true);
    setErr(null);
    try {
      await postJSON("/api/demo/seed", {});
      setDemo(true);
      window.location.reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Не удалось включить демо");
      setBusy(false);
    }
  }

  return (
    <div className="rounded-card border border-surface-border bg-surface p-8 text-center shadow-card">
      <div className="text-3xl">👋</div>
      <h2 className="mt-2 text-lg font-semibold text-ink">Добро пожаловать в AI Trainer</h2>
      <p className="mx-auto mt-1 max-w-md text-sm text-ink-soft">
        Данных пока нет. Синхронизируйтесь с Garmin, чтобы загрузить тренировки и
        метрики, или попробуйте демо на безопасном тестовом наборе.
      </p>
      <div className="mt-5 flex flex-wrap justify-center gap-3">
        <SyncButton onDone={() => window.location.reload()} />
        <button
          type="button"
          onClick={tryDemo}
          disabled={busy}
          className="rounded-lg bg-ink px-5 py-2 text-sm font-medium text-white transition hover:bg-ink/90 disabled:opacity-50"
        >
          {busy ? "Готовлю демо…" : "🎮 Попробовать демо"}
        </button>
      </div>
      {isDemo() ? (
        <p className="mt-3 text-xs text-tone-warning">Демо-режим включён — данные изолированы.</p>
      ) : null}
      {err ? <p className="mt-3 text-xs text-tone-danger">{err}</p> : null}
    </div>
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
