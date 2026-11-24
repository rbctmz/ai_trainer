import type { SwimSeriesFact, SwimSeriesFactEffort, SwimSeriesFactStep } from "@/lib/types";
import { metres } from "./ProgramStructure";

const sources = { garmin: "Круги Garmin", intervals: "Интервалы Intervals.icu" };
const equipment: Record<string, string> = {
  fins: "ласты",
  pull_buoy: "колобашка",
  kickboard: "доска",
  paddles: "лопатки",
  snorkel: "трубка",
  other: "другое снаряжение",
};

function clock(seconds: number | null): string {
  if (seconds == null) return "—";
  const total = Math.round(seconds);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

function authoredAmount(step: SwimSeriesFactStep): string {
  if (step.planned_distance_meters) return metres(step.planned_distance_meters);
  const bounds = step.planned_rest_seconds ?? step.planned_rest_breaths;
  const amount = bounds && (bounds[0] === bounds[1] ? bounds[0] : bounds.join("–"));
  if (step.planned_rest_seconds) {
    return `Отдых ${step.planned_rest_mode === "approximate" ? "около " : ""}${amount} с`;
  }
  return amount ? `Открытый отдых · ${amount} выдоха` : "Открытый отдых";
}

function Effort({ value }: { value: SwimSeriesFactEffort }) {
  return (
    <p className="mt-1 text-xs text-ink-soft">
      Задание по усилию {value.start_percent === value.end_percent
        ? `${value.start_percent}%`
        : `${value.start_percent}–${value.end_percent}%`}
    </p>
  );
}

export function SwimSeriesComparison({ fact }: { fact: SwimSeriesFact }) {
  const explainedGroups = new Set<string>();
  return (
    <section
      aria-label="Серии по заданию тренера"
      className="mt-4 rounded-md border border-surface-border bg-surface p-3"
    >
      <h2 className="text-sm font-medium text-ink">Серии по заданию тренера</h2>
      <p className="mt-1 break-words text-sm text-ink">{fact.title}</p>
      <p className="mt-1 text-xs text-ink-soft">
        Версия {fact.program_revision} · бассейн по плану {metres(fact.planned_pool_length_meters)}
      </p>
      <p className="mt-1 text-xs text-ink-soft">
        {fact.source ? sources[fact.source] : "Нет данных об отрезках"} ·
        {" "}Сопоставлено {fact.matched_swims} из {fact.planned_swims} отрезков
      </p>
      {fact.matched_swims < fact.planned_swims || fact.unassigned_observations > 0 ? (
        <p className="mt-1 text-xs text-ink-soft">Для части тренировки данных не хватило.</p>
      ) : null}
      <details className="mt-3">
        <summary className="cursor-pointer text-sm font-medium text-ink">
          Темп, отрезки и отдых
        </summary>
        {fact.rounds.length > 0 ? (
          <ul aria-label="Темп по кругам" className="mt-2 space-y-2 text-sm">
            {fact.rounds.map((entry) => {
              const round = entry.rounds[entry.rounds.length - 1];
              const key = entry.rounds.map(part => `${part.group_id}:${part.number}`).join("/");
              const firstOfGroup = !explainedGroups.has(round.group_id);
              explainedGroups.add(round.group_id);
              return (
                <li key={key} className="break-words text-ink-soft">
                  <span className="text-ink">{round.name} · круг {round.number}/{round.total}</span>
                  {entry.pace_spread_seconds_per_100m != null ? (
                    <span> · разброс <span className="whitespace-nowrap">{entry.pace_spread_seconds_per_100m.toLocaleString("ru-RU")} с/100 м</span></span>
                  ) : null}
                  {firstOfGroup && round.instructions ? <p className="text-xs">{round.instructions}</p> : null}
                  {firstOfGroup && round.effort ? <Effort value={round.effort} /> : null}
                </li>
              );
            })}
          </ul>
        ) : null}
        <ol aria-label="Отрезки и отдых" className="mt-3 divide-y divide-surface-border">
          {fact.steps.map((step, index) => (
            <li key={index} className="py-2 text-sm text-ink">
              {step.rounds.length > 0 ? (
                <p className="break-words text-xs text-ink-soft">
                  {step.rounds.map(round => `${round.name} ${round.number}/${round.total}`).join(" · ")}
                </p>
              ) : null}
              <p className="break-words font-medium">
                {step.name ? `${step.name} · ` : ""}{authoredAmount(step)}
              </p>
              {step.instructions ? <p className="break-words text-xs text-ink-soft">{step.instructions}</p> : null}
              {step.equipment.length > 0 ? (
                <p className="break-words text-xs text-ink-soft">
                  {step.equipment.map(item => equipment[item] ?? item).join(", ")}
                </p>
              ) : null}
              {step.effort ? <Effort value={step.effort} /> : null}
              {step.observation_indices.length > 0 ? (
                <dl className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs tabular-nums text-ink-soft">
                  <div className="flex gap-1"><dt>Плавание</dt><dd>{clock(step.active_seconds)}</dd></div>
                  <div className="flex gap-1"><dt>Отдых</dt><dd>{clock(step.rest_seconds)}</dd></div>
                  <div className="flex gap-1"><dt>Полное время</dt><dd>{clock(step.elapsed_seconds)}</dd></div>
                  {step.pace_seconds_per_100m != null ? (
                    <div className="flex gap-1"><dt>Темп</dt><dd>{clock(step.pace_seconds_per_100m)} /100 м</dd></div>
                  ) : null}
                </dl>
              ) : <p className="mt-1 text-xs text-ink-soft">Факт недоступен</p>}
            </li>
          ))}
        </ol>
      </details>
    </section>
  );
}
