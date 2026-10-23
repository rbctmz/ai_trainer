"use client";

import type { BuiltPlan, ForecastPoint, PlanWeek } from "@/lib/types";
import { shownNumber } from "./PlanDecisionSummary";
import { phaseLabel } from "./planningLabels";

const lines = [
  { key: "ctl" as const, label: "CTL — модельная форма", color: "stroke-accent dark:stroke-ink", dash: undefined },
  { key: "atl" as const, label: "ATL — модельная усталость", color: "stroke-ink dark:stroke-tone-warning", dash: "7 4" },
  { key: "tsb" as const, label: "TSB — модельный баланс", color: "stroke-ink dark:stroke-tone-success", dash: "2 4" },
];

export function ForecastSection({ forecast }: { forecast?: BuiltPlan["forecast"] | null }) {
  const supplied = Array.isArray(forecast?.points) ? forecast.points : [];
  const points = supplied.filter(point => typeof point?.date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(point.date) && Number.isFinite(Date.parse(point.date)) && [point.ctl, point.atl, point.tsb].every(value => typeof value === "number" && Number.isFinite(value)));
  const w = 680, h = 210, pad = 30;
  const values = points.flatMap(point => [point.ctl, point.atl, point.tsb]);
  const min = Math.min(0, ...values), max = Math.max(0, ...values), span = max - min || 1;
  const firstDate = points.length ? Date.parse(points[0].date) : 0;
  const dateSpan = points.length ? Date.parse(points[points.length - 1].date) - firstDate || 1 : 1;
  const x = (point: ForecastPoint) => pad + (Date.parse(point.date) - firstDate) / dateSpan * (w - 2 * pad);
  const y = (value: number) => h - pad - (value - min) / span * (h - 2 * pad);
  const path = (key: "ctl" | "atl" | "tsb") => points.map((point, index) => `${index ? "L" : "M"}${x(point)},${y(point[key])}`).join(" ");
  return <section aria-label="Модельный прогноз нагрузки" className="rounded-card border border-surface-border bg-surface p-5 shadow-card">
    <h2 className="font-semibold text-ink">Модельный прогноз нагрузки</h2>
    <p className="mt-2 text-sm text-ink-soft">Сценарий по данным этого предложения и назначенной нагрузке. Модельные значения не подтверждают достижение тренировочной цели.</p>
    {points.length ? <>
      <p className="mt-2 text-sm text-ink">Даты доступных точек: {points[0].date} — {points[points.length - 1].date}.</p>
      {points.length !== supplied.length ? <p className="mt-2 text-sm text-tone-warning">Часть точек не передана полностью; показаны доступные значения.</p> : null}
      {points.length > 1 ? <svg viewBox={`0 0 ${w} ${h}`} className="mt-3 w-full" role="img" aria-label="Изменение CTL, ATL и TSB. Точные даты и значения доступны в таблице ниже.">
        <line x1={pad} x2={w - pad} y1={y(0)} y2={y(0)} className="stroke-surface-border" />
        <text x={2} y={y(max) + 4} className="fill-ink-soft text-xs">{shownNumber(max)}</text>
        <text x={2} y={y(min) + 4} className="fill-ink-soft text-xs">{shownNumber(min)}</text>
        <text x={pad} y={h - 4} className="fill-ink-soft text-xs">{points[0].date}</text>
        <text x={w - pad} y={h - 4} textAnchor="end" className="fill-ink-soft text-xs">{points[points.length - 1].date}</text>
        {lines.map(line => <path key={line.key} d={path(line.key)} fill="none" className={line.color} strokeWidth={2} strokeDasharray={line.dash} />)}
      </svg> : null}
      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-sm">{lines.map(line => <li key={line.key} className="flex items-center gap-2 text-ink"><svg width="24" height="12" aria-hidden="true"><line x1="0" x2="24" y1="6" y2="6" className={line.color} strokeWidth={2} strokeDasharray={line.dash} /></svg>{line.label}</li>)}</ul>
      <details className="mt-3 text-sm text-ink-soft"><summary className="cursor-pointer py-2 font-medium text-ink">Даты и значения прогноза</summary>
        <div className="mt-2 overflow-x-auto"><table className="w-full text-left tabular-nums"><caption className="sr-only">Доступные модельные значения по датам</caption><thead><tr>{["Дата", "CTL", "ATL", "TSB"].map(label => <th key={label} className="px-2 py-2 font-medium">{label}</th>)}</tr></thead><tbody>{points.map((point: ForecastPoint, index) => <tr key={index} className="border-t border-surface-border"><th scope="row" className="whitespace-nowrap px-2 py-2 font-normal">{point.date}</th>{lines.map(line => <td key={line.key} className="px-2 py-2">{shownNumber(point[line.key])}</td>)}</tr>)}</tbody></table></div>
      </details>
    </> : <p className="mt-3 text-sm text-ink-soft">Датированные значения прогноза не переданы.</p>}
  </section>;
}

export function WeeksTable({ weeks }: { weeks?: PlanWeek[] | null }) {
  const hasRaceForecast = Array.isArray(weeks) && weeks.some(week => week.race_forecast_tss != null);
  return <section aria-label="Назначения по неделям" className="rounded-card border border-surface-border bg-surface p-5 shadow-card">
    <h2 className="font-semibold text-ink">Назначения по неделям</h2>
    <p className="mt-2 text-sm text-ink-soft">Нагрузки недели и дисциплин указаны в TSS. Это назначения, а не фактическое выполнение.{hasRaceForecast ? " Прогноз нагрузки самого старта указан отдельно и не входит в тренировочный итог." : ""}</p>
    {Array.isArray(weeks) && weeks.length ? <div className="mt-3 overflow-x-auto"><table className="w-full text-sm"><caption className="sr-only">Назначенная тренировочная нагрузка по неделям и дисциплинам</caption>
      <thead><tr className="border-b border-surface-border text-left">{["Начало недели", "Фаза", "Всего, TSS", "Вело, TSS", "Бег, TSS", "Плавание, TSS", ...(hasRaceForecast ? ["Старт: прогноз, TSS"] : []), "Примечание"].map(label => <th key={label} className="whitespace-nowrap px-3 py-2 font-medium text-ink-soft">{label}</th>)}</tr></thead>
      <tbody>{weeks.map((week, index) => <tr key={index} className="border-b border-surface-border last:border-0 text-ink">
        <th scope="row" className="whitespace-nowrap px-3 py-2 font-normal">{week.week_start || "Дата не указана"}</th><td className="px-3 py-2">{phaseLabel(week.phase)}</td>
        {[week.weekly_tss, week.bike, week.run, week.swim, ...(hasRaceForecast ? [week.race_forecast_tss] : [])].map((value, i) => <td key={i} className="px-3 py-2 tabular-nums">{shownNumber(value)}</td>)}
        <td className="min-w-40 px-3 py-2 text-ink-soft">{week.adjustment_note && week.adjustment_note !== "—" ? <details><summary className="cursor-pointer py-1">Примечание расчёта</summary><p>{week.adjustment_note}</p></details> : "—"}</td>
      </tr>)}</tbody>
    </table></div> : <p className="mt-3 text-sm text-ink-soft">Недельные назначения не переданы.</p>}
  </section>;
}
