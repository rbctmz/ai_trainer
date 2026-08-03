"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { ApiError, fetcher, postJSON, putJSON } from "@/lib/api";
import {
  BuiltPlan,
  ForecastPoint,
  PlanningDemand,
  PlanningEditContext,
  PlanningEventsResponse,
  PlanningOnboarding,
  PlanningProfile,
  PlanningStatus,
  PlanWeek,
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

export const DEFAULT_DEMAND_OPTIONS: PlanningDemand[] = [
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

const STEP_LABELS = ["Подход и цель", "Доступность", "Нагрузка и preview", "Подтверждение"];

const MICRO_ROLE_LABELS: Record<string, string> = {
  off: "отдых",
  race: "старт",
  recovery: "восстановление",
  easy: "легко",
  activation: "активация",
  quality: "качество",
  long: "длительная",
};

const MICRO_SPORT_LABELS: Record<string, string> = {
  off: "—",
  bike: "вело",
  run: "бег",
  swim: "плавание",
  brick: "вело → бег",
};

function microcycleStateLabel(state: { role: string; sport: string; tss: number }): string {
  const role = MICRO_ROLE_LABELS[state.role] ?? state.role;
  const sport = MICRO_SPORT_LABELS[state.sport] ?? state.sport;
  return `${role} · ${sport} · ${Number(state.tss).toFixed(1)} TSS`;
}

/**
 * Four-step plan builder/editor (M4c, #337).
 *
 * Serves both the first-plan path (hydrates once from onboarding suggestions)
 * and the "Изменить план" path (hydrates once from the active checkpoint via
 * /api/planning/edit-context). Preview is explicit on step 3; confirmation is
 * an explicit action on step 4 and writes through the existing /build flow.
 */
export function PlanBuilder({
  status,
  onSaved,
}: {
  status?: PlanningStatus;
  onSaved?: () => void;
}) {
  const { mutate } = useSWRConfig();
  const [step, setStep] = useState(1);
  const [planningMode, setPlanningMode] = useState<PlanningMode>("event_goal");
  const [intent, setIntent] = useState<"maintain" | "develop">("develop");
  const [horizonWeeks, setHorizonWeeks] = useState(8);
  const [manualPhases, setManualPhases] = useState(
    "Base, Base, Build, Recovery, Base, Build, Build, Recovery",
  );
  const [goalType, setGoalType] = useState("triathlon");
  const [distance, setDistance] = useState("olympic");
  // Дата A-старта пустая до явного выбора: подставленная «сегодня + 8 недель»
  // молча строила план с тейпером под несуществующее событие (#271 §5).
  const [eventDate, setEventDate] = useState("");
  const [hours, setHours] = useState(10);
  const [days, setDays] = useState<string[]>(DAYS.map((d) => d.value));
  const [demand, setDemand] = useState("moderate");
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [profileWarning, setProfileWarning] = useState<string | null>(null);
  const [plan, setPlan] = useState<BuiltPlan | null>(null);
  const [selectedEvents, setSelectedEvents] = useState<RaceEvent[]>([]);
  const [lastRequest, setLastRequest] = useState<Record<string, unknown> | null>(null);
  // Сохранённая неделя старта активного плана: при редактировании пересборка
  // идёт с того же календаря, а не «с сегодня» (#337, фикс после ручной приёмки).
  const [startWeek, setStartWeek] = useState<string | null>(null);
  const demandOptions = status?.demand_options?.length ? status.demand_options : DEFAULT_DEMAND_OPTIONS;
  const hydrated = useRef(false);
  const stepHeadingRef = useRef<HTMLHeadingElement | null>(null);

  const { data: onboarding } = useSWR<PlanningOnboarding>("/api/onboarding/planning", fetcher, {
    revalidateOnFocus: false,
  });
  const { data: editContext } = useSWR<PlanningEditContext>(
    status?.has_plan ? "/api/planning/edit-context" : null,
    fetcher,
    { revalidateOnFocus: false },
  );

  // Hydrate exactly once: editing an active plan starts from the checkpoint's
  // saved inputs; a first plan starts from the onboarding suggestion/profile.
  // Later SWR revalidation must never clobber athlete edits (#304).
  useEffect(() => {
    if (hydrated.current) return;
    if (status?.has_plan) {
      if (!editContext || editContext.state !== "available" || !editContext.inputs) return;
      hydrated.current = true;
      const source = editContext.inputs;
      setPlanningMode(source.planning_mode as PlanningMode);
      setIntent(source.intent as "maintain" | "develop");
      setGoalType(source.goal_type);
      setDistance(source.distance);
      setEventDate(source.event_date ?? "");
      setHorizonWeeks(source.horizon_weeks);
      if (source.planning_mode === "manual" && source.manual_phases.length) {
        setManualPhases(source.manual_phases.join(", "));
      }
      setHours(source.available_hours);
      if (source.available_days.length) setDays(source.available_days);
      setDemand(source.demand);
      if (source.events?.length) setSelectedEvents(source.events);
      setStartWeek(source.start_week);
      return;
    }
    if (!onboarding) return;
    hydrated.current = true;
    const source: Partial<PlanningProfile> = onboarding.profile ?? {
      planning_mode: onboarding.suggested.planning_mode.value,
      intent: onboarding.suggested.intent.value,
      goal_type: onboarding.suggested.goal_type.value,
      distance: onboarding.suggested.distance.value,
      available_hours: onboarding.suggested.available_hours.value,
      available_days: onboarding.suggested.available_days.value,
      horizon_weeks: onboarding.suggested.horizon_weeks.value,
    };
    if (source.planning_mode) setPlanningMode(source.planning_mode);
    if (source.intent) setIntent(source.intent);
    if (source.goal_type) setGoalType(source.goal_type);
    if (source.distance) setDistance(source.distance);
    if (source.available_hours) setHours(source.available_hours);
    if (source.available_days?.length) setDays(source.available_days);
    if (source.horizon_weeks) setHorizonWeeks(source.horizon_weeks);
  }, [onboarding, editContext, status?.has_plan]);

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

  function invalidatePlan() {
    setPlan(null);
    setLastRequest(null);
  }
  function onGoalChange(v: string) {
    setGoalType(v);
    setDistance(DISTANCES[v][v === "run" ? 2 : 1].value);
    invalidatePlan();
  }
  function toggleDay(v: string) {
    setDays((d) => (d.includes(v) ? d.filter((x) => x !== v) : [...d, v]));
    invalidatePlan();
  }
  function toggleEvent(event: RaceEvent) {
    const key = `${event.source ?? "event"}:${event.source_id ?? event.date}:${event.priority}`;
    const isAlreadySelected = selectedEvents.some(
      (item) => `${item.source ?? "event"}:${item.source_id ?? item.date}:${item.priority}` === key,
    );
    if (
      !isAlreadySelected &&
      event.priority?.toUpperCase() === "A" &&
      event.confirmed !== false
    ) {
      setPlanningMode("event_goal");
    }
    invalidatePlan();
    setSelectedEvents((current) =>
      current.some((item) => `${item.source ?? "event"}:${item.source_id ?? item.date}:${item.priority}` === key)
        ? current.filter((item) => `${item.source ?? "event"}:${item.source_id ?? item.date}:${item.priority}` !== key)
        : [...current, event],
    );
  }
  const hasSelectedARace = selectedEvents.some(
    (event) => event.priority?.toUpperCase() === "A" && event.confirmed !== false,
  );
  function requestPayload(): Record<string, unknown> {
    const parsedManual = manualPhases.split(",").map((value) => value.trim()).filter(Boolean);
    return {
      goal_type: goalType,
      distance,
      event_date: planningMode === "event_goal" && !hasSelectedARace ? eventDate : null,
      events: selectedEvents,
      planning_mode: planningMode,
      intent,
      focus: "balanced_triathlon",
      horizon_weeks: planningMode === "event_goal" ? 8 : horizonWeeks,
      manual_phases: planningMode === "manual" ? parsedManual : null,
      available_hours: hours,
      available_days: days,
      demand,
      start_week: startWeek,
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
    setProfileWarning(null);
    try {
      const confirmed = await postJSON<BuiltPlan>("/api/planning/build", {
        ...lastRequest,
        persist: true,
        confirm: true,
        base_checkpoint_id: plan?.preview.base_checkpoint_id ?? 0,
      });
      setPlan(confirmed);
      // Параметры, которыми план собран, становятся сохранённым профилем: следующий
      // вход начинается с них, а не с констант (#271 §3). Неудача записи профиля не
      // отменяет уже сохранённый план — это разные решения.
      try {
        await putJSON("/api/onboarding/planning", {
          planning_mode: planningMode,
          intent,
          goal_type: goalType,
          distance,
          available_hours: hours,
          available_days: days,
          horizon_weeks: planningMode === "event_goal" ? 8 : horizonWeeks,
          source: "planning_form",
        });
      } catch {
        setProfileWarning(
          "План сохранён, но параметры профиля записать не удалось. Сам план не потерян.",
        );
      }
      await Promise.all([
        mutate("/api/planning/status"),
        mutate("/api/planning/history?limit=8"),
        mutate("/api/onboarding/planning"),
      ]);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Не удалось подтвердить план");
    } finally {
      setBuilding(false);
    }
  }

  const needsEventDate = planningMode === "event_goal" && !eventDate && !hasSelectedARace;
  const canProceedFromStep =
    (step === 1 && !needsEventDate) ||
    (step === 2 && days.length > 0) ||
    (step === 3 && plan !== null) ||
    step === 4;

  function goToStep(next: number) {
    setStep(next);
    requestAnimationFrame(() => stepHeadingRef.current?.focus());
  }
  function resetBuilder() {
    setPlan(null);
    setLastRequest(null);
    setError(null);
    setProfileWarning(null);
    goToStep(1);
  }

  return (
    <>
      {onboarding && !onboarding.completed ? (
        <FirstPlanCard onboarding={onboarding} hours={hours} days={days} />
      ) : null}
      <section className="rounded-card border border-surface-border bg-surface p-5 shadow-card">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2
            ref={stepHeadingRef}
            tabIndex={-1}
            className="text-sm font-semibold text-ink outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            Настройка плана — шаг {step}: {STEP_LABELS[step - 1]}
          </h2>
          <span className="text-xs text-ink-faint">Изменения применяются только после подтверждения</span>
        </div>

        <nav aria-label="Шаги настройки плана" className="mt-4">
          <ol className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
            {STEP_LABELS.map((label, index) => {
              const n = index + 1;
              const isCurrent = n === step;
              const isReached = n < step;
              return (
                <li key={label}>
                  <button
                    type="button"
                    onClick={() => isReached && goToStep(n)}
                    aria-current={isCurrent ? "step" : undefined}
                    disabled={!isReached && !isCurrent}
                    className={`w-full rounded-lg border px-2 py-2 text-left text-xs font-medium transition disabled:opacity-50 ${
                      isCurrent
                        ? "border-accent bg-accent/10 text-ink"
                        : isReached
                          ? "border-surface-border text-ink-soft hover:bg-surface-muted"
                          : "border-surface-border text-ink-faint"
                    }`}
                  >
                    <span className="block text-[10px] uppercase tracking-wide">{n}</span>
                    {label}
                  </button>
                </li>
              );
            })}
          </ol>
        </nav>

        {step === 1 ? (
          <>
            <Field label="Подход к планированию">
              <div className="mb-4 grid gap-2 sm:grid-cols-3">
                {PLANNING_MODES.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => {
                      setPlanningMode(option.value);
                      invalidatePlan();
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
                    onChange={(e) => {
                      setEventDate(e.target.value);
                      invalidatePlan();
                    }}
                    className="w-full rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm"
                  />
                </Field>
              ) : (
                <Field label="Горизонт">
                  <Select
                    value={String(horizonWeeks)}
                    onChange={(value) => {
                      setHorizonWeeks(Number(value));
                      invalidatePlan();
                    }}
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
                    onChange={(value) => {
                      setIntent(value as "maintain" | "develop");
                      invalidatePlan();
                    }}
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
                      onChange={(event) => {
                        setManualPhases(event.target.value);
                        invalidatePlan();
                      }}
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

            {needsEventDate ? (
              <p className="mt-3 text-xs text-ink-faint">
                Для режима «К старту» нужна дата A-гонки — выберите событие из Intervals.icu или
                укажите дату. Без гонки выберите «Развивать форму»: план будет построен на горизонт,
                без тейпера под несуществующий старт.
              </p>
            ) : null}
          </>
        ) : null}

        {step === 2 ? (
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <Field label={`Часов в неделю: ${hours}`}>
              <input
                type="range"
                min={3}
                max={20}
                step={0.5}
                value={hours}
                onChange={(e) => {
                  setHours(Number(e.target.value));
                  invalidatePlan();
                }}
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
        ) : null}

        {step === 3 ? (
          <>
            <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_1.4fr]">
              <Field label="Режим нагрузки">
                <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4 lg:grid-cols-2">
                  {demandOptions.map((option) => (
                    <button
                      key={option.level}
                      type="button"
                      onClick={() => {
                        setDemand(option.level);
                        invalidatePlan();
                      }}
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
              disabled={building || days.length === 0 || needsEventDate}
              className="mt-5 w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-accent-foreground transition hover:bg-accent/90 disabled:opacity-40 sm:w-auto sm:px-8"
            >
              {building ? "Собираю план…" : "🧭 Предпросмотр плана"}
            </button>

            {plan && !plan.plan_id ? (
              <div className="mt-3 rounded-lg border border-surface-border bg-surface-muted/40 px-3 py-2 text-sm text-ink">
                План собран: изменение нагрузки{" "}
                {plan.preview.weekly_tss_delta >= 0 ? "+" : ""}
                {plan.preview.weekly_tss_delta} TSS ·{" "}
                {plan.event_overlay.rule_version}. Переходите к подтверждению.
              </div>
            ) : null}
            {!plan ? (
              <p className="mt-3 text-xs text-ink-faint">
                Сначала соберите предпросмотр плана, затем переходите к подтверждению.
              </p>
            ) : null}
          </>
        ) : null}

        {error ? (
          <div className="mt-3 rounded-lg bg-tone-danger/10 px-3 py-2 text-sm text-tone-danger">
            {error}
          </div>
        ) : null}
        {profileWarning ? (
          <div className="mt-3 rounded-lg bg-tone-warning/10 px-3 py-2 text-sm text-tone-warning">
            {profileWarning}
          </div>
        ) : null}

        <div className="mt-5 flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={() => goToStep(step - 1)}
            disabled={step === 1 || building}
            className="rounded-lg border border-surface-border px-4 py-2 text-sm font-medium text-ink-soft transition hover:bg-surface-muted disabled:opacity-40"
          >
            Назад
          </button>
          {step < 4 ? (
            <button
              type="button"
              onClick={() => goToStep(step + 1)}
              disabled={!canProceedFromStep || building}
              className="rounded-lg bg-accent px-6 py-2 text-sm font-medium text-accent-foreground transition hover:bg-accent/90 disabled:opacity-40"
            >
              Далее
            </button>
          ) : null}
        </div>
      </section>

      {plan && step === 4 ? (
        <>
          <section className="rounded-card border border-surface-border bg-surface p-4 shadow-card">
            {plan.plan_id ? (
              <div className="text-sm text-tone-success">
                <div className="flex items-center gap-2 text-base font-semibold">
                  <span
                    aria-hidden="true"
                    className="flex h-6 w-6 items-center justify-center rounded-full bg-tone-success/15 text-tone-success"
                  >
                    ✓
                  </span>
                  План сохранён и стал активным
                </div>
                <p className="mt-1 text-xs">
                  Новая версия сохранена как checkpoint #{plan.plan_id}. Общая нагрузка
                  изменилась на {plan.preview.weekly_tss_delta >= 0 ? "+" : ""}
                  {plan.preview.weekly_tss_delta} TSS по {plan.weeks.length}{" "}
                  {plan.weeks.length === 1 ? "неделе" : "неделям"} плана.
                </p>
                <p className="mt-1 text-xs text-ink-soft">
                  Продолжить можно в «Обзоре» — там видны доступность, расчёт нагрузки и режим
                  нагрузки.
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={onSaved}
                    className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-foreground transition hover:bg-accent/90"
                  >
                    Открыть план в Обзоре
                  </button>
                  <button
                    type="button"
                    onClick={resetBuilder}
                    className="rounded-lg border border-surface-border px-4 py-2 text-sm text-ink-soft transition hover:bg-surface-muted"
                  >
                    Собрать заново
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-xs font-medium uppercase tracking-wide text-ink-faint">
                    Предпросмотр · SQLite не изменён
                  </div>
                  <div className="mt-1 text-sm text-ink-soft">
                    Изменение нагрузки: {plan.preview.weekly_tss_delta >= 0 ? "+" : ""}{plan.preview.weekly_tss_delta} TSS · {plan.event_overlay.rule_version}
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={resetBuilder}
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
              </div>
            )}
          </section>
          {plan.preview.microcycle_changes.length ? (
            <section className="rounded-card border border-surface-border bg-surface p-4 shadow-card">
              <div className="text-xs font-medium uppercase tracking-wide text-ink-faint">
                Подводка к стартам · до подтверждения
              </div>
              <div className="mt-3 divide-y divide-surface-border">
                {plan.preview.microcycle_changes.map((change) => (
                  <div key={`${change.date}-${change.event_date}-${change.priority}`} className="grid gap-1 py-2.5 sm:grid-cols-[100px_1fr]">
                    <div className="text-xs font-medium tabular-nums text-ink-soft">
                      {change.date.slice(5)} · {change.priority}{change.offset === 0 ? "" : ` ${change.offset > 0 ? "+" : ""}${change.offset}`}
                    </div>
                    <div>
                      <div className="text-sm text-ink">
                        {microcycleStateLabel(change.before)} → {microcycleStateLabel(change.after)}
                      </div>
                      <div className="mt-0.5 text-xs text-ink-soft">
                        {change.phase} · {change.after.focus} · {change.label || `Старт ${change.priority}`}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          ) : null}
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

function FirstPlanCard({
  onboarding,
  hours,
  days,
}: {
  onboarding: PlanningOnboarding;
  hours: number;
  days: string[];
}) {
  const { suggested, event_context: context } = onboarding;
  const dayLabels = days
    .map((day) => DAYS.find((item) => item.value === day)?.label ?? day)
    .join(", ");

  return (
    <section className="mb-4 rounded-card border border-accent/30 bg-accent/5 p-5">
      <h2 className="text-sm font-semibold text-ink">Соберём первый план</h2>
      <p className="mt-1 text-sm text-ink-soft">
        Плана ещё нет. Поля ниже заполнены предложением: то, что удалось посчитать по вашей
        истории, помечено «по вашим данным», остальное — значения по умолчанию, их стоит
        проверить.
      </p>

      <dl className="mt-4 grid gap-2 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-xs text-ink-faint">Часов в неделю</dt>
          <dd className="text-ink">
            {hours}
            <BasisChip basis={suggested.available_hours.basis} />
          </dd>
        </div>
        <div>
          <dt className="text-xs text-ink-faint">Дни тренировок</dt>
          <dd className="text-ink">
            {dayLabels}
            <BasisChip basis={suggested.available_days.basis} />
          </dd>
        </div>
        <div>
          <dt className="text-xs text-ink-faint">Подход</dt>
          <dd className="text-ink">
            {PLANNING_MODES.find((mode) => mode.value === suggested.planning_mode.value)?.label ??
              suggested.planning_mode.value}
            <BasisChip basis={suggested.planning_mode.basis} />
          </dd>
        </div>
      </dl>

      <p className="mt-4 text-xs text-ink-faint">
        {context.degraded_reason
          ? `События Intervals.icu недоступны (${context.degraded_reason}) — предложен режим «Развивать форму»; дату гонки можно указать вручную.`
          : context.has_a_race
            ? `Найдена подтверждённая A-гонка (${context.a_races[0]?.date}) — предложен режим «К старту».`
            : "Подтверждённых A-гонок в календаре нет — предложен режим «Развивать форму». Дата старта не подставляется."}
      </p>
      <p className="mt-2 text-xs text-ink-faint">
        Проверьте параметры, нажмите «Предпросмотр плана», затем «Подтвердить и сохранить» — план
        появится в «Сегодня», а параметры сохранятся для следующего раза.
      </p>
    </section>
  );
}

const BASIS_LABEL: Record<"derived" | "fallback", string> = {
  derived: "по вашим данным",
  fallback: "по умолчанию",
};

function BasisChip({ basis }: { basis: "derived" | "fallback" }) {
  return (
    <span
      className={`ml-2 rounded-full px-2 py-0.5 text-[10px] font-medium ${
        basis === "derived" ? "bg-accent/10 text-accent" : "bg-surface-muted text-ink-faint"
      }`}
    >
      {BASIS_LABEL[basis]}
    </span>
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
    <section className="overflow-x-auto rounded-card border border-surface-border bg-surface shadow-card">
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

export function Stat({ label, value }: { label: string; value: string }) {
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
