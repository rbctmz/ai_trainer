"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { ApiError, fetcher, postJSON, withDemo } from "@/lib/api";
import {
  AdjustResult,
  BuiltPlan,
  ForecastPoint,
  Outcome,
  PlanningEventsResponse,
  PlanningDemand,
  PlanningHistory,
  PlanExport,
  PlanningStatus,
  PlanWeek,
  ReconResponse,
  ReconRow,
  RaceEvent,
  TargetPreview,
} from "@/lib/types";

const GOAL_TYPES = [
  { value: "triathlon", label: "Триатлон" },
  { value: "run", label: "Бег" },
  { value: "bike", label: "Вело" },
];

const DISTANCES: Record<string, { value: string; label: string }[]> = {
  triathlon: [
    { value: "sprint", label: "Спринт" },
    { value: "olympic", label: "Олимпийка" },
    { value: "half", label: "Half (70.3)" },
    { value: "ironman", label: "Ironman" },
  ],
  run: [
    { value: "5k", label: "5 км" },
    { value: "10k", label: "10 км" },
    { value: "half_marathon", label: "Полумарафон" },
    { value: "marathon", label: "Марафон" },
    { value: "ultra", label: "Ультра" },
  ],
  bike: [
    { value: "40k_tt", label: "40 км TT" },
    { value: "100k", label: "100 км" },
    { value: "100mi", label: "100 миль" },
    { value: "brevet", label: "200 км (бревет)" },
    { value: "stage_race", label: "Этапная гонка" },
  ],
};

const DAYS = [
  { value: "mon", label: "Пн" },
  { value: "tue", label: "Вт" },
  { value: "wed", label: "Ср" },
  { value: "thu", label: "Чт" },
  { value: "fri", label: "Пт" },
  { value: "sat", label: "Сб" },
  { value: "sun", label: "Вс" },
];

const OUTCOMES: { value: Outcome; label: string }[] = [
  { value: "as_planned", label: "По плану" },
  { value: "skipped", label: "Пропущено" },
  { value: "reduced", label: "Урезано" },
  { value: "unavailable", label: "Недоступно" },
];

const TABS = ["build", "adjust", "export"] as const;
type Tab = (typeof TABS)[number];
const TAB_LABELS: Record<Tab, string> = {
  build: "Собрать план",
  adjust: "Скорректировать",
  export: "Экспорт",
};

const DEFAULT_DEMAND_OPTIONS: PlanningDemand[] = [
  { level: "easy", label: "Легко", multiplier: 0.9 },
  { level: "moderate", label: "Умеренно", multiplier: 1.0 },
  { level: "demanding", label: "Требовательно", multiplier: 1.1 },
  { level: "aggressive", label: "Агрессивно", multiplier: 1.2 },
];

type PlanningMode = "event_goal" | "training_goal" | "manual";

const PLANNING_MODES: Array<{ value: PlanningMode; label: string; detail: string }> = [
  { value: "event_goal", label: "К старту", detail: "A-цель с B/C-оверлеями" },
  { value: "training_goal", label: "Развивать форму", detail: "Без выдуманной даты гонки" },
  { value: "manual", label: "Ручные фазы", detail: "Фазы задаёте вы" },
];

function defaultEventDate(): string {
  const d = new Date();
  d.setDate(d.getDate() + 56);
  return d.toISOString().slice(0, 10);
}

export default function PlanningPage() {
  const { data: status } = useSWR<PlanningStatus>("/api/planning/status", fetcher);
  const [tab, setTab] = useState<Tab>("build");
  const m = status?.metrics;

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

      <div className="flex gap-1 rounded-card border border-surface-border bg-surface p-1 shadow-card">
        {TABS.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition ${
              tab === t ? "bg-accent text-accent-foreground" : "text-ink-soft hover:bg-surface-muted"
            }`}
          >
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>

      {tab === "build" ? <BuildMode status={status} /> : null}
      {tab === "adjust" ? <AdjustMode hasPlan={status?.has_plan ?? false} /> : null}
      {tab === "export" ? <ExportMode /> : null}
      <AdjustmentHistory />
    </main>
  );
}

/* ---------------- Build mode ---------------- */
function BuildMode({ status }: { status?: PlanningStatus }) {
  const { mutate } = useSWRConfig();
  const [planningMode, setPlanningMode] = useState<PlanningMode>("event_goal");
  const [intent, setIntent] = useState<"maintain" | "develop">("develop");
  const [horizonWeeks, setHorizonWeeks] = useState(8);
  const [manualPhases, setManualPhases] = useState(
    "Base, Base, Build, Recovery, Base, Build, Build, Recovery",
  );
  const [goalType, setGoalType] = useState("triathlon");
  const [distance, setDistance] = useState("olympic");
  const [eventDate, setEventDate] = useState(defaultEventDate);
  const [hours, setHours] = useState(10);
  const [days, setDays] = useState<string[]>(DAYS.map((d) => d.value));
  const [demand, setDemand] = useState("moderate");
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [plan, setPlan] = useState<BuiltPlan | null>(null);
  const [selectedEvents, setSelectedEvents] = useState<RaceEvent[]>([]);
  const [lastRequest, setLastRequest] = useState<Record<string, unknown> | null>(null);
  const demandOptions = status?.demand_options?.length ? status.demand_options : DEFAULT_DEMAND_OPTIONS;

  useEffect(() => {
    if (status?.demand?.level) {
      setDemand(status.demand.level);
    }
  }, [status?.demand?.level]);

  const previewKey = useMemo(() => {
    if (!days.length) return null;
    const params = new URLSearchParams({
      goal_type: goalType,
      distance,
      available_hours: String(hours),
      available_days: days.join(","),
      demand,
    });
    return `/api/planning/target-preview?${params.toString()}`;
  }, [goalType, distance, hours, days, demand]);
  const { data: preview } = useSWR<TargetPreview>(previewKey, fetcher);
  const { data: discovered, error: eventDiscoveryError } = useSWR<PlanningEventsResponse>(
    "/api/planning/events?days=365",
    fetcher,
    { shouldRetryOnError: false },
  );

  function onGoalChange(v: string) {
    setGoalType(v);
    setDistance(DISTANCES[v][v === "run" ? 2 : 1].value);
  }
  function toggleDay(v: string) {
    setDays((d) => (d.includes(v) ? d.filter((x) => x !== v) : [...d, v]));
  }
  function toggleEvent(event: RaceEvent) {
    const key = `${event.source ?? "event"}:${event.source_id ?? event.date}:${event.priority}`;
    const isAlreadySelected = selectedEvents.some(
      (item) => `${item.source ?? "event"}:${item.source_id ?? item.date}:${item.priority}` === key,
    );
    if (!isAlreadySelected && event.priority === "A" && event.confirmed !== false) {
      setPlanningMode("event_goal");
    }
    setPlan(null);
    setLastRequest(null);
    setSelectedEvents((current) =>
      current.some((item) => `${item.source ?? "event"}:${item.source_id ?? item.date}:${item.priority}` === key)
        ? current.filter((item) => `${item.source ?? "event"}:${item.source_id ?? item.date}:${item.priority}` !== key)
        : [...current, event],
    );
  }
  function requestPayload(): Record<string, unknown> {
    const parsedManual = manualPhases.split(",").map((value) => value.trim()).filter(Boolean);
    return {
      goal_type: goalType,
      distance,
      event_date: planningMode === "event_goal" && selectedEvents.length === 0 ? eventDate : null,
      events: selectedEvents,
      planning_mode: planningMode,
      intent,
      focus: "balanced_triathlon",
      horizon_weeks: planningMode === "event_goal" ? 8 : horizonWeeks,
      manual_phases: planningMode === "manual" ? parsedManual : null,
      available_hours: hours,
      available_days: days,
      demand,
    };
  }
  async function build() {
    setBuilding(true);
    setError(null);
    try {
      const request = requestPayload();
      setLastRequest(request);
      setPlan(await postJSON<BuiltPlan>("/api/planning/build", { ...request, persist: false, confirm: false }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Не удалось собрать план");
    } finally {
      setBuilding(false);
    }
  }
  async function confirmPlan() {
    if (!lastRequest) return;
    setBuilding(true);
    setError(null);
    try {
      const confirmed = await postJSON<BuiltPlan>("/api/planning/build", {
        ...lastRequest,
        persist: true,
        confirm: true,
        base_checkpoint_id: plan?.preview.base_checkpoint_id ?? 0,
      });
      setPlan(confirmed);
      await Promise.all([mutate("/api/planning/status"), mutate("/api/planning/history?limit=8")]);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Не удалось подтвердить план");
    } finally {
      setBuilding(false);
    }
  }

  return (
    <>
      <section className="rounded-card border border-surface-border bg-surface p-5 shadow-card">
        <Field label="Подход к планированию">
          <div className="mb-4 grid gap-2 sm:grid-cols-3">
            {PLANNING_MODES.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => {
                  setPlanningMode(option.value);
                  setPlan(null);
                  setLastRequest(null);
                }}
                className={`rounded-lg border px-3 py-3 text-left transition ${
                  planningMode === option.value
                    ? "border-accent bg-accent/10 text-ink"
                    : "border-surface-border text-ink-soft hover:bg-surface-muted"
                }`}
              >
                <span className="block text-sm font-semibold">{option.label}</span>
                <span className="mt-1 block text-xs">{option.detail}</span>
              </button>
            ))}
          </div>
        </Field>

        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Тип цели">
            <Select value={goalType} onChange={onGoalChange} options={GOAL_TYPES} />
          </Field>
          <Field label="Дистанция">
            <Select value={distance} onChange={setDistance} options={DISTANCES[goalType]} />
          </Field>
          {planningMode === "event_goal" ? (
            <Field label="Дата A-старта">
              <input
                type="date"
                value={eventDate}
                onChange={(e) => setEventDate(e.target.value)}
                className="w-full rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm"
              />
            </Field>
          ) : (
            <Field label="Горизонт">
              <Select
                value={String(horizonWeeks)}
                onChange={(value) => setHorizonWeeks(Number(value))}
                options={[4, 6, 8].map((value) => ({ value: String(value), label: `${value} недель` }))}
              />
            </Field>
          )}
        </div>

        {planningMode !== "event_goal" ? (
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <Field label="Намерение">
              <Select
                value={intent}
                onChange={(value) => setIntent(value as "maintain" | "develop")}
                options={[
                  { value: "develop", label: "Развивать форму" },
                  { value: "maintain", label: "Поддерживать форму" },
                ]}
              />
            </Field>
            {planningMode === "manual" ? (
              <Field label={`Фазы через запятую — ровно ${horizonWeeks}`}>
                <input
                  value={manualPhases}
                  onChange={(event) => setManualPhases(event.target.value)}
                  className="w-full rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm"
                />
              </Field>
            ) : null}
          </div>
        ) : null}

        {discovered?.events.length ? (
          <Field label="События из Intervals.icu · только чтение">
            <div className="mt-4 grid gap-2 sm:grid-cols-2">
              {discovered.events.map((event) => {
                const selected = selectedEvents.some(
                  (item) => (item.source_id || item.date) === (event.source_id || event.date) && item.priority === event.priority,
                );
                return (
                  <button
                    key={`${event.source_id || event.date}-${event.priority}`}
                    type="button"
                    onClick={() => toggleEvent(event)}
                    className={`rounded-lg border px-3 py-2 text-left text-xs transition ${
                      selected ? "border-accent bg-accent/10" : "border-surface-border hover:bg-surface-muted"
                    }`}
                  >
                    <span className="font-semibold text-ink">{event.priority} · {event.label || "Без названия"}</span>
                    <span className="mt-1 block text-ink-soft">
                      {event.date} · {event.discipline || "спорт нужно подтвердить"}
                    </span>
                  </button>
                );
              })}
            </div>
          </Field>
        ) : eventDiscoveryError ? (
          <div className="mt-4 text-xs text-ink-faint">
            События Intervals.icu сейчас недоступны — можно продолжить с ручными параметрами.
          </div>
        ) : null}

        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <Field label={`Часов в неделю: ${hours}`}>
            <input
              type="range"
              min={3}
              max={20}
              step={0.5}
              value={hours}
              onChange={(e) => setHours(Number(e.target.value))}
              className="w-full"
            />
          </Field>
          <Field label="Доступные дни">
            <div className="flex flex-wrap gap-1.5">
              {DAYS.map((d) => (
                <button
                  key={d.value}
                  type="button"
                  onClick={() => toggleDay(d.value)}
                  className={`rounded-lg border px-2.5 py-1.5 text-xs font-medium transition ${
                    days.includes(d.value)
                      ? "border-accent bg-accent text-accent-foreground"
                      : "border-surface-border text-ink-soft hover:bg-surface-muted"
                  }`}
                >
                  {d.label}
                </button>
              ))}
            </div>
          </Field>
        </div>

        <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_1.4fr]">
          <Field label="Режим нагрузки">
            <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4 lg:grid-cols-2">
              {demandOptions.map((option) => (
                <button
                  key={option.level}
                  type="button"
                  onClick={() => setDemand(option.level)}
                  className={`rounded-lg border px-3 py-2 text-left text-xs font-medium transition ${
                    demand === option.level
                      ? "border-accent bg-accent text-accent-foreground"
                      : "border-surface-border text-ink-soft hover:bg-surface-muted"
                  }`}
                >
                  <span className="block">{option.label}</span>
                  <span className="text-[11px] opacity-70">×{option.multiplier.toFixed(2)}</span>
                </button>
              ))}
            </div>
          </Field>
          <WeeklyTargetPreview preview={preview} />
        </div>

        <button
          type="button"
          onClick={build}
          disabled={building || days.length === 0}
          className="mt-5 w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-accent-foreground transition hover:bg-accent/90 disabled:opacity-40 sm:w-auto sm:px-8"
        >
          {building ? "Собираю план…" : "🧭 Предпросмотр плана"}
        </button>

        {error ? (
          <div className="mt-3 rounded-lg bg-tone-danger/10 px-3 py-2 text-sm text-tone-danger">
            {error}
          </div>
        ) : null}
      </section>

      {plan ? (
        <>
          <section className="rounded-card border border-surface-border bg-surface p-4 shadow-card">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-xs font-medium uppercase tracking-wide text-ink-faint">
                  {plan.plan_id ? "План сохранён" : "Предпросмотр · SQLite не изменён"}
                </div>
                <div className="mt-1 text-sm text-ink-soft">
                  Изменение нагрузки: {plan.preview.weekly_tss_delta >= 0 ? "+" : ""}{plan.preview.weekly_tss_delta} TSS · {plan.event_overlay.rule_version}
                </div>
              </div>
              {!plan.plan_id ? (
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => { setPlan(null); setLastRequest(null); }}
                    className="rounded-lg border border-surface-border px-3 py-2 text-sm text-ink-soft"
                  >
                    Отменить
                  </button>
                  <button
                    type="button"
                    onClick={confirmPlan}
                    disabled={building}
                    className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-foreground disabled:opacity-40"
                  >
                    Подтвердить и сохранить
                  </button>
                </div>
              ) : null}
            </div>
          </section>
          <section className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            <Stat label="Горизонт" value={plan.goal.weeks_to_race ? `${plan.goal.weeks_to_race} нед. до старта` : `${plan.weeks.length} нед. rolling`} />
            <Stat label="Цель/нед" value={`${plan.weekly_target.target_weekly_tss} TSS`} />
            <Stat label="Режим" value={plan.weekly_target.demand?.label ?? "—"} />
            <Stat label="Пик" value={`${plan.totals.peak_tss} TSS`} />
            <Stat label="Всего" value={`${plan.totals.total_tss} TSS`} />
          </section>
          {plan.weekly_target.breakdown ? (
            <WeeklyTargetPreview
              preview={{
                goal: plan.goal,
                weekly_target: plan.weekly_target,
                breakdown: plan.weekly_target.breakdown,
                demand: plan.weekly_target.demand ?? { level: demand, label: demand, multiplier: 1 },
                options: demandOptions,
              }}
            />
          ) : null}
          <ForecastSection forecast={plan.forecast} />
          <WeeksTable weeks={plan.weeks} />
        </>
      ) : null}
    </>
  );
}

function WeeklyTargetPreview({ preview }: { preview?: TargetPreview | null }) {
  if (!preview) {
    return (
      <section className="rounded-card border border-surface-border bg-surface-muted/40 p-4">
        <div className="text-xs font-medium uppercase tracking-wide text-ink-faint">
          Weekly Target
        </div>
        <div className="mt-3 h-16 animate-pulse rounded-lg bg-surface-muted" />
      </section>
    );
  }

  const target = preview.weekly_target;
  const demand = target.demand ?? preview.demand;
  return (
    <section className="rounded-card border border-surface-border bg-surface-muted/40 p-4">
      <div className="flex items-baseline justify-between gap-3">
        <div className="text-xs font-medium uppercase tracking-wide text-ink-faint">
          Weekly Target
        </div>
        <div className="text-sm font-semibold text-ink">
          {target.target_weekly_tss} TSS
          <span className="ml-2 text-xs font-medium text-ink-soft">
            {demand?.label} ×{Number(demand?.multiplier ?? 1).toFixed(2)}
          </span>
        </div>
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {preview.breakdown.rows.map((row) => (
          <div key={row.key} className="rounded-lg border border-surface-border bg-surface px-3 py-2">
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-xs text-ink-faint">{row.label}</span>
              <span className="text-sm font-semibold tabular-nums text-ink">
                {row.value} <span className="text-xs font-medium text-ink-soft">{row.unit}</span>
              </span>
            </div>
            <div className="mt-1 text-[11px] leading-snug text-ink-soft">{row.detail}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function AdjustmentHistory() {
  const { data } = useSWR<PlanningHistory>("/api/planning/history?limit=8", fetcher);
  if (!data || !data.has_history) return null;

  return (
    <section className="rounded-card border border-surface-border bg-surface p-4 shadow-card">
      <div className="mb-3 flex items-baseline justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-ink-faint">
          Adjustment History
        </span>
        <span className="text-xs text-ink-soft">{data.items.length}</span>
      </div>
      <div className="divide-y divide-surface-border">
        {data.items.map((item) => (
          <div key={`${item.checkpoint_id}-${item.date}`} className="grid gap-2 py-2.5 sm:grid-cols-[110px_130px_1fr]">
            <div className="text-xs tabular-nums text-ink-soft">
              {item.date_label || item.date.slice(0, 10)}
            </div>
            <div className="text-xs font-medium text-ink">{item.type_label}</div>
            <div className="text-sm text-ink-soft">{item.outcome_note}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ---------------- Adjust mode ---------------- */
function AdjustMode({ hasPlan }: { hasPlan: boolean }) {
  const { mutate: mutateGlobal } = useSWRConfig();
  const { data, mutate } = useSWR<ReconResponse>(
    hasPlan ? "/api/planning/reconciliation?weeks=1" : null,
    fetcher,
  );
  const [rows, setRows] = useState<ReconRow[] | null>(null);
  const [result, setResult] = useState<AdjustResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const current = rows ?? data?.rows ?? null;

  function setOutcome(i: number, outcome: Outcome) {
    if (!current) return;
    const next = current.map((r) =>
      r.index === i
        ? { ...r, outcome, actual_total_tss: outcome === "as_planned" ? r.planned_total_tss : outcome === "skipped" || outcome === "unavailable" ? 0 : Math.round(r.planned_total_tss * 0.6) }
        : r,
    );
    setRows(next);
  }

  async function submit() {
    if (!current) return;
    setBusy(true);
    setError(null);
    try {
      const r = await postJSON<AdjustResult>("/api/planning/adjust", {
        rows: current,
        weeks: 1,
      });
      setResult(r);
      mutate();
      mutateGlobal("/api/planning/history?limit=8");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Не удалось пересобрать план");
    } finally {
      setBusy(false);
    }
  }

  if (!hasPlan) return <EmptyPlan />;
  if (!data) return <Skeleton />;

  return (
    <>
      <section className="overflow-hidden rounded-card border border-surface-border bg-surface shadow-card">
        <div className="border-b border-surface-border p-4 text-sm text-ink-soft">
          Отметьте, как прошли тренировки за неделю — план пересоберётся с учётом факта.
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-border text-left text-xs uppercase tracking-wide text-ink-faint">
              <th className="px-3 py-2.5 font-medium">Дата</th>
              <th className="px-3 py-2.5 font-medium">Сессия</th>
              <th className="px-3 py-2.5 text-right font-medium">План TSS</th>
              <th className="px-3 py-2.5 font-medium">Итог</th>
            </tr>
          </thead>
          <tbody>
            {(current ?? []).map((r) => (
              <tr key={r.index} className="border-b border-surface-border last:border-0">
                <td className="px-3 py-2.5 text-ink-soft">{r.date.slice(5)}</td>
                <td className="px-3 py-2.5 text-ink">
                  {r.sport_label}
                  {r.session_role_label ? ` · ${r.session_role_label}` : ""}
                </td>
                <td className="px-3 py-2.5 text-right tabular-nums text-ink">
                  {r.planned_total_tss}
                </td>
                <td className="px-3 py-2.5">
                  <select
                    value={r.outcome}
                    onChange={(e) => setOutcome(r.index, e.target.value as Outcome)}
                    className="rounded-lg border border-surface-border bg-surface px-2 py-1 text-xs"
                  >
                    {OUTCOMES.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="p-4">
          <button
            type="button"
            onClick={submit}
            disabled={busy}
            className="rounded-lg bg-accent px-6 py-2.5 text-sm font-medium text-accent-foreground transition hover:bg-accent/90 disabled:opacity-40"
          >
            {busy ? "Пересобираю…" : "♻️ Пересобрать план"}
          </button>
          {error ? (
            <div className="mt-3 rounded-lg bg-tone-danger/10 px-3 py-2 text-sm text-tone-danger">
              {error}
            </div>
          ) : null}
        </div>
      </section>

      {result ? (
        <>
          <section className="rounded-card border border-surface-border bg-surface p-4 shadow-card">
            <div className="text-sm text-ink">
              {result.adjustment.label} · выполнение{" "}
              {Math.round(result.adjustment.completion_share * 100)}% · пропущено{" "}
              {result.adjustment.missed_sessions}
            </div>
          </section>
          <ForecastSection forecast={result.forecast} />
          <WeeksTable weeks={result.weeks} />
        </>
      ) : null}
    </>
  );
}

/* ---------------- Export mode ---------------- */
function ExportMode() {
  const { data } = useSWR<PlanExport>("/api/planning/plan", fetcher);

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

      <section className="overflow-hidden rounded-card border border-surface-border bg-surface shadow-card">
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
              <tr key={d.index} className="border-b border-surface-border last:border-0">
                <td className="px-3 py-2.5 text-ink-soft">{d.date.slice(5)}</td>
                <td className="px-3 py-2.5 text-ink">
                  <span className="font-medium">{d.sport_label}</span>{" "}
                  <span className="text-ink-faint">· {d.name}</span>
                </td>
                <td className="px-3 py-2.5 text-right tabular-nums text-ink">{d.tss}</td>
                <td className="px-3 py-2.5 text-right">
                  <span className="inline-flex gap-2">
                    <DownloadLink index={d.index} fmt="tcx" label="TCX" />
                    <DownloadLink index={d.index} fmt="fit_csv" label="FIT-CSV" />
                  </span>
                </td>
              </tr>
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
}: {
  index: number;
  fmt: string;
  label: string;
}) {
  return (
    <a
      href={withDemo(`/api/planning/export/workout/${index}?fmt=${fmt}`)}
      className="rounded-md border border-surface-border px-2 py-1 text-xs text-tone-neutral transition hover:bg-surface-muted"
    >
      {label}
    </a>
  );
}

/* ---------------- Shared ---------------- */
function ForecastSection({
  forecast,
}: {
  forecast: { points: ForecastPoint[]; message: string };
}) {
  return (
    <section className="rounded-card border border-surface-border bg-surface p-5 shadow-card">
      <div className="mb-3 flex items-baseline justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-ink-faint">
          Прогноз CTL / ATL / TSB к старту
        </span>
        <span className="text-xs text-ink-soft">{forecast.message}</span>
      </div>
      <ForecastChart points={forecast.points} />
      <Legend />
    </section>
  );
}

function WeeksTable({ weeks }: { weeks: PlanWeek[] }) {
  return (
    <section className="overflow-hidden rounded-card border border-surface-border bg-surface shadow-card">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-surface-border text-left text-xs uppercase tracking-wide text-ink-faint">
            <th className="px-3 py-2.5 font-medium">Нед.</th>
            <th className="px-3 py-2.5 font-medium">Фаза</th>
            <th className="px-3 py-2.5 text-right font-medium">TSS</th>
            <th className="hidden px-3 py-2.5 text-right font-medium sm:table-cell">Вело</th>
            <th className="hidden px-3 py-2.5 text-right font-medium sm:table-cell">Бег</th>
            <th className="hidden px-3 py-2.5 text-right font-medium sm:table-cell">Плав</th>
            <th className="px-3 py-2.5 font-medium">Заметка</th>
          </tr>
        </thead>
        <tbody>
          {weeks.map((w) => (
            <tr key={w.index} className="border-b border-surface-border last:border-0">
              <td className="px-3 py-2.5 text-ink-soft">{w.week_start.slice(5)}</td>
              <td className="px-3 py-2.5 text-ink">{w.phase}</td>
              <td className="px-3 py-2.5 text-right font-medium tabular-nums text-ink">
                {w.weekly_tss}
              </td>
              <td className="hidden px-3 py-2.5 text-right tabular-nums text-ink-soft sm:table-cell">
                {w.bike || "—"}
              </td>
              <td className="hidden px-3 py-2.5 text-right tabular-nums text-ink-soft sm:table-cell">
                {w.run || "—"}
              </td>
              <td className="hidden px-3 py-2.5 text-right tabular-nums text-ink-soft sm:table-cell">
                {w.swim || "—"}
              </td>
              <td className="px-3 py-2.5 text-xs text-ink-faint">{w.adjustment_note}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function ForecastChart({ points }: { points: ForecastPoint[] }) {
  const w = 680;
  const h = 200;
  const pad = 24;
  const { paths, zeroY } = useMemo(() => {
    if (points.length < 2) return { paths: null, zeroY: 0 };
    const s = {
      ctl: points.map((p) => p.ctl),
      atl: points.map((p) => p.atl),
      tsb: points.map((p) => p.tsb),
    };
    const all = [...s.ctl, ...s.atl, ...s.tsb, 0];
    const min = Math.min(...all);
    const max = Math.max(...all);
    const span = max - min || 1;
    const x = (i: number) => pad + (i * (w - 2 * pad)) / (points.length - 1);
    const y = (v: number) => h - pad - ((v - min) / span) * (h - 2 * pad);
    const toPath = (vals: number[]) =>
      vals.map((v, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(v)}`).join(" ");
    return {
      paths: { ctl: toPath(s.ctl), atl: toPath(s.atl), tsb: toPath(s.tsb) },
      zeroY: y(0),
    };
  }, [points]);

  if (!paths) return <div className="text-sm text-ink-faint">Недостаточно точек.</div>;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full">
      <line x1={pad} x2={w - pad} y1={zeroY} y2={zeroY} stroke="#E2E8F0" strokeWidth={1} />
      <path d={paths.ctl} fill="none" stroke="#3B82F6" strokeWidth={2} />
      <path d={paths.atl} fill="none" stroke="#F59E0B" strokeWidth={2} />
      <path d={paths.tsb} fill="none" stroke="#10B981" strokeWidth={2} />
    </svg>
  );
}

function Legend() {
  const items = [
    { c: "#3B82F6", l: "CTL (форма)" },
    { c: "#F59E0B", l: "ATL (усталость)" },
    { c: "#10B981", l: "TSB (свежесть)" },
  ];
  return (
    <div className="mt-2 flex flex-wrap gap-4 text-xs text-ink-soft">
      {items.map((i) => (
        <span key={i.l} className="flex items-center gap-1.5">
          <span className="h-2 w-3 rounded" style={{ background: i.c }} />
          {i.l}
        </span>
      ))}
    </div>
  );
}

function Select({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm"
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-card border border-surface-border bg-surface p-4 shadow-card">
      <div className="text-xs font-medium uppercase tracking-wide text-ink-faint">
        {label}
      </div>
      <div className="mt-1 text-xl font-bold text-ink">{value}</div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-ink-soft">{label}</span>
      {children}
    </label>
  );
}

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
