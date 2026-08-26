"use client";

import { useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import useSWR from "swr";
import { fetcher, postJSON } from "@/lib/api";
import type {
  ComparableSessionProjection,
  SessionFeedbackHistoryResponse,
  SessionFeedbackPrompt,
} from "@/lib/types";

const COMPLETION_LABELS: Record<string, string> = {
  completed: "Выполнено",
  partial: "Частично",
  stopped_early: "Остановился раньше",
  did_not_start: "Не начинал",
  unknown: "Не уверен",
};

const PROVENANCE_LABELS: Record<string, string> = {
  "athlete-entered": "введено спортсменом",
  "admin-entered": "введено администратором",
};

const SPORT_LABELS: Record<string, string> = {
  run: "бег",
  running: "бег",
  bike: "вело",
  cycling: "вело",
  ride: "вело",
  swim: "плавание",
  swimming: "плавание",
};

function sportKey(value: string | null | undefined): string {
  const key = String(value ?? "").trim().toLowerCase();
  if (["run", "running"].includes(key)) return "run";
  if (["bike", "cycling", "ride"].includes(key)) return "bike";
  if (["swim", "swimming"].includes(key)) return "swim";
  return key;
}

function sportLabel(value: string | null | undefined): string {
  const key = String(value ?? "").trim().toLowerCase();
  return SPORT_LABELS[key] ?? (key || "активность");
}

function provenanceLabel(value: string | null | undefined): string {
  const key = String(value ?? "").trim();
  return PROVENANCE_LABELS[key] ?? (key || "введено спортсменом");
}

function createSubmissionFingerprint(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `feedback-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function PostWorkoutFeedbackCard({
  prompt,
  onSaved,
}: {
  prompt: SessionFeedbackPrompt;
  onSaved: (message: string) => void;
}) {
  const saved = prompt.feedback;
  const [editing, setEditing] = useState(prompt.state === "ready");
  const [completionStatus, setCompletionStatus] = useState(
    saved?.completion_status ?? prompt.allowed_completion_statuses[0] ?? "completed",
  );
  const [completionPct, setCompletionPct] = useState<number | null>(
    saved?.completion_pct ?? (completionStatus === "completed" ? 100 : null),
  );
  const [rpe, setRpe] = useState<number | null>(saved?.session_rpe_1_10 ?? null);
  const [quality, setQuality] = useState<number | null>(
    saved?.quality_rating_1_5 ?? null,
  );
  const [note, setNote] = useState(saved?.note ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const submissionFingerprintRef = useRef<string | null>(null);
  const { data: history } = useSWR<SessionFeedbackHistoryResponse>(
    showHistory ? `/api/session-feedback/${prompt.session_id}/history` : null,
    fetcher,
  );
  const needsRatings = !["did_not_start", "unknown"].includes(completionStatus);
  const canSubmit = !submitting && (!needsRatings || (rpe !== null && quality !== null));
  const plannedSportKey = sportKey(prompt.planned_sport);
  const actualSportKeys = Array.from(
    new Set(
      prompt.actual_activities
        .map((activity) => sportKey(activity.sport))
        .filter(Boolean),
    ),
  );
  const confirmedSubstitution =
    prompt.match_method === "user_confirmed" &&
    Boolean(plannedSportKey) &&
    actualSportKeys.some((key) => key !== plannedSportKey);
  const actualSportLabel = actualSportKeys.map(sportLabel).join(" + ");
  const activitySummary = useMemo(
    () =>
      prompt.actual_activities
        .map((activity) => {
          const minutes = Math.round(Number(activity.duration_minutes ?? 0));
          const tss = Math.round(Number(activity.tss ?? 0));
          return `${sportLabel(activity.sport)} · ${minutes} мин · ${tss} TSS`;
        })
        .join("; "),
    [prompt.actual_activities],
  );

  async function saveFeedback() {
    if (!canSubmit) return;
    setSubmitting(true);
    setFormError(null);
    submissionFingerprintRef.current ??= createSubmissionFingerprint();
    const body = {
      client_submission_fingerprint: submissionFingerprintRef.current,
      completion_status: completionStatus,
      completion_pct: completionPct,
      session_rpe_1_10: needsRatings ? rpe : null,
      quality_rating_1_5: needsRatings ? quality : null,
      note: note.trim() || null,
    };
    try {
      const result = saved
        ? await postJSON<{ feedback: { revision: number } }>(
            `/api/session-feedback/${saved.id}/correct`,
            body,
          )
        : await postJSON<{ feedback: { revision: number } }>("/api/session-feedback", {
            session_id: prompt.session_id,
            ...body,
          });
      setEditing(false);
      submissionFingerprintRef.current = null;
      onSaved(`Фидбек сохранён · версия ${result.feedback.revision}`);
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Не удалось сохранить фидбек");
    } finally {
      setSubmitting(false);
    }
  }

  async function dismiss() {
    setSubmitting(true);
    setFormError(null);
    submissionFingerprintRef.current ??= createSubmissionFingerprint();
    try {
      await postJSON(`/api/session-feedback/prompts/${prompt.session_id}/dismiss`, {
        client_submission_fingerprint: submissionFingerprintRef.current,
        prompt_fingerprint: prompt.prompt_fingerprint,
        reason: "not_now",
      });
      submissionFingerprintRef.current = null;
      onSaved("Напоминание скрыто. Факт тренировки не изменён.");
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Не удалось скрыть напоминание");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="rounded-card border border-accent/30 bg-surface p-4 shadow-card">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-ink">
            {prompt.capture_mode === "immediate"
              ? "Оцени тренировку сейчас"
              : "Как прошла сессия?"}
          </h2>
          <p className="mt-1 text-xs text-ink-faint">
            {prompt.name} · совпадение {matchLabel(prompt.match_status)}
            {prompt.capture_mode === "immediate" ? " · только что загружена" : ""}
          </p>
        </div>
        <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[11px] font-medium text-accent">
          {provenanceLabel(saved?.provenance_label ?? prompt.provenance_label)}
        </span>
      </div>

      {activitySummary ? (
        <p className="mt-3 rounded-lg bg-surface-muted px-3 py-2 text-xs text-ink-soft">
          Факт: {activitySummary}
        </p>
      ) : (
        <p className="mt-3 rounded-lg bg-surface-muted px-3 py-2 text-xs text-ink-soft">
          Активность не найдена — можно отметить только «не начинал» или «не уверен».
        </p>
      )}

      {prompt.comparison?.status === "available" ? (
        <ComparableSessionEvidence comparison={prompt.comparison} />
      ) : null}

      {confirmedSubstitution ? (
        <p className="mt-2 text-xs font-medium text-accent">
          Подтверждённая замена: {actualSportLabel} вместо {sportLabel(prompt.planned_sport)}
        </p>
      ) : null}

      {saved && !editing ? (
        <div className="mt-3 space-y-2 text-sm text-ink-soft">
          <p>
            {confirmedSubstitution ? "Фактическая сессия" : "Сессия"} · {" "}
            {COMPLETION_LABELS[saved.completion_status] ?? saved.completion_status}
            {saved.completion_pct != null ? ` · ${Math.round(saved.completion_pct)}%` : ""}
            {saved.session_rpe_1_10 != null ? ` · RPE ${saved.session_rpe_1_10}/10` : ""}
            {saved.quality_rating_1_5 != null
              ? ` · качество ${saved.quality_rating_1_5}/5`
              : ""}
          </p>
          {saved.note ? <p className="text-xs text-ink-faint">«{saved.note}»</p> : null}
          <p className="text-xs text-ink-faint">Сохранена версия {saved.revision}</p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="rounded-lg border border-surface-border px-3 py-1.5 text-xs font-medium text-ink"
            >
              Исправить
            </button>
            <button
              type="button"
              onClick={() => setShowHistory((value) => !value)}
              className="rounded-lg border border-surface-border px-3 py-1.5 text-xs text-ink-soft"
            >
              {showHistory ? "Скрыть историю" : "История"}
            </button>
          </div>
          {showHistory ? (
            <div className="space-y-1 rounded-lg bg-surface-muted p-2.5 text-xs text-ink-soft">
              {(history?.history ?? []).map((item) => (
                <p key={item.id}>
                  версия {item.revision} · {COMPLETION_LABELS[item.completion_status] ?? item.completion_status}
                  {item.session_rpe_1_10 != null ? ` · RPE ${item.session_rpe_1_10}` : ""}
                  {item.quality_rating_1_5 != null ? ` · качество ${item.quality_rating_1_5}` : ""}
                </p>
              ))}
            </div>
          ) : null}
        </div>
      ) : (
        <div className="mt-4 space-y-4">
          <fieldset>
            <legend className="text-xs font-semibold uppercase tracking-wide text-ink-faint">
              {confirmedSubstitution ? "Выполнение фактической сессии" : "Выполнение"}
            </legend>
            <div className="mt-2 flex flex-wrap gap-2">
              {prompt.allowed_completion_statuses.map((status) => (
                <ChoiceButton
                  key={status}
                  active={completionStatus === status}
                  onClick={() => {
                    setCompletionStatus(status);
                    setCompletionPct(status === "completed" ? 100 : null);
                  }}
                >
                  {COMPLETION_LABELS[status] ?? status}
                </ChoiceButton>
              ))}
            </div>
          </fieldset>

          {needsRatings ? (
            <>
              <Scale
                title="Насколько тяжёлой ощущалась вся сессия?"
                hint="1–2 очень легко · 3–4 легко · 5–6 умеренно · 7–8 тяжело · 9 очень тяжело · 10 максимум"
                values={Array.from({ length: 10 }, (_, index) => index + 1)}
                selected={rpe}
                onSelect={setRpe}
              />
              <Scale
                title="Удалось реализовать задуманное качество?"
                hint="1–2 не удалось · 3 неоднозначно (не скорится) · 4–5 удалось"
                values={[1, 2, 3, 4, 5]}
                selected={quality}
                onSelect={setQuality}
              />
            </>
          ) : null}

          <label className="block text-xs font-medium text-ink-soft">
            Заметка — необязательно
            <textarea
              value={note}
              onChange={(event) => setNote(event.target.value)}
              rows={2}
              maxLength={2000}
              className="mt-1 w-full rounded-lg border border-surface-border bg-surface-muted px-3 py-2 text-sm text-ink outline-none focus:border-accent"
              placeholder="Что помогло или помешало?"
            />
          </label>

          {formError ? <p className="text-xs text-tone-danger">{formError}</p> : null}
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={!canSubmit}
              onClick={() => void saveFeedback()}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-foreground disabled:opacity-50"
            >
              {submitting ? "Сохраняю…" : saved ? "Сохранить исправление" : "Сохранить факт"}
            </button>
            {saved ? (
              <button
                type="button"
                onClick={() => setEditing(false)}
                className="rounded-lg border border-surface-border px-3 py-2 text-sm text-ink-soft"
              >
                Отмена
              </button>
            ) : (
              <button
                type="button"
                disabled={submitting}
                onClick={() => void dismiss()}
                className="rounded-lg border border-surface-border px-3 py-2 text-sm text-ink-soft disabled:opacity-50"
              >
                Не сейчас
              </button>
            )}
          </div>
          <p className="text-[11px] text-ink-faint">
            RPE и качество вводит атлет. Они не выводятся из TSS, пульса или Training Effect
            и сами по себе не меняют план.
          </p>
        </div>
      )}
    </section>
  );
}

function ComparableSessionEvidence({
  comparison,
}: {
  comparison: ComparableSessionProjection;
}) {
  const target = comparison.target;
  const prior = comparison.comparator;
  const score = comparison.similarity?.score;
  const sportMetric = comparison.comparison?.sport_metric as
    | {
        kind?: string;
        target?: {
          value?: number;
          source?: string;
          threshold_value?: number;
          threshold_source?: string;
        };
        comparator?: {
          value?: number;
          source?: string;
          threshold_value?: number;
          threshold_source?: string;
        };
      }
    | null;
  const paceUnit =
    sportMetric?.kind === "pace_seconds_per_km" ? "с/км" : "с/100 м";
  if (!target || !prior) return null;
  return (
    <div className="mt-3 rounded-lg border border-surface-border bg-surface-muted px-3 py-2 text-xs text-ink-soft">
      <p className="font-semibold text-ink">Сравнение с похожей сессией</p>
      <p className="mt-1">
        Сейчас: {Math.round(Number(target.duration_minutes ?? 0))} мин · {Math.round(Number(target.tss ?? 0))} TSS
      </p>
      <p>
        {prior.date ?? "Прошлая дата неизвестна"}: {Math.round(Number(prior.duration_minutes ?? 0))} мин · {Math.round(Number(prior.tss ?? 0))} TSS
      </p>
      {score != null ? <p className="mt-1">Сходство по фактам: {Math.round(score * 100)}%</p> : null}
      {sportMetric?.kind === "power_watts" ? (
        <p className="mt-1">
          Мощность: {sportMetric.target?.value ?? "—"} Вт ({sportMetric.target?.source ?? "—"}) · ранее {sportMetric.comparator?.value ?? "—"} Вт ({sportMetric.comparator?.source ?? "—"})
        </p>
      ) : null}
      {sportMetric?.kind?.startsWith("pace_seconds_") ? (
        <p className="mt-1">
          Темп: {sportMetric.target?.value ?? "—"} {paceUnit} · ранее {sportMetric.comparator?.value ?? "—"} {paceUnit}; порог сейчас {sportMetric.target?.threshold_value ?? "—"} ({sportMetric.target?.threshold_source ?? "источник неизвестен"}), ранее {sportMetric.comparator?.threshold_value ?? "—"} ({sportMetric.comparator?.threshold_source ?? "источник неизвестен"})
        </p>
      ) : null}
      <p className="mt-1 text-ink-faint">Одно сравнение не доказывает тренд или причину.</p>
    </div>
  );
}

function ChoiceButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-lg border px-2.5 py-1.5 text-xs ${
        active
          ? "border-accent bg-accent/10 font-medium text-accent"
          : "border-surface-border text-ink-soft"
      }`}
    >
      {children}
    </button>
  );
}

function Scale({
  title,
  hint,
  values,
  selected,
  onSelect,
}: {
  title: string;
  hint: string;
  values: number[];
  selected: number | null;
  onSelect: (value: number) => void;
}) {
  return (
    <fieldset>
      <legend className="text-xs font-medium text-ink-soft">{title}</legend>
      <p className="mt-0.5 text-[11px] text-ink-faint">{hint}</p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {values.map((value) => (
          <ChoiceButton key={value} active={selected === value} onClick={() => onSelect(value)}>
            {value}
          </ChoiceButton>
        ))}
      </div>
    </fieldset>
  );
}

function matchLabel(value: string): string {
  return {
    matched: "подтверждено",
    ambiguous: "нужно уточнить",
    unmatched: "не найдено",
  }[value] ?? value;
}
