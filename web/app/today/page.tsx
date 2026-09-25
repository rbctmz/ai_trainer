"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { fetcher, putJSON } from "@/lib/api";
import { workoutLabel, decisionText } from "@/components/today/displayText";
import { showDevTools } from "@/lib/flags";
import type {
  TodayResponse,
  WorkoutStep,
} from "@/lib/types";
import { ReadinessIndicator, ReadinessDetails } from "@/components/today/ReadinessSummary";
import { ProposalCard } from "@/components/ui/ProposalCard";
import { PostWorkoutFeedbackCard } from "@/components/today/PostWorkoutFeedbackCard";
import { AdherenceStrip } from "@/components/today/AdherenceStrip";
import { SubjectiveWellnessCard } from "@/components/dashboard/SubjectiveWellnessCard";
import { WorkoutStrip } from "@/components/WorkoutStrip";
import { SessionProjectionSummary } from "@/components/session/SessionProjectionSummary";
import {
  TodayDecisionStoryCompact,
  TodayDecisionStoryFull,
} from "@/components/today/TodayDecisionStory";

function formatHumanDate(iso: string): string {
  try {
    const formatted = new Intl.DateTimeFormat("ru-RU", {
      weekday: "long",
      day: "numeric",
      month: "long",
    }).format(new Date(`${iso}T00:00:00`));
    return formatted.charAt(0).toUpperCase() + formatted.slice(1);
  } catch {
    return iso;
  }
}

export default function TodayPage() {
  const { data, error, isLoading, mutate } = useSWR<TodayResponse>(
    "/api/today",
    fetcher,
  );
  const [notice, setNotice] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [frequencySaving, setFrequencySaving] = useState(false);

  const state = data?.state ?? "silence";
  const decisionStory = data?.decision_story;
  const readiness = data?.readiness ?? null;
  const session = data?.session ?? null;
  const proposal = data?.pending_proposal ?? null;
  const forecast = data?.forecast?.prediction ?? null;
  const yesterday = data?.yesterday;
  const feedbackPrompt =
    data?.feedback?.primary ??
    data?.feedback?.prompts.find((prompt) => prompt.state === "submitted") ??
    null;
  const pendingMatch = data?.feedback?.prompts.find(
    (prompt) => prompt.state === "pending_match",
  );
  const projectionSessionIds = session?.sessions !== undefined
    ? Array.from(
        new Set(
          session.sessions
            .map((leaf) => leaf.group_id ?? leaf.session_id)
            .filter((sessionId): sessionId is string => Boolean(sessionId)),
        ),
      )
    : session?.session_id
      ? [session.session_id]
      : [];

  const frequency = data?.briefing?.frequency ?? "daily";
  // The server story owns today's action. A legacy quiet gate must not hide a
  // different next action in the compact briefing.
  const isCompact =
    frequency === "conflicts_only" &&
    Boolean(data?.briefing?.is_quiet_day) &&
    state === "silence" &&
    decisionStory?.next_action.kind === "follow_plan" &&
    !expanded;

  const workout = state !== "no_plan" ? (
    <div className="min-w-0">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-faint">
        Сегодня по плану
      </h2>
      {session ? (
        <div className="mt-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xl font-semibold text-ink">{workoutLabel(session.name)}</span>
            {session.is_key ? (
              <span className="rounded-full bg-accent/10 px-2 py-0.5 text-xs font-medium text-accent">
                ключевая
              </span>
            ) : null}
          </div>
          <p className="mt-0.5 text-sm text-ink-soft">
            {[session.duration_minutes != null ? `${session.duration_minutes} мин` : null, session.role_label, session.sport_label, `${session.tss} TSS`]
              .filter(Boolean)
              .join(" · ")}
          </p>
          {session.sessions && session.sessions.length > 1 ? (
            <div className="mt-3 grid gap-2">
              {session.sessions.map((leaf, index) => (
                <div
                  key={leaf.session_id || `${leaf.sport}-${index}`}
                  className="rounded-lg bg-surface-muted p-2.5"
                >
                  <div className="text-xs font-medium text-ink">
                    {index + 1}. {workoutLabel(leaf.name)}
                    {leaf.kind === "brick_leg" ? (
                      <span className="ml-1 rounded bg-accent/10 px-1 text-[10px] font-medium text-accent">
                        связка · этап {leaf.leg_index}
                      </span>
                    ) : null}
                    <span className="ml-1 font-normal text-ink-faint">
                      {leaf.sport_label} · {leaf.total_tss} TSS
                    </span>
                  </div>
                  <TodaySteps steps={leaf.materialized_steps || []} />
                </div>
              ))}
            </div>
          ) : session.kind === "composite" && session.legs?.length ? (
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {session.legs.map((leg) => (
                <div key={leg.leg_index} className="rounded-lg bg-surface-muted p-2.5">
                  <div className="text-xs font-medium text-ink">
                    {leg.leg_index}. {workoutLabel(leg.template_name || leg.sport || "Этап")}
                    <span className="ml-1 font-normal text-ink-faint">
                      {leg.duration_minutes} мин · {leg.target_tss} TSS
                    </span>
                  </div>
                  <TodaySteps steps={leg.steps} />
                </div>
              ))}
            </div>
          ) : (
            <TodaySteps steps={session.steps || []} />
          )}
          {projectionSessionIds.length > 0 ? (
            <details className="mt-4 border-t border-surface-border pt-3">
              <summary className="cursor-pointer text-sm font-medium text-accent">Сравнить с выполненными тренировками</summary>
              {projectionSessionIds.map((sessionId) => (
                <SessionProjectionSummary key={sessionId} sessionId={sessionId} compact />
              ))}
            </details>
          ) : null}
        </div>
      ) : (
        <p className="mt-1 text-sm text-ink-soft">
          Плановой сессии нет — день отдыха.
        </p>
      )}
    </div>
  ) : null;

  async function toggleBriefingFrequency() {
    const next = frequency === "conflicts_only" ? "daily" : "conflicts_only";
    setFrequencySaving(true);
    try {
      await putJSON("/api/settings/briefing", { frequency: next });
      setExpanded(false);
      await mutate();
    } catch {
      setNotice("Не удалось сохранить настройку частоты брифинга.");
    } finally {
      setFrequencySaving(false);
    }
  }

  return (
    <main className="mx-auto max-w-2xl space-y-5">
      {isLoading ? (
        <div
          role="status"
          aria-label="Загрузка страницы Сегодня"
          aria-live="polite"
          className="h-48 animate-pulse rounded-card bg-surface"
        >
          <span className="sr-only">Загружается экран «Сегодня»</span>
        </div>
      ) : null}
      {error ? (
        <div role="alert" className="rounded-card border border-tone-danger/30 bg-tone-danger/10 p-4 text-sm text-tone-danger">
          Не удалось загрузить «Сегодня». Попробуйте обновить страницу.
        </div>
      ) : null}
      {notice ? (
        <div role="status" className="rounded-card border border-tone-success/30 bg-tone-success/10 p-4 text-sm text-tone-success">
          {notice}
        </div>
      ) : null}

      {data ? (
        <>
          {data.device_sync_hint ? (
            <div className="rounded-card border border-tone-warning/30 bg-tone-warning/10 p-4 text-sm text-tone-warning">
              План на сегодня изменился (переплан по состоянию). Синхронизируй
              устройство (Garmin), чтобы получить актуальную тренировку.
            </div>
          ) : null}
          <header className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm text-ink-faint">{formatHumanDate(data.date)}</p>
              {!isCompact ? (
                <h1 className="mt-1 text-2xl font-bold text-ink">Сегодня</h1>
              ) : null}
            </div>
            <button
              type="button"
              onClick={() => void toggleBriefingFrequency()}
              disabled={frequencySaving}
              title="Частота утреннего брифинга"
              className="shrink-0 whitespace-nowrap rounded-lg border border-surface-border px-2.5 py-1.5 text-xs font-medium text-ink-faint transition hover:bg-surface-muted disabled:opacity-60"
            >
              {frequency === "conflicts_only" ? "Только конфликты" : "Каждое утро"}
            </button>
          </header>

          {isCompact ? (
            <>
              {decisionStory ? (
                <TodayDecisionStoryCompact
                  nextAction={decisionStory.next_action}
                  readiness={readiness}
                  sessionName={session?.name}
                  onExpand={() => setExpanded(true)}
                />
              ) : null}
              <SubjectiveWellnessCard data={data.subjective_wellness} />
            </>
          ) : (
            <>
          {decisionStory ? (
            <TodayDecisionStoryFull
              story={decisionStory}
              nextAction={decisionStory.next_action}
              readiness={readiness}
              workout={workout}
            />
          ) : (
            <section className="rounded-card border border-surface-border bg-surface p-5">
              <p role="alert" className="mb-4 text-sm text-tone-warning">История решения недоступна. Проверьте данные перед действием.</p>
              <div className="grid gap-4 sm:grid-cols-[1fr_160px]">{workout}<ReadinessIndicator readiness={readiness} /></div>
              <details className="mt-4"><summary className="cursor-pointer text-sm text-accent">Показатели восстановления</summary><ReadinessDetails readiness={readiness} /></details>
            </section>
          )}
          {state === "no_plan" ? (
            <div className="rounded-card border border-surface-border bg-surface p-6 text-center shadow-card">
              <p className="text-sm text-ink-soft">
                Построй план — и этот экран каждое утро будет отвечать на вопрос
                «что сегодня делать?».
              </p>
              <Link
                href="/planning"
                className="mt-3 inline-block rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-foreground"
              >
                Открыть планирование
              </Link>
            </div>
          ) : null}

          {(state === "conflict_actionable" || state === "conflict") &&
          proposal &&
          decisionStory?.next_action.kind === "review_proposal" &&
          decisionStory.next_action.enabled ? (
            <ProposalCard
              proposalId={proposal.id}
              action={proposal.action}
              status={proposal.status}
              params={proposal.params}
              preview={proposal.preview}
              onConfirmed={(message) => {
                setNotice(message);
                void mutate();
              }}
              onCancelled={(message) => {
                setNotice(message ?? "Отклонено: план не изменён.");
                void mutate();
              }}
            />
          ) : null}

          {state === "conflict_unactionable" ? (
            <section className="rounded-card border border-tone-warning/40 bg-tone-warning/10 p-4 shadow-card">
              <h2 className="text-sm font-semibold text-ink">
                Изменение плана пока недоступно
              </h2>
              <p className="mt-1 text-sm text-ink-soft">
                Оценка восстановления расходится с запланированной нагрузкой. Готового
                предложения по изменению нет. Посмотрите объяснение ниже и проверьте план.
              </p>
              {data.proposal.relation === "stale" ? (
                <p className="mt-2 text-xs text-tone-warning">
                  Предыдущее предложение относится к старой версии плана и больше не может быть применено.
                </p>
              ) : null}
              {showDevTools && data.gate.proposal_gap ? (
                <p className="mt-2 text-xs text-ink-faint">
                  Причина отсутствия варианта: {data.gate.proposal_gap}
                </p>
              ) : null}
              <div className="mt-3 flex flex-wrap gap-2">
                <Link
                  href="/planning"
                  className="rounded-lg border border-surface-border px-3 py-1.5 text-sm font-medium text-ink"
                >
                  Проверить план
                </Link>
                {showDevTools ? (
                  <Link
                    href="/decisions"
                    className="rounded-lg border border-surface-border px-3 py-1.5 text-sm font-medium text-ink"
                  >
                    Открыть журнал
                  </Link>
                ) : null}
              </div>
            </section>
          ) : null}

          <SubjectiveWellnessCard data={data.subjective_wellness} />

          {data.gate.conflicts.length || data.gate.data_gap || data.gate.proposal_gap ? (
            <details className="rounded-card border border-surface-border bg-surface p-4 shadow-card">
              <summary className="cursor-pointer text-sm font-medium text-ink">
                Что требует внимания
                <span className="ml-2 text-xs font-normal text-ink-faint">
                  {data.gate.data_gap ? "не хватает данных" : ""}
                </span>
              </summary>
              <div className="mt-3 space-y-3 text-sm text-ink-soft">
                {data.gate.conflicts.map((conflict, conflictIndex) => (
                  <div key={`${conflict.kind ?? "conflict"}-${conflictIndex}`}>
                    <p className="font-medium text-ink">
                      {conflict.date ?? data.date}
                    </p>
                    {(conflict.evidence ?? []).map((evidence, evidenceIndex) => (
                      <p key={evidenceIndex}>• {evidence}</p>
                    ))}
                  </div>
                ))}
                {!data.gate.conflicts.length && data.gate.reason ? (
                  <p>{decisionText(data.gate.reason)}</p>
                ) : null}
                {showDevTools && data.gate.decision.id ? (
                  <p className="text-xs text-ink-faint">
                    decision #{data.gate.decision.id} · snapshot {data.snapshot_version}
                  </p>
                ) : null}
              </div>
            </details>
          ) : null}

          {showDevTools && forecast ? (
            <section className="rounded-card border border-surface-border bg-surface p-4 shadow-card">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-sm font-semibold text-ink">Прогноз качества сессии</h2>
                    <span className="rounded-full bg-surface-muted px-2 py-0.5 text-[11px] font-medium text-ink-soft">
                      shadow
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-ink-faint">
                    Наблюдение · не влияет на решение и корректировку плана
                  </p>
                </div>
                <div className="text-right">
                  <div className="text-2xl font-bold tabular-nums text-ink">
                    {forecast.prediction_pct}%
                  </div>
                  <div className="text-xs text-ink-faint">
                    {forecastBandLabel(forecast.prediction_band)}
                  </div>
                </div>
              </div>
              <p className="mt-3 text-sm text-ink-soft">
                Цель {formatHumanDate(forecast.target_date)} · ревизия {forecast.revision}
                {forecast.planned_session?.tss ? ` · ${Math.round(forecast.planned_session.tss)} TSS` : ""}
              </p>
              {data.forecast.relation === "stale_checkpoint" ? (
                <p className="mt-2 text-xs text-tone-warning">
                  Прогноз относится к прошлой версии плана и показан только как evidence.
                </p>
              ) : null}
              <p className="mt-2 text-xs text-ink-faint">
                Время цели известно только как дата; pre-start статус будет подтверждён после
                фактической активности.
              </p>
            </section>
          ) : null}

          {yesterday ? (
            <section className="rounded-card border border-surface-border bg-surface p-4 shadow-card">
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-sm font-semibold text-ink">Вчера · план и факт</h2>
                <span className="text-xs text-ink-faint">{yesterday.date}</span>
              </div>
              {yesterday.status === "unavailable" ? (
                <p className="mt-2 text-sm text-ink-soft">
                  Сопоставление временно недоступно: {yesterday.reason ?? "нет данных"}
                </p>
              ) : yesterday.status === "empty" ? (
                <p className="mt-2 text-sm text-ink-soft">Нет плановых или фактических сессий.</p>
              ) : (
                <>
                  <div className="mt-3 grid grid-cols-3 gap-2">
                    <YesterdayMetric label="План" value={`${Math.round(yesterday.planned_tss)} TSS`} />
                    <YesterdayMetric
                      label="Факт"
                      value={`${Math.round(yesterday.total_actual_tss)} TSS`}
                    />
                    <YesterdayMetric
                      label="Связано с планом"
                      value={`${yesterday.matched_sessions}/${yesterday.planned_sessions}`}
                    />
                  </div>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {Object.entries(yesterday.adherence)
                      .filter(([, count]) => count > 0)
                      .map(([key, count]) => (
                        <span
                          key={key}
                          className="rounded-full bg-surface-muted px-2 py-0.5 text-xs text-ink-soft"
                        >
                          {adherenceLabel(key)} {count}
                        </span>
                      ))}
                    {yesterday.unplanned_tss > 0 ? (
                      <span className="rounded-full bg-tone-warning/10 px-2 py-0.5 text-xs text-tone-warning">
                        вне плана {Math.round(yesterday.unplanned_tss)} TSS
                      </span>
                    ) : null}
                  </div>
                  {yesterday.rows.map((row) => (
                    <div
                      key={row.session_id}
                      className="mt-3 border-t border-surface-border pt-2 text-xs text-ink-soft"
                    >
                      <span className="font-medium text-ink">{row.name}</span>
                      {` · ${Math.round(row.tss)} → ${Math.round(row.actual_total_tss)} TSS`}
                      {` · ${adherenceLabel(row.adherence)}`}
                    </div>
                  ))}
                  <p className="mt-3 text-xs text-ink-faint">
                    {yesterday.activities} активности · {yesterday.minutes} мин
                    {showDevTools ? ` · версия: ${yesterday.rule_version ?? "—"}` : ""}
                  </p>
                </>
              )}
            </section>
          ) : null}

          <AdherenceStrip />

          {feedbackPrompt ? (
            <PostWorkoutFeedbackCard
              key={`${feedbackPrompt.session_id}-${feedbackPrompt.feedback?.revision ?? 0}`}
              prompt={feedbackPrompt}
              onSaved={(message) => {
                setNotice(message);
                void mutate();
              }}
            />
          ) : null}

          {pendingMatch && !feedbackPrompt ? (
            <section className="rounded-card border border-tone-warning/30 bg-tone-warning/10 p-4 shadow-card">
              <h2 className="text-sm font-semibold text-ink">Сначала уточните факт сессии</h2>
              <p className="mt-1 text-sm text-ink-soft">
                Для {pendingMatch.name} найдено неоднозначное совпадение активностей. Оценка
                качества не будет приписана плану, пока связь с тренировкой не подтверждена.
              </p>
              <Link
                href={`/planning?session_id=${encodeURIComponent(pendingMatch.session_id)}`}
                className="mt-3 inline-block rounded-lg border border-surface-border px-3 py-1.5 text-sm font-medium text-ink"
              >
                Уточнить в плане
              </Link>
            </section>
          ) : null}
            </>
          )}
        </>
      ) : null}
    </main>
  );
}

function YesterdayMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-surface-muted px-2.5 py-2">
      <div className="text-[11px] uppercase tracking-wide text-ink-faint">{label}</div>
      <div className="mt-0.5 font-semibold tabular-nums text-ink">{value}</div>
    </div>
  );
}

function adherenceLabel(value: string): string {
  return {
    exact: "по плану",
    substituted: "изменено",
    major_deviation: "сильное отклонение",
    unknown: "не определено",
  }[value] ?? value;
}

function forecastBandLabel(value: string): string {
  return { low: "низкая вероятность", uncertain: "неопределённо", high: "высокая вероятность" }[
    value
  ] ?? value;
}

function TodaySteps({ steps }: { steps: WorkoutStep[] }) {
  if (!steps.length) return null;
  return (
    <div>
      <WorkoutStrip steps={steps.map((step) => ({ ...step, name: workoutLabel(step.name || "") }))} />
      <div className="mt-2 space-y-1.5 text-sm text-ink-soft">
        {steps.map((step, index) => (
          <div key={`${step.name}-${index}`} className="flex items-center justify-between gap-3">
            <span className="min-w-0">{workoutLabel(step.name || `Шаг ${index + 1}`)}</span>
            <span className="shrink-0 tabular-nums">
              {formatSeconds(step.duration_seconds)}
              {formatTarget(step.target) ? ` · ${formatTarget(step.target)}` : ""}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function formatSeconds(seconds: number | null): string {
  if (!seconds) return "—";
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return rest ? `${minutes}:${String(rest).padStart(2, "0")}` : `${minutes} мин`;
}

function formatTarget(target: Record<string, unknown> | null): string {
  if (!target) return "";
  const type = String(target.type || "");
  const low = target.low;
  const high = target.high;
  if (type === "power" && low != null && high != null) return `${low}–${high} Вт`;
  if (type === "heart_rate" && low != null && high != null) return `${low}–${high} уд/мин`;
  if (type === "relative_rpe" && low != null && high != null) return `RPE ${low}–${high}`;
  if (type.includes("pace") && typeof target.fast === "number" && typeof target.slow === "number") {
    const pace = (seconds: number) => `${Math.floor(Math.round(seconds) / 60)}:${String(Math.round(seconds) % 60).padStart(2, "0")}`;
    return `${pace(target.fast)}–${pace(target.slow)} ${target.unit === "seconds_per_100m" ? "/100 м" : target.unit === "seconds_per_km" ? "/км" : ""}`;
  }
  return ({ pace: "по темпу", run_pace: "по темпу бега", swim_pace: "по темпу плавания", power: "по мощности", heart_rate: "по пульсу", relative_rpe: "по ощущению усилия" } as Record<string, string>)[type] ?? "цель не указана";
}
