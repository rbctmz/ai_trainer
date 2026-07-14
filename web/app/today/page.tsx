"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { TodayResponse, WorkoutStep } from "@/lib/types";
import { ProposalCard } from "@/components/ui/ProposalCard";
import { PostWorkoutFeedbackCard } from "@/components/today/PostWorkoutFeedbackCard";

const STATE_META: Record<
  string,
  { title: string; icon: string; tone: string }
> = {
  silence: { title: "План в силе", icon: "✓", tone: "text-tone-success" },
  conflict_actionable: {
    title: "Есть предложение",
    icon: "!",
    tone: "text-tone-warning",
  },
  conflict_unactionable: {
    title: "Конфликт требует внимания",
    icon: "!",
    tone: "text-tone-warning",
  },
  conflict: { title: "Есть предложение", icon: "!", tone: "text-tone-warning" },
  data_gap: { title: "Данных недостаточно", icon: "…", tone: "text-ink-soft" },
  no_plan: { title: "Плана нет", icon: "→", tone: "text-ink-soft" },
};

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

  const state = data?.state ?? "silence";
  const meta = STATE_META[state] ?? STATE_META.silence;
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

  return (
    <main className="mx-auto max-w-2xl space-y-5">
      {isLoading ? <div className="h-48 animate-pulse rounded-card bg-surface" /> : null}
      {error ? (
        <div className="rounded-card border border-tone-danger/30 bg-tone-danger/10 p-4 text-sm text-tone-danger">
          Не удалось загрузить «Сегодня». Проверьте, что ./run_web.sh запущен.
        </div>
      ) : null}
      {notice ? (
        <div className="rounded-card border border-tone-success/30 bg-tone-success/10 p-4 text-sm text-tone-success">
          {notice}
        </div>
      ) : null}

      {data ? (
        <>
          <header>
            <p className="text-sm text-ink-faint">{formatHumanDate(data.date)}</p>
            <div className="mt-1 flex items-center gap-2">
              <span className={`text-xl font-bold ${meta.tone}`}>{meta.icon}</span>
              <h1 className="text-2xl font-bold text-ink">{meta.title}</h1>
            </div>
            {data.reason ? (
              <p className="mt-1 text-sm text-ink-soft">{data.reason}</p>
            ) : null}
          </header>

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

          {(state === "conflict_actionable" || state === "conflict") && proposal ? (
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
                Автоматическая правка сейчас небезопасна
              </h2>
              <p className="mt-1 text-sm text-ink-soft">
                Контур увидел расхождение готовности и нагрузки, но не создал применимое
                предложение. План не объявляется безопасным автоматически — проверьте улики
                ниже и при необходимости скорректируйте день вручную.
              </p>
              {data.proposal.relation === "stale" ? (
                <p className="mt-2 text-xs text-tone-warning">
                  Предыдущее предложение относится к checkpoint #
                  {data.proposal.base_checkpoint_id ?? "—"}, активный checkpoint #
                  {data.proposal.active_checkpoint_id ?? "—"}. Кнопки применения отключены.
                </p>
              ) : null}
              {data.gate.proposal_gap ? (
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
                <Link
                  href="/decisions"
                  className="rounded-lg border border-surface-border px-3 py-1.5 text-sm font-medium text-ink"
                >
                  Открыть журнал
                </Link>
              </div>
            </section>
          ) : null}

          {state !== "no_plan" ? (
            <section className="rounded-card border border-surface-border bg-surface p-4 shadow-card">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-faint">
                Сегодня по плану
              </h2>
              {session ? (
                <div className="mt-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-lg font-semibold text-ink">{session.name}</span>
                    {session.is_key ? (
                      <span className="rounded-full bg-accent/10 px-2 py-0.5 text-xs font-medium text-accent">
                        ключевая
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-0.5 text-sm text-ink-soft">
                    {[session.role_label, session.sport_label, `${session.tss} TSS`]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                  {session.stimulus ? (
                    <p className="mt-2 text-sm text-ink-soft">{session.stimulus}</p>
                  ) : null}
                  {session.fatigue_cost?.length ? (
                    <p className="mt-1 text-xs text-ink-faint">
                      Fatigue {session.fatigue_cost.join("/")}
                      {session.expected_recovery_hours
                        ? ` · восстановление ~${session.expected_recovery_hours} ч`
                        : ""}
                    </p>
                  ) : null}
                  {session.kind === "composite" && session.legs?.length ? (
                    <div className="mt-3 grid gap-2 sm:grid-cols-2">
                      {session.legs.map((leg) => (
                        <div key={leg.leg_index} className="rounded-lg bg-surface-muted p-2.5">
                          <div className="text-xs font-medium text-ink">
                            {leg.leg_index}. {leg.template_name || leg.sport}
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
                </div>
              ) : (
                <p className="mt-1 text-sm text-ink-soft">
                  Плановой сессии нет — день отдыха.
                </p>
              )}
            </section>
          ) : null}

          {readiness ? (
            <details className="rounded-card border border-surface-border bg-surface p-4 shadow-card">
              <summary className="cursor-pointer text-sm font-medium text-ink">
                Готовность {Math.round(readiness.score)}/100
                <span className="ml-2 text-xs font-normal text-ink-faint">
                  почему — {readiness.drivers.length || readiness.factors.length} факторов
                </span>
              </summary>
              <div className="mt-3 space-y-1.5 text-sm text-ink-soft">
                {(readiness.drivers.length > 0 ? readiness.drivers : readiness.factors).map(
                  (item, index) => {
                    const evidence = String(
                      (item as Record<string, unknown>).evidence ?? "",
                    );
                    return evidence ? <p key={index}>• {evidence}</p> : null;
                  },
                )}
                {readiness.tsb &&
                readiness.tsb.tsb != null &&
                !(readiness.drivers.length > 0 ? readiness.drivers : readiness.factors).some(
                  (item) => (item as Record<string, unknown>).key === "tsb",
                ) ? (
                  <p>
                    • TSB {readiness.tsb.tsb} (CTL {readiness.tsb.ctl ?? "—"}, окно{" "}
                    {readiness.tsb.window_days} дн.)
                  </p>
                ) : null}
                {readiness.confidence != null ? (
                  <p className="text-xs text-ink-faint">
                    confidence {readiness.confidence}
                    {readiness.stale ? " · данные устарели" : ""}
                  </p>
                ) : null}
              </div>
            </details>
          ) : null}

          {data.gate.conflicts.length || data.gate.data_gap || data.gate.proposal_gap ? (
            <details className="rounded-card border border-surface-border bg-surface p-4 shadow-card">
              <summary className="cursor-pointer text-sm font-medium text-ink">
                Улики salience-gate
                <span className="ml-2 text-xs font-normal text-ink-faint">
                  {data.gate.outcome ?? "недоступен"}
                </span>
              </summary>
              <div className="mt-3 space-y-3 text-sm text-ink-soft">
                {data.gate.conflicts.map((conflict, conflictIndex) => (
                  <div key={`${conflict.kind ?? "conflict"}-${conflictIndex}`}>
                    <p className="font-medium text-ink">
                      {conflict.date ?? data.date}
                      {conflict.severity ? ` · severity ${conflict.severity}` : ""}
                    </p>
                    {(conflict.evidence ?? []).map((evidence, evidenceIndex) => (
                      <p key={evidenceIndex}>• {evidence}</p>
                    ))}
                  </div>
                ))}
                {!data.gate.conflicts.length && data.gate.reason ? (
                  <p>{data.gate.reason}</p>
                ) : null}
                {data.gate.decision.id ? (
                  <p className="text-xs text-ink-faint">
                    decision #{data.gate.decision.id} · snapshot {data.snapshot_version}
                  </p>
                ) : null}
              </div>
            </details>
          ) : null}

          {forecast ? (
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
                {forecast.planned_tss ? ` · ${Math.round(forecast.planned_tss)} TSS` : ""}
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
                <h2 className="text-sm font-semibold text-ink">Вчера · план vs факт</h2>
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
                      label="Матч"
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
                    {yesterday.activities} активности · {yesterday.minutes} мин · rule {" "}
                    {yesterday.rule_version ?? "—"}
                  </p>
                </>
              )}
            </section>
          ) : null}

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
                качества не будет приписана плану, пока match не подтверждён.
              </p>
              <Link
                href={`/planning?session_id=${encodeURIComponent(pendingMatch.session_id)}`}
                className="mt-3 inline-block rounded-lg border border-surface-border px-3 py-1.5 text-sm font-medium text-ink"
              >
                Уточнить в Planning
              </Link>
            </section>
          ) : null}
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
    substituted: "замена",
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
    <div className="mt-2 space-y-1 text-xs text-ink-faint">
      {steps.map((step, index) => (
        <div key={`${step.name}-${index}`} className="flex items-center justify-between gap-3">
          <span>{step.name || `Шаг ${index + 1}`}</span>
          <span className="shrink-0 tabular-nums">
            {formatSeconds(step.duration_seconds)}
            {formatTarget(step.target) ? ` · ${formatTarget(step.target)}` : ""}
          </span>
        </div>
      ))}
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
  return type;
}
