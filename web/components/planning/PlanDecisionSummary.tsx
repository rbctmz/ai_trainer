"use client";

import type { BuildPreviewResponse, PlanScienceAudit, BuildReadiness } from "@/lib/types";
import { DAYS, DISTANCES, GOAL_TYPES, phaseLabel } from "./planningLabels";

const UNKNOWN = "Нет данных";
// Formatting and vocabulary only: no target, comparison or eligibility calculation.
export function shownNumber(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value) ? String(value) : UNKNOWN;
}
const tss = (value: unknown) => typeof value === "number" && Number.isFinite(value) ? `${shownNumber(value)} TSS` : UNKNOWN;
const modes: Record<string, string> = { event_goal: "Подготовка к старту", training_goal: "Без привязки к старту", manual: "Фазы заданы вручную" };
const intents: Record<string, string> = { develop: "Развивать форму", maintain: "Поддерживать форму" };
const constraintKinds: Record<string, string> = { sick: "Ограничение по состоянию", unavailable: "Недоступный день", forced_rest: "Отдых", manual_delete: "Назначение удалено вручную", disabled_plan_day: "День исключён из плана" };
const dateFormat = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });

function PlanDate({ value }: { value: string }) {
  const date = new Date(`${value}T00:00:00Z`);
  // Display valid date-only values without timezone shifts or normalization.
  const valid = /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
  return valid ? <time dateTime={value}>{dateFormat.format(date)}</time> : <span>Дата не указана</span>;
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="min-w-0"><dt className="text-sm text-ink-soft">{label}</dt><dd className="mt-1 break-words font-medium text-ink">{children}</dd></div>;
}

export function PlanDecisionSummary({ plan, awaitingResult, children }: { plan: BuildPreviewResponse; awaitingResult: boolean; children?: React.ReactNode }) {
  const params = plan.parameters;
  const lifecycle = "lifecycle" in plan ? plan.lifecycle : undefined;
  const action = lifecycle?.action === "start_new" ? "Новый план подготовки" : lifecycle?.action === "edit_current" ? "Изменение плана" : "Действие не указано";
  const goal = GOAL_TYPES.find(item => item.value === params?.goal_type)?.label ?? "Вид подготовки не указан";
  const distance = DISTANCES[params?.goal_type]?.find(item => item.value === params?.distance)?.label ?? "Дистанция не указана";
  const events = plan.goal?.events;
  const application = plan.constraint_application;
  const hasHours = typeof params?.available_hours === "number" && Number.isFinite(params.available_hours);
  return <section aria-label="Резюме плана" className="rounded-card border border-accent/30 bg-surface p-5 shadow-card">
    <h2 className="text-xl font-semibold text-ink">{plan.plan_id ? "Сохранённый вариант плана" : awaitingResult ? "План, отправленный на сохранение" : action}</h2>
    <p className="mt-2 font-medium text-ink">{goal} · {distance}</p>
    <p className="mt-1 text-sm text-ink-soft">{intents[params?.intent] ?? "Цель не указана"}. {modes[params?.planning_mode] ?? "Подход не указан"}.</p>

    {!plan.plan_id && !awaitingResult ? <div className="mt-4 rounded-lg bg-accent/10 p-3 text-ink">
      <h3 className="text-sm font-semibold">После сохранения</h3>
      <p role="note" className="mt-1 text-sm">{lifecycle?.closes_cycle_id ? "Новый план заменит текущий; прежний цикл закроется. История сохранится. Участие в соревновании от этого не изменится." : lifecycle?.action === "edit_current" ? "Сохранится новая версия плана в том же цикле подготовки. История и записи выполнения останутся." : lifecycle?.action === "start_new" ? "Будет создан новый цикл подготовки с этим планом." : "Последствие сохранения этого варианта неизвестно."}</p>
    </div> : null}

    <div className="mt-4 border-y border-surface-border py-4">
      <p className="text-sm text-ink-soft">Период плана</p>
      <p className="mt-1 font-medium text-ink">{lifecycle?.start_date && lifecycle?.end_date ? <><PlanDate value={lifecycle.start_date} /> — <PlanDate value={lifecycle.end_date} /> включительно</> : "Период этого варианта не указан"}</p>
    </div>
    <dl className="mt-4 grid gap-4 sm:grid-cols-2">
      <Fact label="Ваш лимит времени">{hasHours ? `До ${params.available_hours} ч в неделю` : UNKNOWN}
        <span className="mt-1 block text-sm font-normal text-ink-soft">{hasHours ? "Это максимум, который вы указали." : "Лимит времени для этого варианта неизвестен."}</span>
        <span className="mt-1 block text-sm font-normal text-ink-soft">{Array.isArray(params?.available_days) && params.available_days.length ? `Дни: ${params.available_days.map(day => DAYS.find(item => item.value === day)?.label ?? "День не указан").join(" · ")}` : "Дни не указаны"}</span>
      </Fact>
      <Fact label="Соревнования">{Array.isArray(events) ? events.length ? <ul className="space-y-1">{events.map((event, index) => <li key={index}>{event.priority} · <PlanDate value={event.date} /> · {event.label || "Без названия"}</li>)}</ul> : "Соревнования в этот план не включены" : "Сведения о соревнованиях неизвестны"}</Fact>
    </dl>
    {params?.planning_mode === "manual" ? <p className="mt-4 text-sm text-ink-soft">Ручные фазы: {Array.isArray(params.manual_phases) && params.manual_phases.length ? params.manual_phases.map(phaseLabel).join(" → ") : UNKNOWN}.</p> : null}

    <div className="mt-4 border-t border-surface-border pt-4">
      <h3 className="font-semibold text-ink">Нагрузка в этом плане</h3>
      <p className="mt-1 text-sm text-ink-soft">TSS — баллы тренировочной нагрузки, не часы занятий.</p>
      <dl className="mt-3 grid gap-3 sm:grid-cols-3">
        <Fact label="Всего за этот период"><span className="text-xl tabular-nums">{tss(plan.totals?.total_tss)}</span></Fact>
        <Fact label="Максимум за неделю">{tss(plan.totals?.peak_tss)}</Fact>
        <Fact label="Ориентир на неделю">{tss(plan.weekly_target?.target_weekly_tss)}</Fact>
      </dl>
      {lifecycle?.action === "edit_current" ? <p className="mt-3 text-sm text-ink-soft">Сравнение с прежним планом недоступно: неизвестен период прежних назначений. Здесь — нагрузка нового варианта.</p> : null}
      <details className="mt-3 text-sm text-ink-soft">
        <summary className="cursor-pointer py-2 font-medium text-ink">Как понимать нагрузку</summary>
        <p className="mt-2">Итог относится ко всему периоду, максимум — к самой нагруженной неделе. Ориентир не означает, что каждой неделе назначено столько же.</p>
        <p className="mt-2">Общая длительность и число тренировок здесь не показаны. Их нельзя определить по баллам TSS или по вашему лимиту времени.</p>
      </details>
    </div>
    <details className="mt-1 text-sm text-ink-soft">
      <summary className="cursor-pointer py-2 font-medium text-ink">Другие ограничения</summary>
      {application ? <>
        <p className="mt-2">Доступные сведения из расчёта. Полнота списка и влияние каждого ограничения могут быть неизвестны. Начальный объём проверяется отдельно.</p>
        {application.constraints?.length ? <ul className="mt-2 space-y-2">{application.constraints.map((item, index) => <li key={index}>{item.date || "Дата не указана"} · {constraintKinds[item.kind ?? ""] ?? "Вид ограничения не указан"}{item.source ? <span className="block">Источник: {item.source}</span> : <span className="block">Источник не указан.</span>}</li>)}</ul> : <p className="mt-2">Список ограничений недоступен.</p>}
        {application.protected_dates?.length ? <p className="mt-2">Защищённые даты: {application.protected_dates.join(" · ")}.</p> : null}
      </> : <p className="mt-2">Сведения о дополнительных ограничениях неизвестны.</p>}
    </details>
    {children}
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
