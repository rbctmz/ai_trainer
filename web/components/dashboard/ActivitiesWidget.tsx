"use client";

import Link from "next/link";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { ActivitiesResponse } from "@/lib/types";

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-surface-border bg-surface px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-ink-faint">{label}</div>
      <div className="mt-0.5 text-sm font-semibold tabular-nums text-ink">{value}</div>
    </div>
  );
}

/** Meaningful entry card to /activities with server-computed 30-day totals. */
export function ActivitiesWidget({ className = "" }: { className?: string }) {
  const { data, isLoading } = useSWR<ActivitiesResponse>(
    "/api/activities?days=30",
    fetcher,
  );

  if (isLoading) {
    return (
      <div
        className={`rounded-card border border-surface-border bg-surface p-4 shadow-card animate-pulse h-24 ${className}`}
      />
    );
  }

  const totals = data?.totals;
  const count = totals?.count ?? data?.count ?? 0;
  const distance = totals?.distance_km ?? 0;
  const duration = totals?.duration_hours ?? 0;
  const tss = totals?.tss ?? 0;

  return (
    <Link
      href="/activities"
      className={`block rounded-card border border-surface-border bg-surface p-4 shadow-card transition hover:border-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${className}`}
    >
      <div className="text-xs font-medium uppercase tracking-wide text-ink-faint">
        Активности
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Тренировок" value={`${count}`} />
        <Stat label="Дистанция" value={`${distance} км`} />
        <Stat label="Время" value={`${duration} ч`} />
        <Stat label="Σ TSS" value={`${tss}`} />
      </div>
      <div className="mt-3 text-xs font-medium text-tone-neutral">Подробнее →</div>
    </Link>
  );
}
