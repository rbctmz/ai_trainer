"use client";

import Link from "next/link";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { SessionProjection, SessionFeedbackPrompt } from "@/lib/types";
import { workoutLabel } from "./displayText";
import { PostWorkoutFeedbackCard } from "./PostWorkoutFeedbackCard";

const metric = (value: number | null, unit: string) =>
  value == null || !Number.isFinite(value) ? "нет данных" : `${Math.round(value)} ${unit}`;

/** Render the server projection for this exact session; never infer completion from load. */
export function TodaySessionResult({ sessionId, prompt, onSaved, showName = false }: {
  sessionId: string;
  showName?: boolean;
  prompt?: SessionFeedbackPrompt;
  onSaved: (message: string) => void;
}) {
  // api-contract: manual: /api/planning/session-projection/{session_id}
  const { data, error, isLoading, mutate } = useSWR<SessionProjection>(
    `/api/planning/session-projection/${encodeURIComponent(sessionId)}`, fetcher,
  );
  const feedback = prompt?.session_id === sessionId && (prompt.state === "ready" || prompt.state === "submitted") ? prompt : null;
  const feedbackControl = (feedback ? <details className="mt-3 border-t border-surface-border pt-3">
        <summary className="cursor-pointer rounded text-sm font-medium text-ink underline underline-offset-2 focus-visible:outline">{feedback.state === "submitted" ? "Оценка сохранена · посмотреть" : "Оценить тренировку"}</summary>
        <div className="mt-3"><PostWorkoutFeedbackCard key={`${feedback.session_id}-${feedback.feedback?.revision ?? 0}`} prompt={feedback} onSaved={message => { void mutate(); onSaved(message); }} /></div>
      </details> : null);
  if (error) return <><p role="status" className="mt-3 text-sm text-ink-soft">Не удалось проверить выполнение. <button className="rounded underline focus-visible:outline" onClick={() => void mutate()}>Повторить</button></p>{feedbackControl}</>;
  if (isLoading || !data) return <><p role="status" className="mt-3 text-sm text-ink-soft">Проверяем выполнение…</p>{feedbackControl}</>;
  if (data.session_id !== sessionId) return <><p className="mt-3 text-sm text-ink-soft">Данные выполнения требуют уточнения.</p>{feedbackControl}</>;
  const uncertain = data.projection_status === "needs_confirmation" || data.fact.completion_status === "needs_confirmation";
  const gap = data.projection_status === "data_gap";
  const complete = !uncertain && !gap && data.fact.completion_status === "complete";
  const partial = !uncertain && !gap && data.fact.completion_status === "incomplete";
  const observed = complete || partial;
  const label = uncertain ? "Нужно уточнить выполнение" : gap ? "Недостаточно данных о выполнении" : complete ? "✓ Выполнено" : partial ? "◐ Выполнено частично" : "Выполнение пока не найдено";
  return (
    <section aria-label="Выполнение тренировки" data-session-result={sessionId} className="mt-3 rounded-lg border border-surface-border bg-surface-muted p-3">
      {showName ? <h3 className="mb-2 font-medium text-ink">{workoutLabel(data.plan.name)}</h3> : null}
      <p className="font-semibold text-ink">{label}</p>
      {observed ? <>
        <dl className="mt-2 grid grid-cols-3 gap-2 text-sm tabular-nums">
          <div><dt className="text-ink-soft">Показатель</dt><dd className="mt-1">Время</dd><dd className="mt-1">Нагрузка</dd></div>
          <div><dt className="text-ink-soft">План</dt><dd className="mt-1">{metric(data.plan.duration_minutes, "мин")}</dd><dd className="mt-1">{metric(data.plan.load_tss, "TSS")}</dd></div>
          <div><dt className="text-ink-soft">Факт</dt><dd className="mt-1">{metric(data.fact.duration_minutes, "мин")}</dd><dd className="mt-1">{metric(data.fact.load_tss, "TSS")}</dd></div>
        </dl>
        {data.plan.legs.length > 1 ? <ul className="mt-3 space-y-1 text-sm text-ink-soft">
          {data.plan.legs.map(leg => <li key={leg.leg_id}>Этап {leg.leg_index}: {data.fact.legs.some(fact => fact.planned_leg_id === leg.leg_id) ? "есть запись выполнения" : "запись выполнения не найдена"}</li>)}
        </ul> : null}
      </> : null}
      {uncertain ? <Link className="mt-2 inline-block rounded text-sm underline focus-visible:outline" href={`/planning?session_id=${encodeURIComponent(sessionId)}`}>Уточнить в плане</Link> : null}
      {feedbackControl}
    </section>
  );
}
