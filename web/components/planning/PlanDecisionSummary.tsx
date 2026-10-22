"use client";

import type { BuildPreviewResponse, PlanScienceAudit, BuildReadiness } from "@/lib/types";
import { DAYS, DISTANCES, GOAL_TYPES, phaseLabel } from "./planningLabels";

const UNKNOWN = "Данные не переданы";
// Formatting and vocabulary only: no target, comparison or eligibility calculation.
export function shownNumber(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value) ? String(value) : UNKNOWN;
}
const tss = (value: unknown) => typeof value === "number" && Number.isFinite(value) ? `${shownNumber(value)} TSS` : UNKNOWN;
const modes: Record<string, string> = { event_goal: "К старту", training_goal: "Без привязки к старту", manual: "Ручные фазы" };
const intents: Record<string, string> = { develop: "Развивать форму", maintain: "Поддерживать форму" };
const constraintKinds: Record<string, string> = { sick: "Ограничение по состоянию", unavailable: "Недоступный день", forced_rest: "Отдых", manual_delete: "Назначение удалено вручную", disabled_plan_day: "День исключён из плана" };

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="min-w-0"><dt className="text-sm text-ink-soft">{label}</dt><dd className="mt-1 break-words font-medium text-ink">{children}</dd></div>;
}

export function PlanDecisionSummary({ plan, awaitingResult }: { plan: BuildPreviewResponse; awaitingResult: boolean }) {
  const params = plan.parameters;
  const lifecycle = "lifecycle" in plan ? plan.lifecycle : undefined;
  const action = lifecycle?.action === "start_new" ? "Новый цикл" : lifecycle?.action === "edit_current" ? "Изменение выбранного цикла" : "Действие не указано";
  const goal = GOAL_TYPES.find(item => item.value === params?.goal_type)?.label ?? "Вид подготовки не указан";
  const distance = DISTANCES[params?.goal_type]?.find(item => item.value === params?.distance)?.label ?? "Дистанция не указана";
  const events = plan.goal?.events;
  const application = plan.constraint_application;
  return <section aria-label="Резюме плана" className="rounded-card border border-accent/30 bg-surface p-5 shadow-card">
    <p className="text-sm font-medium text-ink">{action}</p>
    <h2 className="mt-1 text-lg font-semibold text-ink">{plan.plan_id ? "Сведения о сохранённом варианте" : awaitingResult ? "Сведения о предложении" : "Проверьте план перед сохранением"}</h2>
    <dl className="mt-5 grid gap-4 sm:grid-cols-2">
      <Fact label="Подготовка">{goal} · {distance}</Fact>
      <Fact label="Период назначений">{lifecycle?.start_date && lifecycle?.end_date ? `${lifecycle.start_date} — ${lifecycle.end_date} включительно` : "Период этого варианта не указан"}</Fact>
      <Fact label="Подход">{modes[params?.planning_mode] ?? "Подход не указан"}</Fact>
      <Fact label="Намерение">{intents[params?.intent] ?? "Намерение не указано"}</Fact>
      <Fact label="Потолок доступности">{typeof params?.available_hours === "number" && Number.isFinite(params.available_hours) ? `${params.available_hours} ч в неделю` : UNKNOWN}
        <span className="mt-1 block text-sm font-normal text-ink-soft">{Array.isArray(params?.available_days) && params.available_days.length ? params.available_days.map(day => DAYS.find(item => item.value === day)?.label ?? "День не указан").join(" · ") : "Дни не указаны"}</span>
      </Fact>
      <Fact label="Применённые старты">{Array.isArray(events) ? events.length ? <ul className="space-y-1">{events.map((event, index) => <li key={index}>{event.priority} · {event.date || "Дата не указана"} · {event.label || "Без названия"}</li>)}</ul> : "Старты не включены в предложение" : "Сведения о стартах не переданы"}</Fact>
    </dl>
    {params?.planning_mode === "manual" ? <p className="mt-4 text-sm text-ink-soft">Ручные фазы: {Array.isArray(params.manual_phases) && params.manual_phases.length ? params.manual_phases.map(phaseLabel).join(" → ") : UNKNOWN}.</p> : null}
    <div className="mt-5 border-t border-surface-border pt-4">
      <h3 className="font-semibold text-ink">Назначенная нагрузка</h3>
      <p className="mt-1 text-sm text-ink-soft">За период назначений выше. TSS — условная мера тренировочной нагрузки, не время занятий.</p>
      <dl className="mt-3 grid gap-4 sm:grid-cols-3">
        <Fact label="Всего за период"><span className="text-xl tabular-nums">{tss(plan.totals?.total_tss)}</span></Fact>
        <Fact label="Максимальная неделя"><span className="text-xl tabular-nums">{tss(plan.totals?.peak_tss)}</span></Fact>
        <Fact label="Ориентир на неделю">{tss(plan.weekly_target?.target_weekly_tss)}</Fact>
      </dl>
      <p className="mt-3 text-sm text-ink-soft">Ориентир и доступное время не означают, что каждой неделе назначен такой объём. Назначенные часы и число занятий за весь период здесь не переданы.</p>
    </div>
    {lifecycle?.action === "edit_current" ? <p className="mt-4 text-sm text-ink-soft">Сопоставимое сравнение с прежним планом недоступно: в предложении нет дат его периода. Здесь показаны назначения этого варианта.</p> : null}
    <details className="mt-4 text-sm text-ink-soft">
      <summary className="cursor-pointer py-2 font-medium text-ink">Ограничения из расчёта</summary>
      {application ? <>
        <p className="mt-2">Ниже — сведения, переданные в этом предложении. Полнота списка и влияние каждого ограничения могут быть не указаны. Начальные ограничения дисциплин показаны отдельно.</p>
        {application.constraints?.length ? <ul className="mt-2 space-y-2">{application.constraints.map((item, index) => <li key={index}>{item.date || "Дата не указана"} · {constraintKinds[item.kind ?? ""] ?? "Вид ограничения не указан"}{item.source ? <span className="block">Источник в данных расчёта: {item.source}</span> : <span className="block">Источник не указан.</span>}</li>)}</ul> : <p className="mt-2">Список применённых ограничений не передан.</p>}
        {application.protected_dates?.length ? <p className="mt-2">Защищённые даты: {application.protected_dates.join(" · ")}.</p> : null}
      </> : <p className="mt-2">Сведения о дополнительных ограничениях не переданы.</p>}
    </details>
    {!plan.plan_id && !awaitingResult ? <p role="note" className="mt-4 rounded-lg bg-accent/10 p-3 text-sm text-ink">{lifecycle?.closes_cycle_id ? "При подтверждении прежний цикл закроется. История сохранится; участие в старте не будет определено автоматически." : lifecycle?.action === "edit_current" ? "При подтверждении сохранится новая версия выбранного цикла. История и записи выполнения сохранятся." : lifecycle?.action === "start_new" ? "При подтверждении будет создан новый цикл с этими назначениями." : "Последствие сохранения не описано в этом старом предложении."}</p> : null}
  </section>;
}

export function PlanRuleAudit({ audit }: { audit?: PlanScienceAudit | null }) {
  return <details className="rounded-card border border-surface-border bg-surface p-5 text-sm text-ink-soft">
    <summary className="cursor-pointer font-medium text-ink">Проверки правил плана</summary>
    <p className="mt-3">Проверки объясняют соответствие правилам составления плана. Они не подтверждают личную безопасность или достижение цели.</p>
    {audit?.state === "available" && audit.summary ? <>
      <p className="mt-2">Пройдено: {audit.summary.passed} · Требует внимания: {audit.summary.attention} · Недостаточно данных: {audit.summary.data_gap}.</p>
      <ul className="mt-3 space-y-3">{audit.findings?.map((finding, index) => <li key={index}><span className="font-medium text-ink">{finding.title}</span><p>{finding.summary}</p>{finding.recommendation ? <p>{finding.recommendation}</p> : null}{finding.affected_dates?.length ? <p>Даты: {finding.affected_dates.join(" · ")}</p> : null}</li>)}</ul>
    </> : <p className="mt-2">Проверка правил этого варианта недоступна.</p>}
  </details>;
}


export function PlanBuildRefusal({ assessment }: { assessment: BuildReadiness }) {
  const reasons: Record<string, string> = {
    prescription_missing: "Для этого дня не подготовлено полное задание.",
    prescription_infeasible: "Задание не соответствует условиям плана.",
    target_semantics_unverified: "Не удалось проверить цели тренировки.",
    load_inconsistent: "Нагрузка назначения не согласована с планом.",
    duration_inconsistent: "Длительность назначения не согласована с планом.",
    availability_exceeded: "Назначение превышает указанную доступность.",
  };
  return <>
    <h3 className="font-semibold">План не готов к сохранению</h3>
    <p className="mt-2">Сервер обнаружил неполные или несогласованные назначения. Предложение для подтверждения не создано.</p>
    <ul className="mt-2 space-y-2">{assessment.blockers?.map((reason, index) => <li key={index}>{reason.date ? `${reason.date}: ` : ""}{reasons[reason.code] ?? "Причина не уточнена в этом ответе."}</li>)}</ul>
    <p className="mt-2">Подготовьте новый предпросмотр. Если отказ повторяется, требуется проверка расчёта плана.</p>
  </>;
}
