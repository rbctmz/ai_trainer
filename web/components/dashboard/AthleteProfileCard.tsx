"use client";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { dataSourceLabel } from "@/lib/sourceLabels";
import { AthleteProfileResponse } from "@/lib/types";

function formatSyncedAt(value: string | null): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" });
}

function formatPace(secondsPerKm: number | null | undefined): string {
  if (
    secondsPerKm == null ||
    !Number.isFinite(secondsPerKm) ||
    secondsPerKm <= 0
  ) {
    return "—";
  }
  const rounded = Math.round(secondsPerKm);
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, "0")}/км`;
}

export function AthleteProfileCard({ className = "" }: { className?: string }) {
  const { data, isLoading } = useSWR<AthleteProfileResponse>(
    "/api/athlete-profile",
    fetcher,
  );

  if (isLoading) {
    return (
      <div className={`rounded-card border border-surface-border bg-surface p-4 shadow-card animate-pulse h-24 ${className}`} />
    );
  }

  const profile = data?.profile ?? null;
  const syncedAtLabel = formatSyncedAt(profile?.synced_at ?? null);
  const thresholdPaceSyncedAtLabel = formatSyncedAt(
    profile?.threshold_pace_synced_at ?? null,
  );

  return (
    <div className={`rounded-card border border-surface-border bg-surface p-4 shadow-card ${className}`}>
      <div className="mb-1 text-xs font-medium uppercase tracking-wide text-ink-faint">
        Профиль атлета
      </div>

      {!data?.has_data ? (
        <p className="text-sm text-ink-soft">
          Профиль ещё не синхронизирован — расчёты используют значения по умолчанию из .env.
        </p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div>
              <div className="text-[11px] text-ink-faint">FTP</div>
              <div className="text-lg font-semibold text-ink">
                {profile?.ftp != null ? `${Math.round(profile.ftp)} Вт` : "—"}
              </div>
            </div>
            <div>
              <div className="text-[11px] text-ink-faint">Вес</div>
              <div className="text-lg font-semibold text-ink">
                {profile?.weight_kg != null ? `${profile.weight_kg} кг` : "—"}
              </div>
            </div>
            <div>
              <div className="text-[11px] text-ink-faint">LTHR</div>
              <div className="text-lg font-semibold text-ink">
                {profile?.lthr != null ? `${Math.round(profile.lthr)} уд/мин` : "—"}
              </div>
            </div>
            <div>
              <div className="text-[11px] text-ink-faint">Пороговый темп</div>
              <div className="text-lg font-semibold text-ink">
                {formatPace(profile?.threshold_pace_seconds_per_km)}
              </div>
              {profile?.threshold_pace_seconds_per_km != null ? (
                <div className="mt-0.5 text-[10px] text-ink-faint">
                  {dataSourceLabel(profile.threshold_pace_source)}
                  {thresholdPaceSyncedAtLabel ? ` · ${thresholdPaceSyncedAtLabel}` : null}
                </div>
              ) : null}
            </div>
          </div>
          <div className="mt-2 text-[11px] text-ink-faint">
            Синхронизировано: {dataSourceLabel(profile?.source)}
            {syncedAtLabel ? ` · ${syncedAtLabel}` : null}
          </div>
        </>
      )}
    </div>
  );
}
