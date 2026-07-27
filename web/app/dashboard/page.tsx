"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { fetcher, isDemo, postJSON, setDemo } from "@/lib/api";
import { DashboardResponse, DashboardWidgets } from "@/lib/types";
import { StatusRow } from "@/components/dashboard/StatusRow";
import { TodayCard } from "@/components/dashboard/TodayCard";
import { WeekCard } from "@/components/dashboard/WeekCard";
import { WeekStrip } from "@/components/dashboard/WeekStrip";
import { DailyOutlook } from "@/components/dashboard/DailyOutlook";
import { TrainingScore } from "@/components/dashboard/TrainingScore";
import { SleepWidget } from "@/components/dashboard/SleepWidget";
import { RaceProjection } from "@/components/dashboard/RaceProjection";
import { AthleteProfileCard } from "@/components/dashboard/AthleteProfileCard";
import { SyncControl } from "@/components/sync/SyncControl";

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
        <h1 className="text-2xl font-bold text-ink">Обзор</h1>
        <div className="flex items-center gap-3">
          {data?.summary ? (
            <span className="text-sm text-ink-faint">{data.summary.today.date}</span>
          ) : null}
          <SyncControl onDone={() => mutate()} />
        </div>
      </header>

      <SectionLinks />

      {isLoading ? <SkeletonState /> : null}

      {error ? (
        <div className="rounded-card border border-tone-danger/30 bg-tone-danger/10 p-4 text-sm text-tone-danger">
          Не удалось загрузить данные. Проверьте, что ./run_web.sh запущен.
        </div>
      ) : null}

      {data && !data.has_data ? <Onboarding /> : null}

      {data?.summary ? (
        <>
          <StatusRow today={data.summary.today} />

          {widgets?.daily_outlook && (
            <DailyOutlook data={widgets.daily_outlook} />
          )}

          {widgets && (
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-4">
                <SleepWidget className="flex-1" />
                {widgets.race_projection && (
                  <RaceProjection data={widgets.race_projection} />
                )}
              </div>
              <div className="flex flex-col gap-4">
                {widgets.training_score && (
                  <TrainingScore data={widgets.training_score} />
                )}
                <AthleteProfileCard />
              </div>
            </div>
          )}

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

// Secondary detail surfaces, demoted from the top nav into «Обзор» (#253).
// The raw-data drilldowns (Активности/Сон/HRV) are no longer peer primary
// destinations; they live here as sections reachable from the overview.
function SectionLinks() {
  const sections = [
    { href: "/activities", label: "Активности" },
    { href: "/sleep", label: "Сон" },
    { href: "/hrv", label: "HRV" },
  ];
  return (
    <nav aria-label="Разделы обзора" className="flex flex-wrap items-center gap-2">
      <span className="text-xs font-medium uppercase tracking-wide text-ink-faint">
        Разделы
      </span>
      {sections.map((s) => (
        <Link
          key={s.href}
          href={s.href}
          className="rounded-lg border border-surface-border px-3 py-1.5 text-sm font-medium text-ink-soft transition hover:bg-surface-muted"
        >
          {s.label}
        </Link>
      ))}
    </nav>
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
        Данных пока нет. Выберите настроенный источник и загрузите активности.
        Для старта через Intervals.icu нужен <code>INTERVALS_ICU_API_KEY</code> в{" "}
        <code>.env</code>. Также можно попробовать безопасный демо-набор.
      </p>
      <SyncControl detailed onDone={() => window.location.reload()} />
      <div className="mt-4 flex flex-wrap justify-center gap-3">
        <button
          type="button"
          onClick={tryDemo}
          disabled={busy}
          className="rounded-lg bg-accent px-5 py-2 text-sm font-medium text-accent-foreground transition hover:bg-accent/90 disabled:opacity-50"
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
