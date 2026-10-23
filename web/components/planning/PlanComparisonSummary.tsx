"use client";

import { useId } from "react";
import type { PlanBuildComparison, PlanComparisonDayValue, PlanComparisonParameters, PlanComparisonSession, PlanComparisonSide, WorkoutTarget } from "@/lib/types";
import { formatTarget } from "@/components/WorkoutStrip";
import { DAYS, DISTANCES, GOAL_TYPES, phaseLabel } from "./planningLabels";
import { PlanningDate } from "./PlanningDate";

const unknown = "Нет данных";
const numeric = (value: number | null | undefined, unit: string) => typeof value === "number" && Number.isFinite(value) ? `${value} ${unit}` : unknown;
const intentLabels: Record<string, string> = { develop: "Развивать форму", maintain: "Поддерживать форму" };
const modeLabels: Record<string, string> = { training_goal: "Без привязки к старту", event_goal: "К старту", manual: "Ручные фазы" };
const demandLabels: Record<string, string> = { easy: "Легко", moderate: "Умеренно", demanding: "Требовательно", aggressive: "Агрессивно" };
const sportLabels: Record<string, string> = { run: "Бег", bike: "Велосипед", swim: "Плавание", brick: "Вело → бег" };
const roleLabels: Record<string, string> = { easy: "Лёгкая", recovery: "Восстановление", quality: "Интенсивная", long: "Длительная", activation: "Активация", race: "Старт", off: "Отдых" };
const changeLabels = { added: "Назначения добавлены", removed: "Назначения убраны", changed: "Назначения изменены", unchanged: "Без изменений", unknown: "Недостаточно данных для сравнения" };

function Period({ side }: { side: PlanComparisonSide }) {
  return side.scope ? <><PlanningDate value={side.scope.start_date} /> — <PlanningDate value={side.scope.end_date} /><span className="block font-normal text-ink-soft">включительно</span></> : <>{unknown}</>;
}
function preparation(params: PlanComparisonParameters) {
  const goal = GOAL_TYPES.find(item => item.value === params.goal_type)?.label ?? unknown;
  const distance = DISTANCES[params.goal_type ?? ""]?.find(item => item.value === params.distance)?.label ?? unknown;
  return `${goal} · ${distance}`;
}
const knownText = (text: string) => text.includes(unknown) ? null : text;
const numberKey = (value: number | null) => typeof value === "number" && Number.isFinite(value) ? String(value) : null;
function eventKey(params: PlanComparisonParameters) {
  return params.events === null ? null : JSON.stringify(params.events.map(event => [event.priority, event.date, event.label || "Без названия"]));
}
function daysLabel(days: string[] | null) {
  return days === null ? unknown : days.length ? days.map(day => DAYS.find(item => item.value === day)?.label ?? unknown).join(" · ") : "Дни не выбраны";
}
function targetLabel(value: unknown) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return "Цель не указана";
  const target = value as WorkoutTarget;
  const type = String(target.type ?? "");
  const finite = (value: unknown) => typeof value === "number" && Number.isFinite(value);
  const pair = ["power", "heart_rate", "relative_rpe"].includes(type) && finite(target.low) && finite(target.high);
  const pace = type.includes("pace") && finite(target.fast) && finite(target.slow);
  const distance = type === "distance" && finite(target.low);
  return pair || pace || distance ? formatTarget(target) : "Цель не указана";
}
function Session({ session }: { session: PlanComparisonSession }) {
  return <li className="min-w-0 break-words">
    <p className="font-medium">{session.name ?? sportLabels[session.sport ?? ""] ?? "Тренировка"}</p>
    <p className="mt-1">{sportLabels[session.sport ?? ""] ?? "Дисциплина не указана"} · {roleLabels[session.role ?? ""] ?? "Тип не указан"}</p>
    <p className="mt-1">{numeric(session.minutes, "мин")} · {numeric(session.tss, "TSS")}</p>
    {session.legs?.length ? <ol className="mt-2 list-inside list-decimal space-y-3">{session.legs.map((leg, index) => <Session key={index} session={leg} />)}</ol> : session.steps?.length ? <details className="mt-2">
      <summary className="cursor-pointer py-1 text-ink">Этапы и цели тренировки</summary>
      <ol className="mt-2 space-y-2">{session.steps.map((step, index) => <li key={index}>{step.name ?? "Этап"} · {numeric(step.duration_seconds, "с")} · {targetLabel(step.target)}</li>)}</ol>
    </details> : <p className="mt-1">Этапы тренировки не сохранены</p>}
  </li>;
}
function DayValue({ value }: { value: PlanComparisonDayValue }) {
  if (value.state === "unknown") return <p>{unknown}</p>;
  if (value.state === "outside") return <p>Вне периода этого плана</p>;
  if (value.state === "rest") return <><p className="mb-2">{value.phase ? phaseLabel(value.phase) : "Фаза не указана"}</p><p>Отдых · {numeric(value.tss, "TSS")}</p></>;
  return <><p className="mb-2">{value.phase ? phaseLabel(value.phase) : "Фаза не указана"}</p><ul className="space-y-3">{value.sessions?.map((session, index) => <Session key={index} session={session} />)}</ul></>;
}
function Events({ params }: { params: PlanComparisonParameters }) {
  return params.events === null ? <>{unknown}</> : params.events.length ? <ul className="space-y-2">{params.events.map((event, index) => <li key={index}>{event.priority} · <PlanningDate value={event.date} /> · {event.label || "Без названия"}</li>)}</ul> : <>Соревнования не включены</>;
}

export function PlanComparisonSummary({ comparison, historical, weeklyTarget }: { comparison: PlanBuildComparison; historical: boolean; weeklyTarget: number | null | undefined }) {
  const statusId = useId();
  const before = comparison.before;
  if (!before) return null;
  const after = comparison.after;
  // Keys describe displayed summary facts only. Calendar/content change states
  // remain server-owned; absent facts are never classified as a change here.
  const rows: { label: string; value: (side: PlanComparisonSide) => React.ReactNode; displayKey: (side: PlanComparisonSide) => string | null }[] = [
    { label: "Период плана", value: side => <Period side={side} />, displayKey: side => side.scope ? `${side.scope.start_date}/${side.scope.end_date}` : null },
    { label: "Подготовка", value: side => preparation(side.parameters), displayKey: side => knownText(preparation(side.parameters)) },
    { label: "Намерение", value: side => intentLabels[side.parameters.intent ?? ""] ?? unknown, displayKey: side => intentLabels[side.parameters.intent ?? ""] ?? null },
    { label: "Акцент", value: side => side.parameters.focus === "balanced_triathlon" ? "Сбалансированная подготовка" : unknown, displayKey: side => side.parameters.focus === "balanced_triathlon" ? "Сбалансированная подготовка" : null },
    { label: "Подход", value: side => modeLabels[side.parameters.planning_mode ?? ""] ?? unknown, displayKey: side => modeLabels[side.parameters.planning_mode ?? ""] ?? null },
    { label: "Лимит времени", value: side => side.parameters.available_hours === null ? unknown : `До ${numeric(side.parameters.available_hours, "ч в неделю")}`, displayKey: side => numberKey(side.parameters.available_hours) },
    { label: "Дни занятий", value: side => daysLabel(side.parameters.available_days), displayKey: side => knownText(daysLabel(side.parameters.available_days)) },
    { label: "Режим нагрузки", value: side => demandLabels[side.parameters.demand ?? ""] ?? unknown, displayKey: side => demandLabels[side.parameters.demand ?? ""] ?? null },
    { label: "Сумма за весь период", value: side => <span className="text-base font-semibold">{numeric(side.total_tss, "TSS")}</span>, displayKey: side => numberKey(side.total_tss) },
    { label: "Максимум за неделю", value: side => numeric(side.peak_tss, "TSS"), displayKey: side => numberKey(side.peak_tss) },
    { label: "Соревнования", value: side => <Events params={side.parameters} />, displayKey: side => eventKey(side.parameters) },
  ];
  return <section aria-label="Было и станет" className="mt-5 min-w-0">
    <h3 className="text-base font-semibold text-ink">{historical ? "Сравнение версий из предложения" : "Что изменится в плане"}</h3>
    <p className="mt-1 text-sm text-ink-soft">{historical ? "Показаны версии, зафиксированные в этом предложении." : "Проверьте изменения перед сохранением."}</p>
    <p className="mt-2 text-sm text-ink-soft">Различающиеся известные значения выделены цветом и пометкой «Изменено».</p>
    <table className="mt-3 w-full table-fixed border-collapse text-left text-sm text-ink">
      <caption className="sr-only">{historical ? "Версии из предложения" : "Текущий и предлагаемый план"}: периоды, параметры и назначенная нагрузка</caption>
      <thead><tr className="border-b border-surface-border"><th scope="col" className="w-[28%] py-3 pr-2">Параметр</th><th scope="col" className="px-2 py-3">{historical ? "Было в предложении" : "Текущий план"}</th><th scope="col" className="px-2 py-3">{historical ? "Предложенный вариант" : "Предлагаемый план"}</th></tr></thead>
      <tbody>{rows.map((row, index) => {
        const oldValue = row.displayKey(before);
        const newValue = row.displayKey(after);
        const incomplete = oldValue === null || newValue === null;
        const differs = !incomplete && oldValue !== newValue;
        const marker = differs ? "Изменено" : incomplete ? "Нет данных для сравнения" : null;
        const markerId = `${statusId}-${index}`;
        return <tr key={row.label} className={`border-b border-surface-border${differs ? " bg-accent/10" : ""}`}>
          <th scope="row" aria-label={row.label} aria-describedby={marker ? markerId : undefined} className="break-words py-3 pr-2 align-top font-normal text-ink-soft">
            {row.label}{marker ? <span id={markerId} className={`mt-1 block text-xs${differs ? " font-semibold text-ink" : ""}`}>{marker}</span> : null}
          </th>
          <td className="break-words px-2 py-3 align-top">{row.value(before)}</td><td className="break-words px-2 py-3 align-top">{row.value(after)}</td>
        </tr>;
      })}</tbody>
    </table>
    <p className="mt-3 text-sm text-ink-soft">TSS — баллы нагрузки. Сумма относится к периоду в своём столбце. Разница сумм за разные периоды не означает изменение недельной нагрузки.</p>
    <p className="mt-2 text-sm text-ink-soft">Ориентир предлагаемого плана на неделю: {numeric(weeklyTarget, "TSS")}. Это расчётный ориентир, а не назначение каждой неделе.</p>
    {comparison.status !== "complete" ? <p role="note" className="mt-3 rounded-lg bg-tone-warning/10 p-3 text-sm text-ink">В сравнении есть неполные данные. «Нет данных» не означает ноль или отдых; полный итог изменений недоступен.</p> : null}
    <details className="mt-4 text-sm text-ink-soft">
      <summary className="cursor-pointer py-2 font-medium text-ink">Изменения расписания по датам</summary>
      {comparison.counts ? <p className="my-2">Дни: с добавленными назначениями — {comparison.counts.added}; с убранными — {comparison.counts.removed}; с изменениями — {comparison.counts.changed}; без изменений — {comparison.counts.unchanged}.</p> : null}
      <p className="my-2">Показаны изменения назначений. История и записи выполнения сохраняются. Перенос между датами отдельно не определяется.</p>
      <div className="overflow-x-auto rounded-lg border border-surface-border" role="region" aria-label="Расписание до и после" tabIndex={0}>
        <table className="w-full min-w-[560px] table-fixed text-left">
          <thead><tr className="border-b border-surface-border"><th scope="col" className="w-[22%] p-3">Дата</th><th scope="col" className="p-3">Было</th><th scope="col" className="p-3">{historical ? "Предложено" : "Станет"}</th></tr></thead>
          <tbody>{comparison.days.map(day => <tr key={day.date} className={`border-b border-surface-border${["added", "removed", "changed"].includes(day.change) ? " bg-accent/10" : ""}`}><th scope="row" className="break-words p-3 align-top font-medium text-ink"><PlanningDate value={day.date} /><span className="mt-2 block font-normal text-ink-soft">{changeLabels[day.change] ?? "Нет данных для сравнения"}</span></th><td className="break-words p-3 align-top"><DayValue value={day.before} /></td><td className="break-words p-3 align-top"><DayValue value={day.after} /></td></tr>)}</tbody>
        </table>
      </div>
      {!comparison.days.length ? <p className="mt-2">Датированное сравнение назначений недоступно.</p> : null}
    </details>
  </section>;
}
