"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { CoachDecisionsResponse } from "@/lib/types";
import { DecisionEntry } from "@/components/ui/DecisionEntry";

export default function DecisionsPage() {
  const { data, error, isLoading } = useSWR<CoachDecisionsResponse>(
    "/api/decisions?days=30",
    fetcher,
  );

  return (
    <main className="space-y-5">
      <h1 className="text-2xl font-bold text-ink">Решения коуча</h1>

      {isLoading ? <div className="h-40 animate-pulse rounded-card bg-surface" /> : null}
      {error ? (
        <div className="rounded-card border border-tone-danger/30 bg-tone-danger/10 p-4 text-sm text-tone-danger">
          Не удалось загрузить решения. Запущен ли API на :8000?
        </div>
      ) : null}

      {data?.has_data ? (
        <div className="space-y-4">
          {data.days.map((day) => (
            <section
              key={day.date}
              className="rounded-card border border-surface-border bg-surface p-4 shadow-card"
            >
              <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">
                {day.date}
              </h2>
              <div className="mt-2">
                {day.decisions.map((decision) => (
                  <DecisionEntry key={decision.id} decision={decision} />
                ))}
              </div>
            </section>
          ))}
        </div>
      ) : null}

      {data && !data.has_data ? (
        <div className="rounded-card border border-surface-border bg-surface p-6 text-center text-sm text-ink-soft shadow-card">
          No decisions logged yet
        </div>
      ) : null}
    </main>
  );
}
