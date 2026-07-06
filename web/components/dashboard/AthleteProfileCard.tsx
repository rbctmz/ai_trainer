"use client";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { AthleteProfileResponse } from "@/lib/types";

function formatSyncedAt(value: string | null): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" });
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
          <div className="grid grid-cols-3 gap-3">
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
          </div>
          <div className="mt-2 text-[11px] text-ink-faint">
            {profile?.source === "intervals_icu" ? "Синхронизировано из Intervals.icu" : profile?.source}
            {syncedAtLabel ? ` · ${syncedAtLabel}` : null}
          </div>
        </>
      )}
    </div>
  );
}
