"use client";

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { ApiError, fetcher, postJSON, putJSON, withDemo } from "@/lib/api";
import { AdherenceRibbon } from "@/components/AdherenceRibbon";
import {
  BuiltPlan,
  ForecastPoint,
  IntervalsDeliveryResult,
  PlanningEventsResponse,
  PlanningDemand,
  PlanningHistory,
  PlanningOnboarding,
  PlanningOverview,
  PlanningProfile,
  PlanExport,
  PlanningStatus,
  PlanWeek,
  RebalanceConfirmResult,
  RebalancePreviewResult,
  ReconResponse,
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

const READER_TABS = ["overview", "weeks", "execution"] as const;
type ReaderTab = (typeof READER_TABS)[number];
type Tab = ReaderTab | "build" | "adjust" | "export";
const READER_TAB_LABELS: Record<ReaderTab, string> = {
  overview: "Обзор",
  weeks: "Недели",
  execution: "Выполнение",
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

      {!hasPlan || tab === "build" ? <BuildMode status={status} /> : null}
      {hasPlan && tab === "overview" ? <ActivePlanOverview overview={overview} error={overviewError} /> : null}
      {hasPlan && tab === "weeks" ? <PlanWeeks overview={overview} error={overviewError} /> : null}
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

function PlanWeeks({ overview, error }: { overview?: PlanningOverview; error?: Error }) {
  if (error) return <LocalDataGap label="Недели плана сейчас недоступны. Попробуйте открыть их позже." />;
  if (!overview || !overview.has_plan) return <Skeleton />;
  if (!overview.weeks?.length) {
    return <LocalDataGap label="Недели плана пока недоступны в сохранённом checkpoint." />;
  }
  return (
    <section className="overflow-x-auto rounded-card border border-surface-border bg-surface shadow-card">
      <table className="w-full min-w-[520px] text-sm">
        <thead>
          <tr className="border-b border-surface-border text-left text-xs uppercase tracking-wide text-ink-faint">
            <th className="px-3 py-2.5 font-medium">Неделя</th>
            <th className="px-3 py-2.5 font-medium">Старт</th>
            <th className="px-3 py-2.5 font-medium">Фаза</th>
            <th className="px-3 py-2.5 text-right font-medium">TSS</th>
          </tr>
        </thead>
        <tbody>
          {overview.weeks.map((week) => (
            <tr key={week.number} className="border-b border-surface-border last:border-0">
              <td className="px-3 py-2.5 text-ink">{week.number}</td>
              <td className="px-3 py-2.5 text-ink-soft">{week.week_start ?? "—"}</td>
              <td className="px-3 py-2.5 text-ink">{week.phase ?? "Недостаточно данных"}</td>
              <td className="px-3 py-2.5 text-right tabular-nums text-ink">{week.weekly_tss}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
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
  const demandOptions = status?.demand_options?.length ? status.demand_options : DEFAULT_DEMAND_OPTIONS;

  // M2 (#271): входы планирования приходят с сервера — сохранённый профиль, а до
  // онбординга предложение, выведенное из истории атлета. Хардкод 10ч/7 дней
  // остаётся только как значение до загрузки.
  const { data: onboarding } = useSWR<PlanningOnboarding>("/api/onboarding/planning", fetcher, {
    revalidateOnFocus: false,
  });
  const hydrated = useRef(false);

  useEffect(() => {
    if (!onboarding || hydrated.current) return;
    hydrated.current = true; // гидратация ровно один раз — правки атлета важнее ревалидации
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
  }, [onboarding]);

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
    if (
      !isAlreadySelected &&
      event.priority?.toUpperCase() === "A" &&
      event.confirmed !== false
    ) {
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

  return (
    <>
      {onboarding && !onboarding.completed ? (
        <FirstPlanCard onboarding={onboarding} hours={hours} days={days} />
      ) : null}
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
          disabled={building || days.length === 0 || needsEventDate}
          className="mt-5 w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-accent-foreground transition hover:bg-accent/90 disabled:opacity-40 sm:w-auto sm:px-8"
        >
          {building ? "Собираю план…" : "🧭 Предпросмотр плана"}
        </button>

        {needsEventDate ? (
          <p className="mt-3 text-xs text-ink-faint">
            Для режима «К старту» нужна дата A-гонки — выберите событие из Intervals.icu или
            укажите дату. Без гонки выберите «Развивать форму»: план будет построен на горизонт,
            без тейпера под несуществующий старт.
          </p>
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
  const [expanded, setExpanded] = useState(false);
  if (!data || !data.has_history) return null;

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
  const reasonLabels: Record<string, string> = {
    data_gap: "Пока недостаточно надёжных сопоставлений — план не меняется.",
    no_change_under_plan: "Недовыполнение принято как факт: догонять объём автоматически не будем.",
    no_change_below_threshold: "Отклонение меньше 10 TSS — пересборка не нужна.",
    no_eligible_future_sessions: "Нет будущих лёгких сессий, которые можно безопасно уменьшить.",
  };
  const preview = previewResult?.preview;

  return (
    <>
      <section className="overflow-hidden rounded-card border border-surface-border bg-surface shadow-card">
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
                    {r.match_method} · {adherenceLabels[r.adherence] ?? r.adherence} · {Math.round(r.confidence * 100)}%
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
