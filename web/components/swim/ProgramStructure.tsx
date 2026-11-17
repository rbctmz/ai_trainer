"use client";

import { useState } from "react";
import type {
  SwimExerciseBinding, SwimIntegerRange, SwimProgramDocument, SwimProgramDocumentV2,
  SwimProgramNode, SwimProgramSummary, SwimProgramSummaryV2, SwimSourceSpan, SwimV2Node,
} from "@/lib/types";
import { button, panel } from "./styles";
import { videoTime } from "./ExerciseDefinition";

type Document = SwimProgramDocument | SwimProgramDocumentV2;
type Summary = SwimProgramSummary | SwimProgramSummaryV2;
type Node = SwimProgramNode | SwimV2Node;

const equipment: Record<string, string> = { fins: "ласты", pull_buoy: "колобашка", kickboard: "доска", paddles: "лопатки", snorkel: "трубка", other: "другое снаряжение" };
const strokes: Record<string, string> = { freestyle: "кроль", backstroke: "на спине", breaststroke: "брасс", butterfly: "баттерфляй", mixed: "смешанный стиль", drill: "упражнение" };
const warnings: Record<string, string> = {
  pool_distance_not_multiple: "Дистанция шага не кратна длине бассейна. Проверьте способ учёта отрезка.",
  last_rest_unspecified: "Отдых после последнего повтора не уточнён.",
  exercise_environment_mismatch: "Вариант упражнения не подходит для указанной среды.",
  unresolved_source: "Есть неразобранный элемент программы.",
  source_not_covered: "Есть фрагменты исходника без привязки к структуре.",
};

export function metres(value: number): string { return `${new Intl.NumberFormat("ru-RU").format(value)} м`; }
export function range(value: SwimIntegerRange): string { return value.minimum === value.maximum ? String(value.minimum) : `${value.minimum}–${value.maximum}`; }
function clock(seconds: number): string { return seconds % 60 === 0 ? `${seconds / 60} мин` : `${seconds} с`; }

function SourceFragments({ spans, source }: { spans: SwimSourceSpan[]; source: string[] }) {
  const [open, setOpen] = useState(false);
  if (!spans.length) return null;
  return <details className="mt-2 text-sm" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary className="cursor-pointer text-ink-soft focus:outline-none focus:ring-2 focus:ring-accent">Фрагменты исходника</summary>
    {open ? spans.map((span, index) => <blockquote className="mt-2 whitespace-pre-wrap break-words border-l-2 border-surface-border pl-3 text-ink-soft" key={index}>{source.slice(span.start, span.end).join("")}</blockquote>) : null}
  </details>;
}

function Technique({ binding }: { binding: SwimExerciseBinding }) {
  return <details className="mt-2 rounded-lg bg-surface-muted p-3 text-sm">
    <summary className="cursor-pointer text-ink focus:outline-none focus:ring-2 focus:ring-accent">Техника: {binding.document.name} — {binding.document.variant} · версия {binding.revision}</summary>
    <p className="mt-2 whitespace-pre-wrap break-words text-ink">{binding.document.instructions}</p>
    {binding.document.equipment.length ? <p className="mt-2 text-ink-soft">Снаряжение варианта: {binding.document.equipment.map(item => equipment[item]).join(", ")}</p> : null}
    {binding.document.video_cues.map((cue, index) => <p className="mt-2 text-ink-soft" key={index}>Видео «{cue.source_label}»: {videoTime(cue.start_seconds)} — {videoTime(cue.end_seconds)}</p>)}
  </details>;
}

function dose(node: Node): string {
  if (node.kind === "rest") {
    if (node.seconds !== null) {
      const seconds = typeof node.seconds === "number" ? String(node.seconds) : range(node.seconds);
      return `${node.mode === "approximate" ? "Около " : ""}${seconds} с отдыха`;
    }
    const breaths = node.breaths === null ? "" : `${typeof node.breaths === "number" ? node.breaths : range(node.breaths)} выдоха · `;
    return `${breaths}открытый отдых`;
  }
  if (node.kind === "unresolved") return "Нужно уточнение";
  if (node.kind === "group") {
    if ("repetitions" in node) return `${node.repetitions} ×`;
    return node.repeat.kind === "count" ? `${range(node.repeat.count)} ×` : `${clock(node.repeat.seconds)} по циклу`;
  }
  if ("distance_meters" in node) return metres(node.distance_meters);
  const quantity = node.quantity;
  if (quantity.kind === "distance") return metres(quantity.meters);
  if (quantity.kind === "duration") return clock(quantity.seconds);
  if (quantity.kind === "attempts") return `${range(quantity.count)} попыток · дистанция не задана`;
  return "Дистанция и время не заданы";
}

function Step({ node, source, bindings, onEdit, onAdd, disabled }: {
  node: Node; source: string[]; bindings: Map<string, SwimExerciseBinding>;
  onEdit?: (id: string) => void; onAdd?: (id: string) => void;
  disabled: boolean;
}) {
  const name = "name" in node ? node.name : node.kind === "rest" ? "Отдых" : "Неразобранный элемент";
  const spans = "source_spans" in node ? node.source_spans : [];
  const instruction = node.instructions ? <p className="mt-2 whitespace-pre-wrap break-words text-sm text-ink-soft">{node.instructions}</p> : null;
  const effort = "effort" in node && node.effort ? <p className="mt-2 text-sm text-ink-soft">Субъективное усилие: {node.effort.start_percent} → {node.effort.end_percent}%{"scope" in node.effort ? node.effort.scope === "within_node" ? " · внутри отрезка" : " · от повтора к повтору" : ""}</p> : null;
  const edit = onEdit ? <button type="button" className={button} disabled={disabled} aria-label={`Изменить: ${name}`} onClick={() => onEdit(node.id)}>Изменить</button> : null;
  if (node.kind === "group") return <details className="min-w-0 rounded-lg border border-surface-border p-3" aria-label={name}>
    <summary className="cursor-pointer break-words text-sm text-ink focus:outline-none focus:ring-2 focus:ring-accent"><span className="font-semibold">{name}</span><span className="ml-2 text-ink-soft">{dose(node)}</span></summary>
    {instruction}{effort}
    {"repeat" in node && node.repeat.kind === "time" ? <p className="mt-2 text-sm text-ink-soft">{node.repeat.finish === "current_cycle" ? "Закончить текущий цикл" : "Закончить по таймеру"}</p> : null}
    {node.last_rest !== "unspecified" ? <p className="mt-2 text-sm text-ink-soft">Последний отдых: {node.last_rest === "include" ? "включён" : "пропущен"}</p> : null}
    <div className="mt-3 space-y-2 border-l-2 border-surface-border pl-3">{node.steps.map(child => <Step key={child.id} node={child} source={source} bindings={bindings} onEdit={onEdit} onAdd={onAdd} disabled={disabled} />)}</div>
    <SourceFragments spans={spans} source={source} />
    {onEdit || onAdd ? <div className="mt-3 flex flex-wrap gap-2">{edit}{onAdd ? <button type="button" className={button} disabled={disabled} onClick={() => onAdd(node.id)}>Добавить шаг в группу</button> : null}</div> : null}
  </details>;
  return <div className={`min-w-0 rounded-lg border p-3 ${node.kind === "unresolved" ? "border-tone-warning/50 bg-tone-warning/5" : "border-surface-border"}`}>
    <div className="flex flex-wrap items-start justify-between gap-2"><p className="min-w-0 break-words text-sm font-medium text-ink">{name}</p><span className="text-sm text-ink-soft">{dose(node)}</span></div>
    {instruction}{effort}
    {node.kind === "swim" ? <>
      {strokes[node.stroke] ? <p className="mt-1 text-sm text-ink-soft">{strokes[node.stroke]}</p> : null}
      {node.equipment.length ? <p className="mt-1 text-sm text-ink-soft">{node.equipment.map(item => equipment[item]).join(", ")}</p> : null}
      {"quantity" in node && node.quantity.kind === "attempts" && node.quantity.distance_hint_meters ? <p className="mt-1 text-sm text-ink-soft">Ориентир на попытку: {metres(node.quantity.distance_hint_meters)}. Это не заданная дистанция серии.</p> : null}
    </> : node.kind === "unresolved" ? <p className="mt-2 text-sm text-ink"><strong>Вопрос разбора:</strong> {node.question}</p> : null}
    {bindings.has(node.id) ? <Technique binding={bindings.get(node.id)!} /> : null}
    <SourceFragments spans={spans} source={source} />
    {edit ? <div className="mt-3">{edit}</div> : null}
  </div>;
}

export function ProgramSummary({ document, summary }: { document: Document; summary: Summary }) {
  const known = "known_distance_meters" in summary ? summary.known_distance_meters : summary.distance_meters;
  return <section className={panel} aria-label="Объём программы">
      <h2 className="text-lg font-semibold text-ink">Объём программы</h2>
      <p className="mt-2 text-lg font-semibold text-ink">{summary.distance_meters === null ? "Полная дистанция неизвестна" : metres(summary.distance_meters)}</p>
      {summary.distance_meters === null ? <p className="mt-1 text-sm text-ink-soft">Известная фиксированная часть: {metres(known)}</p> : null}
      <p className="mt-1 text-sm text-ink-soft">Тренировок: {document.workouts.length} · Полная длительность и TSS не определены</p>
      {summary.warnings.length ? <ul className="mt-3 space-y-1 border-l-2 border-tone-warning pl-3 text-sm text-ink">{summary.warnings.map((warning, index) => <li key={index}>{document.workouts.find(item => item.id === warning.workout_id)?.title}{warning.workout_id ? ": " : ""}{warnings[warning.code] || "Требуется проверка структуры."}</li>)}</ul> : null}
    </section>;
}

export function ProgramStructure({ document, summary, onEditNode, onAddNode, onEditWorkout, editingDisabled = false, showSummary = true }: {
  document: Document; summary: Summary; onEditNode?: (id: string) => void;
  onAddNode?: (id: string) => void; onEditWorkout?: (id: string) => void;
  editingDisabled?: boolean; showSummary?: boolean;
}) {
  const source = Array.from(document.source_text);
  const bindings = new Map<string, SwimExerciseBinding>(document.schema_version === 2 ? document.exercise_bindings.map(binding => [binding.node_id, binding]) : []);
  return <div className="space-y-4">
    {showSummary ? <ProgramSummary document={document} summary={summary} /> : null}
    <section className="space-y-4" aria-label="Структура программы">
      <h2 className="text-lg font-semibold text-ink">Структура программы</h2>
      {document.workouts.map(workout => {
        const total = summary.workouts.find(item => item.workout_id === workout.id);
        return <article key={workout.id} className={panel} aria-label={workout.title}>
          <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="break-words text-lg font-semibold text-ink">{workout.title}</h3><p className="mt-1 text-sm text-ink-soft">{workout.environment === "pool" ? `Бассейн · ${metres(workout.pool_length_meters!)}` : "Открытая вода"} · {total?.distance_meters === null || !total ? "Дистанция неизвестна" : metres(total.distance_meters)}</p></div>{onEditWorkout ? <button type="button" className={button} disabled={editingDisabled} onClick={() => onEditWorkout(workout.id)}>Изменить тренировку</button> : null}</div>
          <div className="mt-4 space-y-2">{workout.steps.map(node => <Step key={node.id} node={node} source={source} bindings={bindings} onEdit={onEditNode} onAdd={onAddNode} disabled={editingDisabled} />)}</div>
          {onAddNode ? <button type="button" className={`${button} mt-3`} disabled={editingDisabled} onClick={() => onAddNode(workout.id)}>Добавить шаг</button> : null}
        </article>;
      })}
    </section>
  </div>;
}
