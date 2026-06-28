"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { ActivitiesResponse } from "@/lib/types";

const sportLabels: Record<string, string> = {
  cycling: "вело",
  bike: "вело",
  ride: "вело",
  running: "бег",
  run: "бег",
  swimming: "плавание",
  swim: "плавание",
  walking: "ходьба",
  walk: "ходьба",
};

function sportLabel(s: string): string {
  return sportLabels[s.toLowerCase()] ?? s;
}

export default function ActivitiesPage() {
  const { data, error, isLoading } = useSWR<ActivitiesResponse>(
    "/api/activities?days=30",
    fetcher,
  );

  return (
    <main className="space-y-5">
      <h1 className="text-2xl font-bold text-ink">Активности</h1>

      {isLoading ? <div className="h-40 animate-pulse rounded-card bg-surface" /> : null}
      {error ? (
        <div className="rounded-card border border-red-200 bg-red-50 p-4 text-sm text-tone-danger">
          Не удалось загрузить активности. Запущен ли API на :8000?
        </div>
      ) : null}

      {data?.has_data ? (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Total label="Тренировок" value={`${data.totals.count ?? data.count}`} />
            <Total label="Дистанция" value={`${data.totals.distance_km ?? 0} км`} />
            <Total label="Время" value={`${data.totals.duration_hours ?? 0} ч`} />
            <Total label="Σ TSS" value={`${data.totals.tss ?? 0}`} />
          </div>

          <div className="overflow-hidden rounded-card border border-surface-border bg-surface shadow-card">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-surface-border text-left text-xs uppercase tracking-wide text-ink-faint">
                  <th className="px-4 py-2.5 font-medium">Дата</th>
                  <th className="px-4 py-2.5 font-medium">Спорт</th>
                  <th className="px-4 py-2.5 text-right font-medium">Мин</th>
                  <th className="hidden px-4 py-2.5 text-right font-medium sm:table-cell">Км</th>
                  <th className="px-4 py-2.5 text-right font-medium">TSS</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((a) => (
                  <tr
                    key={a.activity_id}
                    className="border-b border-surface-border last:border-0 hover:bg-surface-muted"
                  >
                    <td className="px-4 py-2.5 text-ink-soft">{a.date}</td>
                    <td className="px-4 py-2.5 text-ink">{sportLabel(a.sport)}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-ink">
                      {a.duration_minutes ?? "—"}
                    </td>
                    <td className="hidden px-4 py-2.5 text-right tabular-nums text-ink sm:table-cell">
                      {a.distance_km ?? "—"}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums font-medium text-ink">
                      {a.tss ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}

      {data && !data.has_data ? (
        <div className="rounded-card border border-surface-border bg-surface p-6 text-center shadow-card">
          <div className="text-lg font-semibold text-ink">Нет активностей</div>
          <p className="mt-1 text-sm text-ink-soft">Синхронизируйте Garmin, чтобы увидеть тренировки.</p>
        </div>
      ) : null}
    </main>
  );
}

function Total({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-card border border-surface-border bg-surface p-4 shadow-card">
      <div className="text-xs font-medium uppercase tracking-wide text-ink-faint">
        {label}
      </div>
      <div className="mt-1 text-xl font-bold text-ink">{value}</div>
    </div>
  );
}
