"use client";

import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { ApiError, deleteJSON, fetcher, postJSON, putJSON } from "@/lib/api";
import {
  Activity,
  ActivitiesResponse,
  ActivityIntervals,
  AthleteProfileResponse,
} from "@/lib/types";
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

function formatIntervalTime(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

function formatIntervalDistance(distanceKm: number): string {
  if (distanceKm >= 1) {
    const rounded = Math.round(distanceKm * 10) / 10;
    return `${rounded} км`;
  }
  return `${Math.round(distanceKm * 1000)} м`;
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
  const { data, error, isLoading, mutate } = useSWR<ActivitiesResponse>(
    "/api/activities?days=30",
    fetcher,
  );
  const { data: profileData } = useSWR<AthleteProfileResponse>(
    "/api/athlete-profile",
    fetcher,
  );
  const [selected, setSelected] = useState<Activity | null>(null);

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
                    className="cursor-pointer border-b border-surface-border last:border-0 hover:bg-surface-muted"
                    onClick={() => setSelected(a)}
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

      {selected ? (
        <ActivityCardModal
          activity={selected}
          onClose={() => setSelected(null)}
          onChanged={() => mutate()}
        />
      ) : null}
    </main>
  );
}

const GRADE_CLASSES: Record<string, string> = {
  A: "border-tone-success/30 bg-tone-success/15 text-tone-success",
  B: "border-tone-success/20 bg-tone-success/10 text-tone-success",
  C: "border-tone-warning/30 bg-tone-warning/15 text-tone-warning",
  D: "border-tone-warning/40 bg-tone-warning/20 text-tone-warning",
  E: "border-tone-danger/30 bg-tone-danger/15 text-tone-danger",
};

function ActivityCardModal({
  activity,
  onClose,
  onChanged,
}: {
  activity: Activity;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [tags, setTags] = useState<string[]>(activity.tags ?? []);
  const [newTag, setNewTag] = useState("");
  const [draftNotes, setDraftNotes] = useState(activity.coach_notes ?? "");
  const [intervals, setIntervals] = useState<ActivityIntervals | null | undefined>(
    activity.intervals,
  );
  const fallbackIntervals = useRef(activity.intervals);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const id = encodeURIComponent(activity.activity_id);
  const feedback = activity.feedback;

  useEffect(() => {
    let cancelled = false;
    fetcher<{ activity: Activity }>(`/api/activities/${id}`)
      .then((res) => {
        if (!cancelled) setIntervals(res.activity.intervals ?? null);
      })
      .catch(() => {
        if (!cancelled) setIntervals(fallbackIntervals.current ?? null);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось выполнить действие");
    } finally {
      setBusy(false);
    }
  }

  function addTag() {
    const tag = newTag.trim();
    if (!tag) return;
    void run(async () => {
      const res = await postJSON<{ tags: string[] }>(`/api/activities/${id}/tags`, { tag });
      setTags(res.tags);
      setNewTag("");
    });
  }

  function removeTag(tag: string) {
    void run(async () => {
      const res = await deleteJSON<{ tags: string[] }>(
        `/api/activities/${id}/tags/${encodeURIComponent(tag)}`,
      );
      setTags(res.tags);
    });
  }

  function analyze() {
    void run(async () => {
      const res = await postJSON<{ coach_notes: string }>(
        `/api/activities/${id}/analyze`,
        {},
      );
      setDraftNotes(res.coach_notes);
    });
  }

  function saveNotes() {
    void run(async () => {
      const res = await putJSON<{ coach_notes: string }>(
        `/api/activities/${id}/coach-notes`,
        { body: draftNotes, source: "coach" },
      );
      setDraftNotes(res.coach_notes);
    });
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-card border border-surface-border bg-surface p-5 shadow-card"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-lg font-semibold text-ink">
              {activity.sport_label ?? activity.sport} · {activity.date_label ?? activity.date}
            </div>
            <div className="mt-0.5 text-xs text-ink-faint">
              {activity.duration_minutes ?? "—"} мин · {activity.distance_km ?? "—"} км ·{" "}
              {activity.tss ?? "—"} TSS
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded px-2 py-1 text-sm text-ink-soft hover:bg-surface hover:text-ink"
          >
            ✕
          </button>
        </div>

        <div className="mt-4 rounded-md border border-surface-border bg-surface p-3">
          <div className="text-xs font-medium uppercase tracking-wide text-ink-faint">
            Оценка тренировки
          </div>
          {feedback ? (
            <div className="mt-2 flex flex-wrap items-center gap-3">
              {feedback.grade ? (
                <span
                  className={`rounded border px-2 py-0.5 text-sm font-bold ${
                    GRADE_CLASSES[feedback.grade] ?? "text-ink"
                  }`}
                >
                  {feedback.grade}
                </span>
              ) : null}
              <span className="text-sm text-ink">
                RPE {feedback.session_rpe_1_10 ?? "—"}/10
              </span>
              {feedback.foster_load != null ? (
                <span className="text-sm text-ink-soft">
                  нагрузка {feedback.foster_load} AU
                </span>
              ) : null}
              {feedback.quality_rating_1_5 != null ? (
                <span className="text-sm text-ink-soft">
                  качество {feedback.quality_rating_1_5}/5
                </span>
              ) : null}
              {feedback.note ? (
                <p className="w-full text-sm text-ink-soft">{feedback.note}</p>
              ) : null}
            </div>
          ) : (
            <p className="mt-2 text-sm text-ink-soft">
              Фидбек ещё не заполнен — он появится на экране «Сегодня».
            </p>
          )}
        </div>

        <div className="mt-4 rounded-md border border-surface-border bg-surface p-3">
          <div className="text-xs font-medium uppercase tracking-wide text-ink-faint">
            Структура тренировки
          </div>
          {intervals && intervals.intervals.length > 0 ? (
            <ul className="mt-2 space-y-1.5 text-sm text-ink">
              {intervals.intervals.map((iv, index) => (
                <li
                  key={index}
                  className="flex flex-wrap items-center gap-x-2 gap-y-1"
                >
                  <span className="rounded border border-surface-border bg-surface px-1.5 py-0.5 text-xs font-semibold text-ink-soft">
                    #{index + 1}
                  </span>
                  {iv.moving_time != null ? (
                    <span className="font-medium tabular-nums">
                      {formatIntervalTime(iv.moving_time)}
                    </span>
                  ) : null}
                  {iv.distance_km != null ? (
                    <span className="text-ink-soft">
                      {formatIntervalDistance(iv.distance_km)}
                    </span>
                  ) : null}
                  {iv.average_watts != null ? (
                    <span className="text-ink-soft">{iv.average_watts} Вт</span>
                  ) : null}
                  {iv.average_heartrate != null ? (
                    <span className="text-ink-soft">HR {iv.average_heartrate}</span>
                  ) : null}
                  {iv.zone != null ? (
                    <span className="text-ink-soft">зона {iv.zone}</span>
                  ) : null}
                  {iv.training_load != null ? (
                    <span className="text-ink-faint">TL {iv.training_load}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-ink-soft">
              {intervals
                ? "Интервалы не детектированы."
                : "Интервалы недоступны для этой активности."}
            </p>
          )}
        </div>

        <div className="mt-4">
          <div className="text-xs font-medium uppercase tracking-wide text-ink-faint">
            Теги
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {tags.map((tag) => (
              <span
                key={tag}
                className="flex items-center gap-1 rounded-full border border-surface-border bg-surface px-2 py-0.5 text-xs text-ink"
              >
                {tag}
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => removeTag(tag)}
                  className="text-ink-faint hover:text-tone-danger"
                  aria-label={`Удалить тег ${tag}`}
                >
                  ×
                </button>
              </span>
            ))}
            <input
              value={newTag}
              onChange={(event) => setNewTag(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") addTag();
              }}
              placeholder="Добавить тег…"
              className="min-w-32 flex-1 rounded border border-surface-border bg-surface px-2 py-1 text-sm text-ink"
            />
            <button
              type="button"
              disabled={busy || !newTag.trim()}
              onClick={addTag}
              className="rounded border border-surface-border px-2 py-1 text-sm text-ink hover:bg-surface"
            >
              Добавить
            </button>
          </div>
        </div>

        <div className="mt-4">
          <div className="flex items-center justify-between">
            <div className="text-xs font-medium uppercase tracking-wide text-ink-faint">
              Разбор
            </div>
            <button
              type="button"
              disabled={busy}
              onClick={analyze}
              className="rounded border border-surface-border px-2 py-1 text-sm text-ink hover:bg-surface"
            >
              Разобрать
            </button>
          </div>
          <textarea
            value={draftNotes}
            onChange={(event) => setDraftNotes(event.target.value)}
            rows={8}
            className="mt-2 w-full resize-y rounded border border-surface-border bg-surface p-2 text-sm text-ink"
            placeholder="Здесь появится разбор или заметка тренера…"
          />
          <button
            type="button"
            disabled={busy}
            onClick={saveNotes}
            className="mt-2 rounded border border-surface-border px-3 py-1 text-sm text-ink hover:bg-surface"
          >
            Сохранить заметку
          </button>
        </div>

        {error ? <p className="mt-3 text-sm text-tone-danger">{error}</p> : null}
      </div>
    </div>
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
