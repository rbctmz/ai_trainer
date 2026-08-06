"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { Activity, ActivitiesResponse, AthleteProfileResponse } from "@/lib/types";
import { DrillDownHeader } from "@/components/ui/DrillDownHeader";

const TSS_SOURCE_LABELS: Record<string, string> = {
  power: "по мощности",
  pace: "по темпу",
  heart_rate: "по пульсу",
  heuristic: "оценочно",
};

function formatCssPace(secondsPer100m: number): string {
  const rounded = Math.round(secondsPer100m);
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, "0")}/100м`;
}

function tssProvenanceLabel(activity: Activity): string | null {
  const sourceLabel = activity.tss_source ? TSS_SOURCE_LABELS[activity.tss_source] : null;
  if (!sourceLabel) return null;
  if (activity.tss_source === "power" && activity.tss_ftp_used != null) {
    return `${sourceLabel}, FTP ${Math.round(activity.tss_ftp_used)}`;
  }
  if (activity.tss_source === "pace" && activity.tss_pace_used != null) {
    return `${sourceLabel}, CSS ${formatCssPace(activity.tss_pace_used)}`;
  }
  return sourceLabel;
}

function ftpDriftHint(
  activity: Activity,
  profileFtp: number | null | undefined,
): string | null {
  if (
    activity.tss_source !== "power" ||
    activity.tss_ftp_used == null ||
    activity.tss_ftp_used <= 0 ||
    profileFtp == null ||
    profileFtp <= 0
  ) {
    return null;
  }
  const used = activity.tss_ftp_used;
  const base = Math.min(used, profileFtp);
  const pct = (Math.abs(profileFtp - used) / base) * 100;
  if (pct < 10) {
    return null;
  }
  return `FTP профиля сейчас ${Math.round(profileFtp)} Вт, эта активность посчитана по ${Math.round(used)} Вт`;
}

export default function ActivitiesPage() {
  const { data, error, isLoading } = useSWR<ActivitiesResponse>(
    "/api/activities?days=30",
    fetcher,
  );
  const { data: profileData } = useSWR<AthleteProfileResponse>(
    "/api/athlete-profile",
    fetcher,
  );

  return (
    <main className="space-y-5">
      <DrillDownHeader title="Активности" />

      {isLoading ? <div className="h-40 animate-pulse rounded-card bg-surface" /> : null}
      {error ? (
        <div className="rounded-card border border-tone-danger/30 bg-tone-danger/10 p-4 text-sm text-tone-danger">
          Не удалось загрузить активности. Проверьте, что ./run_web.sh запущен.
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

          <div className="overflow-x-auto rounded-card border border-surface-border bg-surface shadow-card">
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
                    <td className="px-4 py-2.5 text-ink-soft">{a.date_label ?? a.date}</td>
                    <td className="px-4 py-2.5 text-ink">{a.sport_label ?? a.sport}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-ink">
                      {a.duration_minutes ?? "—"}
                    </td>
                    <td className="hidden px-4 py-2.5 text-right tabular-nums text-ink sm:table-cell">
                      {a.distance_km ?? "—"}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums font-medium text-ink">
                      {a.tss ?? "—"}
                      {tssProvenanceLabel(a) ? (
                        <div className="text-[11px] font-normal normal-case tabular-nums text-ink-faint">
                          {tssProvenanceLabel(a)}
                        </div>
                      ) : null}
                      {ftpDriftHint(a, profileData?.profile?.ftp) ? (
                        <div className="text-[11px] font-normal normal-case text-tone-warning">
                          {ftpDriftHint(a, profileData?.profile?.ftp)}
                        </div>
                      ) : null}
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
          <p className="mt-1 text-sm text-ink-soft">
            Синхронизируйте настроенный источник, чтобы увидеть тренировки.
          </p>
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
