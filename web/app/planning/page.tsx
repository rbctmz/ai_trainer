"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { ApiError, fetcher, postJSON, withDemo } from "@/lib/api";
import { AdherenceRibbon } from "@/components/AdherenceRibbon";
import { DEFAULT_DEMAND_OPTIONS, PlanBuilder, Stat } from "@/components/planning/PlanBuilder";
import {
  DemandConfirmResult,
  DemandPreview,
  ForecastPoint,
  IntervalsDeliveryResult,
  PlanningHistory,
  PlanningOverview,
  PlanExport,
  PlanningStatus,
  RebalanceConfirmResult,
  RebalancePreviewResult,
  ReconResponse,
  RestoreHistoryResult,
  WeekByWeekPlan,
} from "@/lib/types";

const READER_TABS = ["overview", "weeks", "execution"] as const;
type ReaderTab = (typeof READER_TABS)[number];
type Tab = ReaderTab | "build" | "adjust" | "export";
const READER_TAB_LABELS: Record<ReaderTab, string> = {
  overview: "Обзор",
  weeks: "Недели",
  execution: "Выполнение",
};

export default function PlanningPage() {
  const { data: status } = useSWR<PlanningStatus>("/api/planning/status", fetcher);
  const { data: overview, error: overviewError } = useSWR<PlanningOverview>(
    status?.has_plan ? "/api/planning/overview" : null,
    fetcher,
  );
  const [tab, setTab] = useState<Tab | null>(null);
  const [targetSessionId, setTargetSessionId] = useState<string | null>(null);
  const resolvedDefault = useRef(false);
  const hasAdjustmentDeepLink = useRef(false);
  const m = status?.metrics;

  useEffect(() => {
    const searchParams = new URLSearchParams(window.location.search);
    const sessionId = searchParams.get("session_id")?.trim();
    if (!sessionId) return;
    hasAdjustmentDeepLink.current = true;
    setTargetSessionId(sessionId);
    setTab("adjust");
  }, []);

  useEffect(() => {
    if (!status || resolvedDefault.current) return;
    resolvedDefault.current = true;
    setTab(status.has_plan && hasAdjustmentDeepLink.current ? "adjust" : status.has_plan ? "overview" : "build");
  }, [status]);

  const hasPlan = status?.has_plan ?? false;

  if (!status || !tab) {
    return (
      <main className="space-y-5">
        <h1 className="text-2xl font-bold text-ink">Планирование</h1>
        <Skeleton />
      </main>
    );
  }

  return (
    <main className="space-y-5">
      <h1 className="text-2xl font-bold text-ink">Планирование</h1>

      <section className="rounded-card border border-surface-border bg-surface p-4 shadow-card">
        <div className="text-xs font-medium uppercase tracking-wide text-ink-faint">
          Текущий статус нагрузки
        </div>
        <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="CTL" value={m ? `${m.ctl}` : "—"} />
          <Stat label="ATL" value={m ? `${m.atl}` : "—"} />
          <Stat label="TSB" value={m ? `${m.tsb}` : "—"} />
          <Stat label="Форма" value={m?.form ?? "—"} />
        </div>
      </section>

      {hasPlan ? (
        <>
          <nav
            aria-label="Просмотр активного плана"
            className="flex gap-1 overflow-x-auto rounded-card border border-surface-border bg-surface p-1 shadow-card"
          >
            {READER_TABS.map((readerTab) => (
              <button
                key={readerTab}
                type="button"
                onClick={() => setTab(readerTab)}
                aria-current={tab === readerTab ? "page" : undefined}
                className={`min-w-fit flex-1 rounded-lg px-3 py-2 text-sm font-medium transition ${
                  tab === readerTab ? "bg-accent text-accent-foreground" : "text-ink-soft hover:bg-surface-muted"
                }`}
              >
                {READER_TAB_LABELS[readerTab]}
              </button>
            ))}
          </nav>
          <div className="flex flex-wrap gap-2" aria-label="Действия с планом">
            <button
              type="button"
              onClick={() => setTab("build")}
              className="rounded-lg border border-surface-border px-3 py-2 text-sm font-medium text-ink transition hover:bg-surface-muted"
            >
              Изменить план
            </button>
            <button
              type="button"
              onClick={() => setTab("adjust")}
              className="rounded-lg border border-surface-border px-3 py-2 text-sm font-medium text-ink transition hover:bg-surface-muted"
            >
              Скорректировать
            </button>
            <button
              type="button"
              onClick={() => setTab("export")}
              className="rounded-lg border border-surface-border px-3 py-2 text-sm font-medium text-ink transition hover:bg-surface-muted"
            >
              Экспорт
            </button>
          </div>
        </>
      ) : null}

      {!hasPlan || tab === "build" ? (
        <PlanBuilder status={status} onSaved={() => setTab("overview")} />
      ) : null}
      {hasPlan && tab === "overview" ? <ActivePlanOverview overview={overview} error={overviewError} /> : null}
      {hasPlan && tab === "weeks" ? <PlanWeeks onResolveAmbiguous={() => setTab("adjust")} /> : null}
      {hasPlan && tab === "execution" ? <ExecutionOverview /> : null}
      {tab === "adjust" ? (
        <AdjustMode
          hasPlan={hasPlan}
          targetSessionId={targetSessionId}
        />
      ) : null}
      {tab === "export" ? <ExportMode /> : null}
      {hasPlan ? <AdjustmentHistory /> : null}
    </main>
  );
}

function ActivePlanOverview({ overview, error }: { overview?: PlanningOverview; error?: Error }) {
  if (error) return <LocalDataGap label="Обзор активного плана сейчас недоступен. Остальные действия сохранены." />;
  if (!overview || !overview.has_plan) return <Skeleton />;

  const event = overview.timeline?.kind === "event" ? overview.timeline.event : null;
  const goalTitle = [overview.goal?.goal_type, overview.goal?.distance].filter(Boolean).join(" · ");
  const currentWeek = overview.current_week;

  return (
    <section className="rounded-card border border-surface-border bg-surface p-5 shadow-card">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-xs font-medium uppercase tracking-wide text-ink-faint">Активный план</div>
          <h2 className="mt-1 text-xl font-bold text-ink">{goalTitle || "Цель плана уточняется"}</h2>
          {overview.timeline?.kind === "rolling" ? (
            <p className="mt-2 text-sm text-ink-soft">
              Скользящий горизонт на {overview.timeline.horizon_weeks} нед. без привязки к дате гонки.
            </p>
          ) : event?.date ? (
            <p className="mt-2 text-sm text-ink-soft">
              A-цель: {event.label} · {event.date} · осталось {overview.timeline?.days_remaining} дн.
            </p>
          ) : (
            <p className="mt-2 text-sm text-ink-soft">
              A-цель или её дата пока не подтверждены в сохранённом плане.
            </p>
          )}
        </div>
        <span className="rounded-full bg-accent/10 px-3 py-1 text-xs font-medium text-accent">
          {overview.progress?.status_label ?? "Статус уточняется"}
        </span>
      </div>

      <dl className="mt-5 grid gap-3 sm:grid-cols-3">
        <OverviewFact
          label="Текущая фаза"
          value={currentWeek?.phase ?? "Недостаточно данных"}
          detail={currentWeek ? `Неделя ${currentWeek.number}` : ""}
        />
        <OverviewFact
          label="Прогресс"
          value={overview.progress ? `${overview.progress.completed_weeks}/${overview.progress.total_weeks} нед.` : "Недостаточно данных"}
          detail="по сохранённому горизонту"
        />
        <OverviewFact
          label="Выполнение"
          value={overview.execution?.label ?? "Недостаточно данных"}
          detail={overview.execution?.description ?? ""}
        />
      </dl>
      <div className="mt-5 space-y-5">
        <AvailabilitySummary availability={overview.availability} />
        <WeeklyTargetExplanation explanation={overview.weekly_target_explanation} />
        <DemandControl explanation={overview.weekly_target_explanation} />
        <PhaseRoadmap roadmap={overview.roadmap} />
        <FormProjection projection={overview.form_projection} />
      </div>
    </section>
  );
}

function OverviewFact({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="rounded-lg border border-surface-border bg-surface-muted/40 p-3">
      <dt className="text-xs text-ink-faint">{label}</dt>
      <dd className="mt-1 text-sm font-semibold text-ink">{value}</dd>
      {detail ? <p className="mt-1 text-xs text-ink-soft">{detail}</p> : null}
    </div>
  );
}

function AvailabilitySummary({ availability }: { availability?: PlanningOverview["availability"] }) {
  if (!availability || availability.state !== "available") {
    return <LocalDataGap label={availability?.reason ?? "Доступность пока недоступна в сохранённом checkpoint."} />;
  }
  const periodLabel = availability.period
    ? `${availability.period.week_start} — ${availability.period.week_end}`
    : "выбранная неделя не определена";
  return (
    <section aria-labelledby="availability-title">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id="availability-title" className="text-sm font-semibold text-ink">Доступность</h3>
        <span className="text-xs text-ink-faint">Сохранённые ограничения плана</span>
      </div>
      <dl className="mt-3 grid gap-2 sm:grid-cols-4">
        <OverviewFact label="Доступно" value={`${availability.available_hours} ч/нед.`} detail={`${availability.available_days.join(" · ")} · ${availability.available_minutes} мин/нед. · потолок, не цель заполнения`} />
        <OverviewFact label="Запланировано на выбранной неделе" value={`${availability.planned_hours} ч`} detail={`${availability.planned_minutes} мин · ${periodLabel}`} />
        <OverviewFact label="Сессии на выбранной неделе" value={`${availability.session_count}`} detail={periodLabel} />
        <OverviewFact label="По дням" value="Нет лимитов" detail={availability.daily.reason ?? "Дневные данные недоступны."} />
      </dl>
    </section>
  );
}

function WeeklyTargetExplanation({ explanation }: { explanation?: PlanningOverview["weekly_target_explanation"] }) {
  if (!explanation || explanation.state !== "available" || !explanation.demand) {
    return <LocalDataGap label={explanation?.reason ?? "Расчёт недельной нагрузки пока недоступен в сохранённом checkpoint."} />;
  }
  return (
    <section aria-labelledby="weekly-target-title">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id="weekly-target-title" className="text-sm font-semibold text-ink">Как рассчитана недельная нагрузка</h3>
        <span className="text-xs text-ink-faint">Сохранённый расчёт при создании плана</span>
      </div>
      <dl className="mt-3 grid gap-2 sm:grid-cols-4">
        {explanation.rows.map((row) => (
          <OverviewFact key={row.key} label={row.label} value={`${row.value} ${row.unit}`} detail={row.detail} />
        ))}
      </dl>
      <div className="mt-3 rounded-lg border border-accent/20 bg-accent/5 p-3 text-sm text-ink">
        <strong>Итог: {explanation.final_target_weekly_tss} TSS/нед.</strong>
        <span className="ml-2 text-xs text-ink-soft">
          спрос: {explanation.demand.label} × {explanation.demand.multiplier}
        </span>
      </div>
    </section>
  );
}

function DemandControl({ explanation }: { explanation?: PlanningOverview["weekly_target_explanation"] }) {
  const { mutate } = useSWRConfig();
  const [selected, setSelected] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [applied, setApplied] = useState<string | null>(null);
  const currentLevel =
    explanation?.state === "available" && explanation.demand ? explanation.demand.level : null;

  const previewKey = selected
    ? `/api/planning/demand-preview?level=${encodeURIComponent(selected)}`
    : null;
  const { data: preview, isValidating } = useSWR<DemandPreview>(previewKey, fetcher, {
    revalidateOnFocus: false,
  });

  if (explanation?.state !== "available" || !currentLevel) {
    return null;
  }

  const previewData = preview?.state === "available" && preview.preview ? preview.preview : null;
  const baseCheckpointId = preview?.base_checkpoint_id ?? null;
  const previewFingerprint = preview?.preview_fingerprint ?? null;

  function choose(level: string) {
    setApplied(null);
    setError(null);
    setSelected((current) => (current === level ? null : level));
  }
  function cancel() {
    setSelected(null);
    setError(null);
    setApplied(null);
  }
  async function apply() {
    if (!previewData || baseCheckpointId == null || !previewFingerprint) return;
    setConfirming(true);
    setError(null);
    try {
      const result = await postJSON<DemandConfirmResult>("/api/planning/demand/confirm", {
        level: previewData.level,
        base_checkpoint_id: baseCheckpointId,
        preview_fingerprint: previewFingerprint,
      });
      setApplied(`Сохранено как checkpoint #${result.applied_checkpoint_id}. Режим нагрузки обновлён.`);
      setSelected(null);
      await Promise.all([
        mutate("/api/planning/overview"),
        mutate("/api/planning/status"),
        mutate("/api/planning/history?limit=8"),
      ]);
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : "Не удалось применить режим нагрузки. Подготовьте новый preview.",
      );
      setSelected(null);
    } finally {
      setConfirming(false);
    }
  }

  return (
    <section
      aria-labelledby="demand-control-title"
      className="rounded-card border border-surface-border bg-surface-muted/40 p-4"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id="demand-control-title" className="text-sm font-semibold text-ink">
          Режим нагрузки
        </h3>
        <span className="text-xs text-ink-faint">Применяется отдельной кнопкой после preview</span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        {DEFAULT_DEMAND_OPTIONS.map((option) => {
          const isCurrent = option.level === currentLevel;
          const isSelected = option.level === selected;
          return (
            <button
              key={option.level}
              type="button"
              onClick={() => choose(option.level)}
              aria-pressed={isSelected}
              className={`rounded-lg border px-3 py-2 text-left text-xs font-medium transition ${
                isSelected
                  ? "border-accent bg-accent text-accent-foreground"
                  : isCurrent
                    ? "border-accent/40 bg-accent/5 text-ink"
                    : "border-surface-border text-ink-soft hover:bg-surface-muted"
              }`}
            >
              <span className="block">{option.label}</span>
              <span className="text-[11px] opacity-70">
                {isCurrent ? "текущий" : `×${option.multiplier.toFixed(2)}`}
              </span>
            </button>
          );
        })}
      </div>

      {selected && isValidating ? (
        <p className="mt-3 text-xs text-ink-faint">Считаю ожидаемый эффект…</p>
      ) : null}
      {selected && preview && preview.state === "data_gap" ? (
        <p className="mt-3 text-xs text-ink-faint">{preview.reason ?? "Preview недоступен."}</p>
      ) : null}

      {previewData ? (
        <div className="mt-3 rounded-lg border border-surface-border bg-surface p-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="text-xs text-ink-faint">Новый итог недели</span>
            <span className="text-sm font-semibold tabular-nums text-ink">
              {previewData.final_target_weekly_tss} TSS/нед
              <span
                className={`ml-2 text-xs font-medium ${
                  previewData.delta_weekly_tss > 0
                    ? "text-accent"
                    : previewData.delta_weekly_tss < 0
                      ? "text-rose-600"
                      : "text-ink-faint"
                }`}
              >
                {previewData.delta_weekly_tss > 0 ? "+" : ""}
                {previewData.delta_weekly_tss} TSS
              </span>
            </span>
          </div>
          <div className="mt-2 grid gap-1.5 text-xs text-ink-soft sm:grid-cols-2">
            <span>База недели: {previewData.base_weekly_tss} TSS/нед</span>
            <span>Потолок доступности: {previewData.availability_cap_tss} TSS/нед</span>
            <span>Потребность цели: {previewData.goal_need_tss} TSS/нед</span>
            <span>Недавняя нагрузка: {previewData.recent_load_tss} TSS/нед</span>
          </div>
          {previewData.capped ? (
            <p className="mt-2 text-xs text-amber-700">
              Итог упирается в потолок доступности — выше {previewData.availability_cap_tss} TSS/нед
              план не поднимется.
            </p>
          ) : null}
          {selected === currentLevel ? (
            <p className="mt-2 text-xs text-ink-faint">Это текущий режим — применять нечего.</p>
          ) : (
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={apply}
                disabled={confirming}
                className="rounded-lg bg-accent px-4 py-2 text-xs font-medium text-accent-foreground transition hover:bg-accent/90 disabled:opacity-40"
              >
                {confirming ? "Применяю…" : "Применить и пересобрать"}
              </button>
              <button
                type="button"
                onClick={cancel}
                disabled={confirming}
                className="rounded-lg border border-surface-border px-4 py-2 text-xs font-medium text-ink transition hover:bg-surface-muted disabled:opacity-40"
              >
                Отмена
              </button>
            </div>
          )}
        </div>
      ) : null}

      {error ? <p className="mt-3 text-xs text-rose-600">{error}</p> : null}
      {applied ? <p className="mt-3 text-xs text-emerald-700">{applied}</p> : null}
    </section>
  );
}

const PHASE_TONES: Record<string, string> = {
  Base: "bg-sky-100 text-sky-900",
  Build: "bg-violet-100 text-violet-900",
  Recovery: "bg-emerald-100 text-emerald-900",
  Peak: "bg-amber-100 text-amber-900",
  Taper: "bg-orange-100 text-orange-900",
  "Race Week": "bg-rose-100 text-rose-900",
};

const PHASE_BAR_TONES: Record<string, string> = {
  Base: "bg-sky-200",
  Build: "bg-violet-200",
  Recovery: "bg-emerald-200",
  Peak: "bg-amber-200",
  Taper: "bg-orange-200",
  "Race Week": "bg-rose-200",
};

function PhaseRoadmap({ roadmap }: { roadmap?: PlanningOverview["roadmap"] }) {
  if (!roadmap || roadmap.state !== "available" || !roadmap.segments.length) {
    return <LocalDataGap label={roadmap?.reason ?? "Roadmap фаз пока недоступен в сохранённом checkpoint."} />;
  }
  const marker = roadmap.current_marker;
  return (
    <section aria-labelledby="phase-roadmap-title">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id="phase-roadmap-title" className="text-sm font-semibold text-ink">Roadmap фаз</h3>
        <span className="text-xs text-ink-faint">
          {roadmap.horizon_start} — {roadmap.horizon_end}
        </span>
      </div>
      <div
        role="img"
        aria-label={`Фазы плана от ${roadmap.horizon_start} до ${roadmap.horizon_end}. Текущая дата: ${marker?.date ?? "вне горизонта"}.`}
        className="relative mt-3 pt-5"
      >
        <div className="flex min-h-14 overflow-hidden rounded-lg border border-surface-border">
          {roadmap.segments.map((segment) => (
            <div
              key={`${segment.phase}-${segment.start_date}`}
              style={{ flexGrow: Math.max(1, segment.duration_days), flexBasis: 0 }}
              className={`min-w-0 border-r border-white/70 p-2 last:border-r-0 ${PHASE_TONES[segment.phase] ?? "bg-surface-muted text-ink-soft"}`}
            >
              <div className="truncate text-xs font-medium">{segment.phase}</div>
              <div className="mt-1 text-[11px] opacity-80">{segment.duration_days} дн.</div>
            </div>
          ))}
        </div>
        {marker ? (
          <span
            aria-hidden="true"
            style={{ left: `${marker.position_percent}%` }}
            className="absolute bottom-0 top-0 z-10 w-px bg-ink"
          />
        ) : null}
        {roadmap.events.map((event) => (
          <span
            key={`${event.priority}-${event.date}-${event.label}`}
            aria-hidden="true"
            title={`${event.priority} · ${event.label} · ${event.date}`}
            style={{ left: `${Math.min(98, Math.max(2, event.position_percent))}%` }}
            className="absolute top-3 z-20 -translate-x-1/2 rounded-full border border-surface bg-surface px-1.5 py-0.5 text-[10px] font-bold text-ink shadow-sm"
          >
            {event.priority}
          </span>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-soft">
        <span>│ Сегодня {marker?.date ?? "вне горизонта"}</span>
        <span>A/B/C — сохранённые старты</span>
      </div>
      {roadmap.events.length ? (
        <ul className="mt-2 grid gap-1 text-xs text-ink-soft sm:grid-cols-2">
          {roadmap.events.map((event) => (
            <li key={`${event.priority}-${event.date}-${event.label}`}>
              <strong className="text-ink">{event.priority}</strong> · {event.date} · {event.label}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function FormProjection({ projection }: { projection?: PlanningOverview["form_projection"] }) {
  if (!projection || projection.state !== "available" || !projection.summary) {
    return <LocalDataGap label={projection?.reason ?? "Прогноз формы пока недоступен в сохранённом checkpoint."} />;
  }
  const { actual_points: actual, forecast_points: forecast, boundary_date: boundary, summary } = projection;
  const allPoints = [...actual, ...forecast];
  if (actual.length < 1 || forecast.length < 1 || allPoints.length < 2) {
    return <LocalDataGap label="Недостаточно точек для честного графика формы." />;
  }

  const width = 720;
  const height = 220;
  const padding = 28;
  const dates = allPoints.map((point) => Date.parse(point.date));
  const minDate = Math.min(...dates);
  const maxDate = Math.max(...dates);
  const dateSpan = Math.max(1, maxDate - minDate);
  const values = allPoints.flatMap((point) => [point.ctl, point.atl, point.tsb, 0]);
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const valueSpan = Math.max(1, maxValue - minValue);
  const x = (day: string) => padding + ((Date.parse(day) - minDate) / dateSpan) * (width - padding * 2);
  const y = (value: number) => height - padding - ((value - minValue) / valueSpan) * (height - padding * 2);
  const path = (points: ForecastPoint[], key: "ctl" | "atl" | "tsb") =>
    points.map((point, index) => `${index === 0 ? "M" : "L"}${x(point.date)},${y(point[key])}`).join(" ");
  const targetX = x(summary.target_date);
  const series = [
    { key: "ctl" as const, color: "#3B82F6", label: "CTL (форма)" },
    { key: "atl" as const, color: "#F59E0B", label: "ATL (усталость)" },
    { key: "tsb" as const, color: "#10B981", label: "TSB (свежесть)" },
  ];
  const targetDetail = summary.target_kind === "event"
    ? `${summary.target_date} · ${summary.days_to_goal} дн. до A-цели`
    : `${summary.target_date} · конец скользящего горизонта`;

  return (
    <section aria-labelledby="form-projection-title">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id="form-projection-title" className="text-sm font-semibold text-ink">Факт и прогноз формы</h3>
        <span className="text-xs text-ink-faint">Цель: {targetDetail}</span>
      </div>
      <dl className="mt-3 grid gap-2 sm:grid-cols-4">
        <OverviewFact label="Текущий CTL" value={`${summary.current_ctl}`} detail={`факт на ${boundary}`} />
        <OverviewFact label="Пиковый CTL" value={`${summary.peak_projected_ctl}`} detail="в сохранённом плане" />
        <OverviewFact label="CTL к цели" value={`${summary.projected_ctl}`} detail={summary.target_date} />
        <OverviewFact label="TSB к цели" value={`${summary.projected_tsb}`} detail={summary.target_kind === "event" ? "к A-цели" : "к концу горизонта"} />
      </dl>
      <svg
        role="img"
        aria-label={`Факт формы до ${boundary} показан сплошной линией; прогноз после ${boundary} — пунктиром. ${targetDetail}.`}
        viewBox={`0 0 ${width} ${height}`}
        className="mt-4 w-full"
      >
        <line x1={padding} x2={width - padding} y1={y(0)} y2={y(0)} stroke="#E2E8F0" strokeWidth={1} />
        <line x1={targetX} x2={targetX} y1={padding} y2={height - padding} stroke="#334155" strokeWidth={1} />
        {series.map((item) => (
          <Fragment key={`actual-${item.key}`}>
            <path d={path(actual, item.key)} fill="none" stroke={item.color} strokeWidth={2} />
            <path d={path(forecast, item.key)} fill="none" stroke={item.color} strokeWidth={2} strokeDasharray="6 4" />
          </Fragment>
        ))}
      </svg>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-soft">
        <span>Сплошная: Факт до {boundary}</span>
        <span>Пунктир: Прогноз после {boundary}</span>
        <span>│ Целевая дата</span>
        {series.map((item) => <span key={item.key}>{item.label}</span>)}
      </div>
    </section>
  );
}

function PlanWeeks({ onResolveAmbiguous }: { onResolveAmbiguous: () => void }) {
  const { data, error } = useSWR<WeekByWeekPlan>("/api/planning/week-by-week", fetcher);
  if (error) return <LocalDataGap label="Недели плана сейчас недоступны. Попробуйте открыть их позже." />;
  if (!data) return <Skeleton />;
  if (data.state === "no_plan") return <LocalDataGap label="Активного плана пока нет." />;
  if (data.state !== "available" || !data.weeks.length || Array.isArray(data.chart)) {
    return <LocalDataGap label={data.reason ?? "Недели плана пока недоступны в сохранённом checkpoint."} />;
  }
  return (
    <section className="space-y-4">
      <WeekLoadChart chart={data.chart} />
      <p className="text-xs text-ink-faint">
        {data.window?.returned_weeks} из {data.window?.total_weeks} недель сохранённого плана. Факт и статусы совпадений получены одним локальным снимком на {data.as_of}.
      </p>
      {data.weeks.map((week) => (
        <details
          key={week.week_start}
          open={week.is_current}
          className="overflow-x-auto rounded-card border border-surface-border bg-surface shadow-card"
        >
          <summary className="cursor-pointer list-none p-4 marker:hidden">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-xs text-ink-faint">{week.week_start} — {week.week_end} · {week.state === "current" ? "текущая неделя" : week.state === "past" ? "прошедшая" : "будущая"}</div>
                <div className="mt-1 font-semibold text-ink"><span className={`mr-2 inline-block rounded px-1.5 py-0.5 text-xs ${PHASE_TONES[week.phase] ?? "bg-surface-muted text-ink-soft"}`}>Фаза: {week.phase}</span></div>
                {week.focus.length ? <div className="mt-1 text-xs text-ink-soft">Фокус: {week.focus.map((item) => item.name).join(" · ")}</div> : null}
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-right text-xs tabular-nums text-ink-soft">
                <span>План: <strong className="text-ink">{week.target_tss} TSS</strong></span>
                <span>Факт: <strong className="text-ink">{week.actual_tss ?? "—"}</strong></span>
                <span>Вне плана: <strong className="text-tone-warning">{week.unplanned_tss || "—"}</strong></span>
                <span>{week.completion_percent == null ? "Ожидается" : `${week.completion_percent}%`}</span>
              </div>
            </div>
            {week.state === "current" ? <div className="mt-2 text-xs text-ink-soft">В процессе · осталось {week.remaining_tss} TSS</div> : null}
            {week.events.length ? <div className="mt-2 flex flex-wrap gap-1 text-xs">{week.events.map((event) => <span key={`${event.priority}-${event.date}`} className="rounded bg-surface-muted px-1.5 py-0.5 text-ink"><strong>{event.priority}</strong> · {event.label}</span>)}</div> : null}
          </summary>
          <div className="border-t border-surface-border p-4">
            <div className="grid gap-2">
              {week.days.map((day) => <WeekDay key={day.date} day={day} onResolveAmbiguous={onResolveAmbiguous} />)}
            </div>
          </div>
        </details>
      ))}
    </section>
  );
}

function WeekLoadChart({ chart }: { chart: Exclude<WeekByWeekPlan["chart"], []> }) {
  return (
    <section className="rounded-card border border-surface-border bg-surface p-4 shadow-card">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold text-ink">Недельная нагрузка</h2>
        <span className="text-xs text-ink-faint">TSS · план и факт</span>
      </div>
      <div role="img" aria-label="Столбцы недельного TSS: светлый фон — план, тёмный столбец — факт; маркеры A, B и C обозначают сохранённые старты." className="mt-4 flex h-36 items-end gap-1 overflow-x-auto pb-5">
        {chart.weeks.map((week) => {
          const phaseLabel = `Фаза: ${week.phase}`;
          return (
          <div key={week.week_start} aria-label={`${phaseLabel}. ${week.week_start}: план ${week.target_tss} TSS, факт ${week.actual_tss ?? "—"}.`} className="relative flex h-full min-w-10 flex-1 items-end justify-center" title={`${phaseLabel}. ${week.week_start}: план ${week.target_tss} TSS, факт ${week.actual_tss ?? "—"}`}>
            <span aria-hidden="true" className={`absolute bottom-0 w-full rounded-t ${PHASE_BAR_TONES[week.phase] ?? "bg-surface-muted"}`} style={{ height: `${week.target_percent}%` }} />
            <span aria-hidden="true" className="relative w-3/5 rounded-t bg-accent/70" style={{ height: `${week.actual_percent ?? 0}%` }} />
            {week.events.map((event) => <span key={`${event.priority}-${event.date}`} className="absolute top-1 z-10 rounded bg-surface px-1 text-[10px] font-bold text-ink shadow-sm">{event.priority}</span>)}
            <span className="absolute -bottom-5 text-[10px] text-ink-faint">{week.number}</span>
          </div>
          );
        })}
      </div>
      <div className="mt-2 flex flex-wrap gap-3 text-xs text-ink-soft"><span>Фон: план</span><span>Столбец: факт</span><span>A/B/C: старты</span></div>
    </section>
  );
}

function WeekDay({ day, onResolveAmbiguous }: { day: WeekByWeekPlan["weeks"][number]["days"][number]; onResolveAmbiguous: () => void }) {
  const dayLabel = day.plan_state === "rest" ? "Отдых" : day.plan_state === "unplanned" ? "Вне плана" : "Запланировано";
  return (
    <article className="rounded-lg bg-surface-muted p-3">
      <div className="flex flex-wrap items-start justify-between gap-2 text-sm">
        <div><strong className="text-ink">{day.date}</strong><span className="ml-2 text-xs text-ink-faint">{dayLabel}</span></div>
        <div className="text-right text-xs tabular-nums text-ink-soft">План {day.target_tss} · факт {day.actual_tss ?? "—"}{day.unplanned_tss ? <span className="ml-1 text-tone-warning">+{day.unplanned_tss} вне плана</span> : null}</div>
      </div>
      {day.events.length ? <div className="mt-2 text-xs text-ink-soft">{day.events.map((event) => <span key={`${event.priority}-${event.date}`} className="mr-2"><strong className="text-ink">{event.priority}</strong> · {event.label}</span>)}</div> : null}
      {day.sessions.length ? <div className="mt-2 grid gap-2">{day.sessions.map((session) => <WeekLeaf key={session.session_id || session.name} session={session} dayIndex={day.index} onResolveAmbiguous={onResolveAmbiguous} />)}</div> : null}
      {day.plan_state === "rest" && !day.unplanned_tss ? <p className="mt-2 text-xs text-ink-faint">День отдыха.</p> : null}
      {day.unplanned_activities.length ? <p className="mt-2 text-xs text-tone-warning">Вне плана: {day.unplanned_activities.map((activity) => activity.name || activity.sport).join(" · ")}</p> : null}
    </article>
  );
}

function WeekLeaf({ session, dayIndex, onResolveAmbiguous }: { session: WeekByWeekPlan["weeks"][number]["days"][number]["sessions"][number]; dayIndex: number | null; onResolveAmbiguous: () => void }) {
  const labels: Record<string, string> = { planned: "запланировано", in_progress: "в процессе", exact: "выполнено", substituted: "замена", major_deviation: "отклонение", unknown: "нужна проверка", ambiguous: "нужно уточнить", missed: "пропущено" };
  return (
    <div className="rounded-md border border-surface-border bg-surface p-2.5 text-xs">
      <div className="flex flex-wrap items-center justify-between gap-2"><span className="font-medium text-ink">{session.name}</span><span className="text-ink-soft">{session.duration_minutes} мин · {session.tss} TSS · {labels[session.adherence_status]}</span></div>
      {session.actual_tss != null ? <div className="mt-1 text-ink-faint">Факт: {session.actual_tss} TSS · {session.actual_duration_minutes} мин</div> : null}
      {session.adherence_status === "ambiguous" ? <button type="button" onClick={onResolveAmbiguous} className="mt-2 rounded border border-surface-border px-2 py-1 text-ink hover:bg-surface-muted">Нужно уточнить</button> : null}
      {dayIndex != null && session.executable && session.kind !== "composite" && session.session_id ? <div className="mt-2 flex gap-2"><DownloadLink index={dayIndex} sessionId={session.session_id} fmt="tcx" label="TCX" /><DownloadLink index={dayIndex} sessionId={session.session_id} fmt="fit_csv" label="FIT" /></div> : null}
      {dayIndex != null && session.executable && session.kind === "composite" ? <div className="mt-2 flex flex-wrap gap-2">{session.legs.map((leg) => <span key={leg.leg_index} className="inline-flex items-center gap-1"><span className="text-ink-faint">{leg.sport}</span><DownloadLink index={dayIndex} sessionId={session.session_id ?? undefined} leg={leg.leg_index ?? undefined} fmt="tcx" label="TCX" /><DownloadLink index={dayIndex} sessionId={session.session_id ?? undefined} leg={leg.leg_index ?? undefined} fmt="fit_csv" label="FIT" /></span>)}</div> : null}
    </div>
  );
}

function ExecutionOverview() {
  return (
    <section className="space-y-3">
      <AdherenceRibbon />
      <p className="text-xs text-ink-faint">
        Для уточнения совпадений и безопасной пересборки используйте действие «Скорректировать».
      </p>
    </section>
  );
}

function LocalDataGap({ label }: { label: string }) {
  return (
    <section className="rounded-card border border-surface-border bg-surface p-4 text-sm text-ink-soft shadow-card">
      {label}
    </section>
  );
}

/* ---------------- Первый план (онбординг, #271 §7) ---------------- */
function AdjustmentHistory() {
  const { mutate } = useSWRConfig();
  const { data } = useSWR<PlanningHistory>("/api/planning/history?limit=8", fetcher);
  const [expanded, setExpanded] = useState(false);
  const [confirmingId, setConfirmingId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  if (!data || !data.has_history) return null;
  const activeId = data.items[0]?.checkpoint_id ?? null;

  async function restore(item: { checkpoint_id: number | null }) {
    if (activeId == null || item.checkpoint_id == null) return;
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const result = await postJSON<RestoreHistoryResult>("/api/planning/history/restore", {
        checkpoint_id: item.checkpoint_id,
        base_checkpoint_id: activeId,
      });
      setConfirmingId(null);
      setDone(`Восстановлено как checkpoint #${result.applied_checkpoint_id}.`);
      await Promise.all([
        mutate("/api/planning/history?limit=8"),
        mutate("/api/planning/status"),
        mutate("/api/planning/overview"),
      ]);
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : "Не удалось восстановить версию. Подготовьте новое действие.",
      );
      setConfirmingId(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-card border border-surface-border bg-surface p-4 shadow-card">
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls="planning-adjustment-history"
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            setExpanded((current) => !current);
          }
        }}
        onClick={() => setExpanded((current) => !current)}
        className="flex w-full items-baseline justify-between gap-3 text-left text-sm font-medium text-ink"
      >
        <span>История изменений</span>
        <span className="text-xs font-normal text-ink-soft">{data.items.length}</span>
      </button>
      {expanded ? (
        <div id="planning-adjustment-history" className="mt-3 divide-y divide-surface-border">
          {error ? <p className="py-2 text-xs text-rose-600">{error}</p> : null}
          {done ? <p className="py-2 text-xs text-emerald-700">{done}</p> : null}
          {data.items.map((item, index) => {
            const isActive = index === 0;
            const isConfirming = confirmingId === item.checkpoint_id;
            return (
              <div key={`${item.checkpoint_id}-${item.date}`} className="py-2.5">
                <div className="grid gap-2 sm:grid-cols-[110px_130px_1fr]">
                  <div className="text-xs tabular-nums text-ink-soft">
                    {item.date_label || item.date.slice(0, 10)}
                  </div>
                  <div className="text-xs font-medium text-ink">{item.type_label}</div>
                  <div className="text-sm text-ink-soft">{item.outcome_note}</div>
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  {isActive ? (
                    <span className="text-[11px] text-ink-faint">активная версия</span>
                  ) : isConfirming ? (
                    <>
                      <span className="text-xs text-ink-soft">
                        Восстановить версию {item.checkpoint_id}?
                      </span>
                      <button
                        type="button"
                        onClick={() => restore(item)}
                        disabled={busy}
                        className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-accent-foreground transition hover:bg-accent/90 disabled:opacity-40"
                      >
                        {busy ? "Восстанавливаю…" : "Да, восстановить"}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setConfirmingId(null);
                          setError(null);
                        }}
                        disabled={busy}
                        className="rounded-lg border border-surface-border px-3 py-1.5 text-xs text-ink-soft transition hover:bg-surface-muted disabled:opacity-40"
                      >
                        Отмена
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      onClick={() => {
                        setConfirmingId(item.checkpoint_id);
                        setError(null);
                        setDone(null);
                      }}
                      className="rounded-lg border border-surface-border px-2.5 py-1 text-xs font-medium text-ink-soft transition hover:bg-surface-muted"
                    >
                      Восстановить
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}

/* ---------------- Adjust mode ---------------- */
function AdjustMode({
  hasPlan,
  targetSessionId,
}: {
  hasPlan: boolean;
  targetSessionId: string | null;
}) {
  const { mutate: mutateGlobal } = useSWRConfig();
  const { data, mutate } = useSWR<ReconResponse>(
    hasPlan ? "/api/planning/reconciliation?weeks=1" : null,
    fetcher,
  );
  const [previewResult, setPreviewResult] = useState<RebalancePreviewResult | null>(null);
  const [result, setResult] = useState<RebalanceConfirmResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const targetRowRef = useRef<HTMLTableRowElement | null>(null);
  const focusedTargetRef = useRef<string | null>(null);

  useEffect(() => {
    if (!targetSessionId || !data || focusedTargetRef.current === targetSessionId) return;
    const targetRow = targetRowRef.current;
    if (!targetRow) return;
    const frame = window.requestAnimationFrame(() => {
      targetRow.scrollIntoView({ behavior: "smooth", block: "center" });
      const targetAction = targetRow.querySelector<HTMLElement>(
        '[data-target-action="primary"]',
      );
      (targetAction ?? targetRow).focus({ preventScroll: true });
      focusedTargetRef.current = targetSessionId;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [data, targetSessionId]);

  async function buildPreview() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const r = await postJSON<RebalancePreviewResult>("/api/planning/rebalance/preview", {
        weeks: 1,
      });
      setPreviewResult(r);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Не удалось подготовить пересборку");
    } finally {
      setBusy(false);
    }
  }

  async function confirmPreview() {
    const preview = previewResult?.preview;
    if (!preview || preview.status !== "proposal") return;
    setBusy(true);
    setError(null);
    try {
      const confirmed = await postJSON<RebalanceConfirmResult>("/api/planning/rebalance/confirm", {
        weeks: 1,
        as_of: preview.as_of,
        base_checkpoint_id: preview.base_checkpoint_id,
        preview_fingerprint: preview.preview_fingerprint,
      });
      setResult(confirmed);
      setPreviewResult(null);
      await mutate();
      mutateGlobal("/api/planning/status");
      mutateGlobal("/api/planning/history?limit=8");
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setPreviewResult(null);
        await mutate();
        setError("План или фактические данные изменились. Подготовьте новый preview.");
      } else {
        setError(e instanceof ApiError ? e.message : "Не удалось применить пересборку");
      }
    } finally {
      setBusy(false);
    }
  }

  async function resolveMatch(
    row: ReconResponse["rows"][number],
    action: "confirm" | "reject",
  ) {
    if (data?.base_checkpoint_id == null) return;
    setBusy(true);
    setError(null);
    try {
      await postJSON("/api/planning/reconciliation/matches", {
        base_checkpoint_id: data.base_checkpoint_id,
        session_id: row.session_id,
        activity_ids: action === "confirm" ? row.candidate_activities.map((item) => item.activity_id) : [],
        actual_role: null,
        action,
      });
      setPreviewResult(null);
      await mutate();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setPreviewResult(null);
        await mutate();
        setError("Активный план изменился. Проверьте сопоставление заново.");
      } else {
        setError(e instanceof ApiError ? e.message : "Не удалось сохранить сопоставление");
      }
    } finally {
      setBusy(false);
    }
  }

  if (!hasPlan) return <EmptyPlan />;
  if (!data) return <Skeleton />;

  const matchLabels: Record<string, string> = {
    matched: "Сопоставлено",
    ambiguous: "Нужно уточнить",
    unmatched: "Нет факта",
  };
  const adherenceLabels: Record<string, string> = {
    exact: "точно",
    substituted: "замена",
    major_deviation: "сильное отклонение",
    unknown: "не оценено",
  };
  const matchMethodLabels: Record<string, string> = {
    date_sport_heuristic: "по дате и виду спорта",
    ai_trainer_external_id: "по external_id Intervals.icu",
    user_confirmed: "подтверждено пользователем",
    user_rejected: "отклонено пользователем",
    admin_resolve: "сопоставлено вручную",
  };
  const reasonLabels: Record<string, string> = {
    data_gap: "Пока недостаточно надёжных сопоставлений — план не меняется.",
    no_change_under_plan: "Недовыполнение принято как факт: догонять объём автоматически не будем.",
    no_change_below_threshold: "Отклонение меньше 10 TSS — пересборка не нужна.",
    no_eligible_future_sessions: "Нет будущих лёгких сессий, которые можно безопасно уменьшить.",
  };
  const preview = previewResult?.preview;

  return (
    <>
      <section className="overflow-x-auto rounded-card border border-surface-border bg-surface shadow-card">
        <div className="border-b border-surface-border p-4">
          <div className="text-sm font-medium text-ink">План и факт · {data.window?.start}–{data.window?.end}</div>
          <div className="mt-1 text-xs text-ink-soft">
            Сопоставлено {data.data_quality?.matched_count ?? 0} из {data.data_quality?.planned_session_count ?? 0}
            {data.data_quality ? ` · coverage ${Math.round(data.data_quality.coverage * 100)}%` : ""}
            {data.provider?.status ? ` · Intervals: ${data.provider.status}` : ""}
          </div>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-border text-left text-xs uppercase tracking-wide text-ink-faint">
              <th className="px-3 py-2.5 font-medium">Дата</th>
              <th className="px-3 py-2.5 font-medium">Сессия</th>
              <th className="px-3 py-2.5 text-right font-medium">План TSS</th>
              <th className="px-3 py-2.5 text-right font-medium">Факт TSS</th>
              <th className="px-3 py-2.5 font-medium">Доказательство</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r) => {
              const isTarget = targetSessionId === r.session_id;
              return (
              <tr
                key={r.session_id}
                ref={isTarget ? targetRowRef : undefined}
                tabIndex={isTarget ? -1 : undefined}
                aria-current={isTarget ? "true" : undefined}
                className={`border-b border-surface-border last:border-0 align-top transition ${
                  isTarget ? "bg-accent/10 ring-1 ring-inset ring-accent/40" : ""
                }`}
              >
                <td className="px-3 py-2.5 text-ink-soft">{r.date.slice(5)}</td>
                <td className="px-3 py-2.5 text-ink">
                  <div>{r.name}</div>
                  <div className="mt-0.5 text-xs text-ink-faint">{r.sport} · {r.role}</div>
                </td>
                <td className="px-3 py-2.5 text-right tabular-nums text-ink">
                  {r.tss}
                </td>
                <td className="px-3 py-2.5 text-right tabular-nums text-ink">
                  {r.actual_total_tss}
                  {r.actual_activities.length ? (
                    <div className="mt-1 text-[11px] text-ink-faint">
                      {r.actual_activities.map((item) => `${item.name} ${item.tss} TSS`).join(" · ")}
                    </div>
                  ) : null}
                </td>
                <td className="px-3 py-2.5">
                  <div className={r.match_status === "ambiguous" ? "text-tone-warning" : r.match_status === "matched" ? "text-tone-success" : "text-ink-soft"}>
                    {matchLabels[r.match_status] ?? r.match_status}
                  </div>
                  <div className="mt-0.5 text-xs text-ink-faint">
                    {matchMethodLabels[r.match_method] ?? r.match_method} ·{" "}
                    {adherenceLabels[r.adherence] ?? r.adherence}
                    {r.adherence === "unknown" && r.match_status === "matched"
                      ? " — подтвердите сопоставление"
                      : ""}{" "}
                    · {Math.round(r.confidence * 100)}%
                  </div>
                  {r.evidence[0] ? <div className="mt-1 max-w-xs text-[11px] text-ink-faint">{r.evidence[0]}</div> : null}
                  {r.match_status === "ambiguous" && r.candidate_activities.length ? (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <button
                        type="button"
                        data-target-action="primary"
                        onClick={() => resolveMatch(r, "confirm")}
                        disabled={busy}
                        className="rounded border border-tone-success/30 px-2 py-1 text-[11px] text-tone-success disabled:opacity-40"
                      >
                        Сопоставить {r.candidate_activities.length} акт.
                      </button>
                      <button
                        type="button"
                        onClick={() => resolveMatch(r, "reject")}
                        disabled={busy}
                        className="rounded border border-surface-border px-2 py-1 text-[11px] text-ink-soft disabled:opacity-40"
                      >
                        Не относится
                      </button>
                    </div>
                  ) : null}
                </td>
              </tr>
              );
            })}
          </tbody>
        </table>
        {data.unplanned_activities.length ? (
          <div className="border-t border-surface-border bg-surface-muted/40 p-4 text-xs text-ink-soft">
            <div className="font-medium text-ink">Несопоставленная нагрузка · {data.metrics?.unplanned_tss ?? 0} TSS</div>
            <div className="mt-1">
              {data.unplanned_activities.map((item) => `${item.date.slice(5)} ${item.name} · ${item.sport} · ${item.tss} TSS`).join("; ")}
            </div>
          </div>
        ) : null}
        <div className="p-4">
          <button
            type="button"
            onClick={buildPreview}
            disabled={busy}
            className="rounded-lg bg-accent px-6 py-2.5 text-sm font-medium text-accent-foreground transition hover:bg-accent/90 disabled:opacity-40"
          >
            {busy ? "Проверяю…" : "Подготовить future-only preview"}
          </button>
          {error ? (
            <div className="mt-3 rounded-lg bg-tone-danger/10 px-3 py-2 text-sm text-tone-danger">
              {error}
            </div>
          ) : null}
        </div>
      </section>

      {preview ? (
        <section className="rounded-card border border-surface-border bg-surface p-4 shadow-card">
          <div className="text-sm font-medium text-ink">
            {preview.status === "proposal" ? `Предложение: ${preview.future_tss_delta} TSS только в будущем` : "План остаётся без изменений"}
          </div>
          {preview.status === "no_change" ? (
            <div className="mt-2 text-sm text-ink-soft">{reasonLabels[preview.reason] ?? preview.reason}</div>
          ) : (
            <>
              <div className="mt-2 space-y-2 text-sm text-ink-soft">
                {preview.changes.map((item) => (
                  <div key={item.session_id} className="flex justify-between rounded-lg bg-surface-muted px-3 py-2">
                    <span>{item.date} · easy</span>
                    <span className="tabular-nums">{item.before_tss} → {item.after_tss} TSS</span>
                  </div>
                ))}
              </div>
              <div className="mt-3 text-xs text-ink-faint">
                Сегодня и прошлое, гонки, отдых, ограничения и ручные правки не меняются.
                {preview.unused_reduction_tss > 0 ? ` Неиспользованный лимит: ${preview.unused_reduction_tss} TSS.` : ""}
              </div>
              <button
                type="button"
                onClick={confirmPreview}
                disabled={busy}
                className="mt-4 rounded-lg bg-accent px-6 py-2.5 text-sm font-medium text-accent-foreground disabled:opacity-40"
              >
                {busy ? "Применяю…" : "Подтвердить пересборку"}
              </button>
            </>
          )}
        </section>
      ) : null}

      {result ? (
        <section className="rounded-card border border-tone-success/30 bg-tone-success/10 p-4 text-sm text-tone-success shadow-card">
          Создан checkpoint #{result.applied_checkpoint_id}. Прошлая версия осталась в истории.
        </section>
      ) : null}
    </>
  );
}

/* ---------------- Export mode ---------------- */
function ExportMode() {
  const { data } = useSWR<PlanExport>("/api/planning/plan", fetcher);
  const [deliveryDays, setDeliveryDays] = useState<7 | 14>(7);
  const [deliveryBusy, setDeliveryBusy] = useState(false);
  const [deliveryResult, setDeliveryResult] = useState<IntervalsDeliveryResult | null>(null);
  const [deliveryError, setDeliveryError] = useState("");

  async function deliverToIntervals() {
    setDeliveryBusy(true);
    setDeliveryError("");
    try {
      const result = await postJSON<IntervalsDeliveryResult>(
        "/api/planning/delivery/intervals",
        { days: deliveryDays },
      );
      setDeliveryResult(result);
    } catch (error) {
      setDeliveryError(error instanceof Error ? error.message : "Не удалось доставить план");
    } finally {
      setDeliveryBusy(false);
    }
  }

  if (!data) return <Skeleton />;
  if (!data.has_plan) return <EmptyPlan />;

  return (
    <>
      <section className="flex flex-wrap items-center gap-3 rounded-card border border-surface-border bg-surface p-4 shadow-card">
        <div className="text-sm font-medium text-ink">
          {data.goal?.goal_type} · {data.goal?.distance}
        </div>
        <a
          href={withDemo("/api/planning/export/ics")}
          className="ml-auto rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-foreground transition hover:bg-accent/90"
        >
          📅 Весь план в календарь (ICS)
        </a>
      </section>

      <section className="rounded-card border border-surface-border bg-surface p-4 shadow-card">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-sm font-medium text-ink">Доставить через Intervals.icu</div>
            <p className="mt-1 max-w-2xl text-xs text-ink-faint">
              Обновляет только события AI Trainer с защищённым идентификатором. Чужие тренировки,
              гонки и ручные записи не изменяются.
            </p>
          </div>
          <div className="flex items-center gap-2">
            {([7, 14] as const).map((days) => (
              <button
                key={days}
                type="button"
                onClick={() => setDeliveryDays(days)}
                className={`rounded-md border px-3 py-1.5 text-xs ${
                  deliveryDays === days
                    ? "border-accent bg-accent/10 text-accent"
                    : "border-surface-border text-ink-soft"
                }`}
              >
                {days} дней
              </button>
            ))}
            <button
              type="button"
              onClick={deliverToIntervals}
              disabled={!data.delivery.configured || deliveryBusy}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-foreground disabled:cursor-not-allowed disabled:opacity-40"
            >
              {deliveryBusy ? "Доставляю…" : "Отправить план"}
            </button>
          </div>
        </div>
        {!data.delivery.configured ? (
          <p className="mt-3 text-xs text-tone-warning">
            Intervals.icu не настроен: добавьте INTERVALS_ICU_API_KEY в локальный .env.
          </p>
        ) : null}
        {deliveryError ? <p className="mt-3 text-xs text-tone-danger">{deliveryError}</p> : null}
        {deliveryResult ? (
          <div className="mt-4 grid gap-2 text-xs sm:grid-cols-4">
            <div className="rounded-lg bg-tone-success/10 p-3 text-tone-success">
              Исполняемые: <strong>{deliveryResult.executable_count}</strong>
            </div>
            <div className="rounded-lg bg-tone-warning/10 p-3 text-tone-warning">
              Только календарь: <strong>{deliveryResult.calendar_only_count}</strong>
            </div>
            <div className="rounded-lg bg-surface-muted p-3 text-ink-soft">
              Удалено старых AI Trainer: <strong>{deliveryResult.deleted_count}</strong>
            </div>
            <div className="rounded-lg bg-tone-danger/10 p-3 text-tone-danger">
              Ошибки: <strong>{deliveryResult.failed_count}</strong>
            </div>
            {deliveryResult.target_mismatch_count > 0 ? (
              <p className="sm:col-span-4 text-tone-danger">
                Intervals.icu потерял или изменил цели темпа: {deliveryResult.target_mismatch_count}.
                Доставка не считается успешной; старые тренировки AI Trainer сохранены.
              </p>
            ) : null}
            {deliveryResult.error ? (
              <p className="sm:col-span-4 text-tone-danger">{deliveryResult.error}</p>
            ) : null}
          </div>
        ) : null}
      </section>

      <section className="overflow-x-auto rounded-card border border-surface-border bg-surface shadow-card">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-border text-left text-xs uppercase tracking-wide text-ink-faint">
              <th className="px-3 py-2.5 font-medium">Дата</th>
              <th className="px-3 py-2.5 font-medium">Сессия</th>
              <th className="px-3 py-2.5 text-right font-medium">TSS</th>
              <th className="px-3 py-2.5 text-right font-medium">Экспорт</th>
            </tr>
          </thead>
          <tbody>
            {data.days.map((d) => (
              <Fragment key={d.index}>
                <tr className="border-b border-surface-border/70">
                  <td className="px-3 py-2.5 text-ink-soft">{d.date.slice(5)}</td>
                  <td className="px-3 py-2.5 text-ink">
                    <div className="font-medium">
                      {d.sessions?.length > 1
                        ? `${d.sessions.length} тренировки`
                        : d.template_name || d.sport_label}
                      {d.kind === "composite" ? " · вело → бег" : ""}
                    </div>
                    <div className="text-xs text-ink-faint">
                      {[d.stimulus, d.phase].filter(Boolean).join(" · ") || d.name}
                    </div>
                    {d.fatigue_cost.length ? (
                      <div className="mt-1 text-[11px] text-ink-faint">
                        fatigue {d.fatigue_cost.join("/")}
                        {d.expected_recovery_hours
                          ? ` · восстановление ~${d.expected_recovery_hours} ч`
                          : ""}
                        </div>
                      ) : null}
                    {(d.sessions?.length ?? 0) <= 1 && d.kind !== "composite" ? (
                      <TargetBasis provenance={d.target_provenance} />
                    ) : null}
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-ink">{d.tss}</td>
                  <td className="px-3 py-2.5 text-right">
                    {!d.executable ? (
                      <span className="text-xs text-tone-negative">нужен ремонт</span>
                    ) : d.sessions?.length > 1 ? (
                      <span className="text-xs text-ink-faint">по сессиям</span>
                    ) : d.kind === "composite" && d.legs.length ? (
                      <span className="inline-flex flex-col gap-1">
                        {d.legs.map((leg) => (
                          <span key={leg.leg_index} className="inline-flex justify-end gap-1">
                            <span className="mr-1 text-[11px] text-ink-faint">
                              {leg.sport}
                            </span>
                            <DownloadLink index={d.index} leg={leg.leg_index ?? undefined} fmt="tcx" label="TCX" />
                            <DownloadLink index={d.index} leg={leg.leg_index ?? undefined} fmt="fit_csv" label="FIT" />
                          </span>
                        ))}
                      </span>
                    ) : (
                      <span className="inline-flex gap-2">
                        <DownloadLink index={d.index} fmt="tcx" label="TCX" />
                        <DownloadLink index={d.index} fmt="fit_csv" label="FIT-CSV" />
                      </span>
                    )}
                  </td>
                </tr>
                {d.steps.length || d.legs.length || d.sessions?.length > 1 || !d.executable ? (
                  <tr className="border-b border-surface-border last:border-0">
                    <td colSpan={4} className="px-3 pb-3 pt-0">
                      {!d.executable ? (
                        <div className="rounded-lg border border-tone-negative/30 bg-tone-negative/5 p-2.5 text-xs text-tone-negative">
                          Тренировка не имеет сохранённой структуры. Экспорт и отправка
                          заблокированы до безопасного ремонта плана.
                        </div>
                      ) : d.sessions?.length > 1 ? (
                        <div className="grid gap-2 sm:grid-cols-2">
                          {d.sessions.map((session) => (
                            <div
                              key={session.session_id || `${session.sport}-${session.name}`}
                              className="rounded-lg bg-surface-muted p-2.5"
                            >
                              <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-medium text-ink">
                                <span>
                                  {session.template_name || session.sport_label || session.name}
                                </span>
                                <span className="font-normal text-ink-faint">
                                  {session.duration_minutes} мин · {session.tss} TSS
                                </span>
                              </div>
                              {session.kind !== "composite" ? (
                                <TargetBasis provenance={session.target_provenance} />
                              ) : null}
                              {session.session_id &&
                              session.kind === "composite" &&
                              session.legs.length ? (
                                <div className="mt-2 grid gap-2">
                                  {session.legs.map((leg) => (
                                    <div
                                      key={leg.leg_index}
                                      className="rounded-md border border-surface-border bg-surface px-2 py-1.5"
                                    >
                                      <div className="flex flex-wrap items-center justify-between gap-2">
                                        <span className="text-[11px] text-ink-faint">
                                          {leg.leg_index}. {leg.template_name || leg.sport}
                                        </span>
                                        <span className="inline-flex gap-1">
                                          <DownloadLink
                                            index={d.index}
                                            sessionId={session.session_id ?? undefined}
                                            leg={leg.leg_index ?? undefined}
                                            fmt="tcx"
                                            label="TCX"
                                          />
                                          <DownloadLink
                                            index={d.index}
                                            sessionId={session.session_id ?? undefined}
                                            leg={leg.leg_index ?? undefined}
                                            fmt="fit_csv"
                                            label="FIT"
                                          />
                                        </span>
                                      </div>
                                      <TargetBasis provenance={leg.target_provenance} />
                                      <StepPreview steps={leg.steps} />
                                    </div>
                                  ))}
                                </div>
                              ) : session.session_id ? (
                                <div className="mt-2 flex gap-2">
                                  <DownloadLink
                                    index={d.index}
                                    sessionId={session.session_id}
                                    fmt="tcx"
                                    label="TCX"
                                  />
                                  <DownloadLink
                                    index={d.index}
                                    sessionId={session.session_id}
                                    fmt="fit_csv"
                                    label="FIT-CSV"
                                  />
                                </div>
                              ) : null}
                              <StepPreview steps={session.steps} />
                            </div>
                          ))}
                        </div>
                      ) : d.kind === "composite" ? (
                        <div className="grid gap-2 sm:grid-cols-2">
                          {d.legs.map((leg) => (
                            <div key={leg.leg_index} className="rounded-lg bg-surface-muted p-2.5">
                              <div className="text-xs font-medium text-ink">
                                {leg.leg_index}. {leg.template_name || leg.sport}
                                <span className="ml-1 font-normal text-ink-faint">
                                  {leg.duration_minutes} мин · {leg.target_tss} TSS
                                </span>
                              </div>
                              <TargetBasis provenance={leg.target_provenance} />
                              <StepPreview steps={leg.steps} />
                            </div>
                          ))}
                        </div>
                      ) : (
                        <StepPreview steps={d.steps} />
                      )}
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}

function DownloadLink({
  index,
  fmt,
  label,
  leg,
  sessionId,
}: {
  index: number;
  fmt: string;
  label: string;
  leg?: number;
  sessionId?: string;
}) {
  const legQuery = leg ? `&leg=${leg}` : "";
  const sessionQuery = sessionId ? `&session_id=${encodeURIComponent(sessionId)}` : "";
  return (
    <a
      href={withDemo(
        `/api/planning/export/workout/${index}?fmt=${fmt}${legQuery}${sessionQuery}`,
      )}
      className="rounded-md border border-surface-border px-2 py-1 text-xs text-tone-neutral transition hover:bg-surface-muted"
    >
      {label}
    </a>
  );
}

function StepPreview({ steps }: { steps: Array<{ name: string | null; duration_seconds: number | null; target: Record<string, unknown> | null }> }) {
  if (!steps.length) return null;
  return (
    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-ink-faint">
      {steps.map((step, index) => (
        <span key={`${step.name}-${index}`}>
          {step.name || `Шаг ${index + 1}`} · {formatStepDuration(step.duration_seconds)}
          {formatTarget(step.target) ? ` · ${formatTarget(step.target)}` : ""}
        </span>
      ))}
    </div>
  );
}

function formatPaceSeconds(seconds: number, unit = "seconds_per_km"): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "—";
  const rounded = Math.round(seconds);
  const suffix = unit.endsWith("100m") ? "/100м" : "/км";
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, "0")}${suffix}`;
}

function targetBasisLabel(provenance: Record<string, unknown> | null): string {
  if (!provenance) return "";
  const kind = String(provenance.kind || "");
  const value = Number(provenance.value);
  if (kind === "threshold_pace" && Number.isFinite(value) && value > 0) {
    return `по пороговому темпу ${formatPaceSeconds(value)}`;
  }
  if (kind === "lthr" && Number.isFinite(value) && value > 0) {
    return `по LTHR ${Math.round(value)}`;
  }
  if (kind === "relative_rpe") return "по RPE";
  if (kind === "ftp" && Number.isFinite(value) && value > 0) {
    return `по FTP ${Math.round(value)} Вт`;
  }
  if (kind === "css" && Number.isFinite(value) && value > 0) {
    return `по CSS ${formatPaceSeconds(value, "seconds_per_100m")}`;
  }
  return "";
}

function TargetBasis({ provenance }: { provenance: Record<string, unknown> | null }) {
  const label = targetBasisLabel(provenance);
  if (!label) return null;
  return (
    <div className="mt-1 text-[10px] font-medium text-tone-neutral">
      Основание: {label}
    </div>
  );
}

function formatStepDuration(seconds: number | null): string {
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
  if (type === "pace") {
    const fast = Number(target.fast ?? target.low);
    const slow = Number(target.slow ?? target.high ?? target.fast ?? target.low);
    if (Number.isFinite(fast) && fast > 0 && Number.isFinite(slow) && slow > 0) {
      const unit = String(target.unit || "seconds_per_km");
      return `${formatPaceSeconds(fast, unit)}–${formatPaceSeconds(slow, unit)}`;
    }
  }
  if (type === "relative_rpe" && low != null && high != null) return `RPE ${low}–${high}`;
  return type;
}

/* ---------------- Shared ---------------- */
function Skeleton() {
  return <div className="h-40 animate-pulse rounded-card bg-surface" />;
}

function EmptyPlan() {
  return (
    <div className="rounded-card border border-surface-border bg-surface p-6 text-center shadow-card">
      <div className="text-lg font-semibold text-ink">Активного плана нет</div>
      <p className="mt-1 text-sm text-ink-soft">
        Соберите план во вкладке «Собрать план» — затем откроются корректировка и экспорт.
      </p>
    </div>
  );
}
