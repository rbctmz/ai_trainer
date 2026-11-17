"use client";

import { useId, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import type { SwimIntegerRange, SwimSourceSpan, SwimSubjectiveEffortV2, SwimV2NodeInput, SwimV2WorkoutInput } from "@/lib/types";
import { button, input } from "./styles";

export function Field({ label, children }: { label: string; children: (id: string) => ReactNode }) {
  const id = useId();
  return <div className="min-w-0"><label htmlFor={id} className="block text-sm text-ink">{label}</label><div className="mt-1">{children(id)}</div></div>;
}
export function TextField({ label, value, onChange, required = false, multiline = false, onEnter }: { label: string; value: string; onChange: (value: string) => void; required?: boolean; multiline?: boolean; onEnter?: () => void }) {
  const enter = (event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    if (onEnter && !multiline && event.key === "Enter") { event.preventDefault(); onEnter(); }
  };
  return <Field label={label}>{id => multiline ? <textarea id={id} className={`${input} min-h-24`} value={value} required={required} onChange={event => onChange(event.target.value)} /> : <input id={id} className={input} value={value} required={required} onChange={event => onChange(event.target.value)} onKeyDown={enter} />}</Field>;
}
export function NumberField({ label, value, onChange, min = 1, max = 86400, required = true }: { label: string; value: number | null | undefined; onChange: (value: number | null) => void; min?: number; max?: number; required?: boolean }) {
  return <Field label={label}>{id => <input id={id} className={input} type="number" step="1" min={min} max={max} required={required} value={value === 0 && min > 0 ? "" : value ?? ""} onChange={event => onChange(event.target.value === "" ? null : Number(event.target.value))} />}</Field>;
}
export function Choice<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: readonly (readonly [T, string])[]; onChange: (value: T) => void }) {
  return <Field label={label}>{id => <select id={id} className={input} value={value} onChange={event => onChange(event.target.value as T)}>{options.map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select>}</Field>;
}
function RangeFields({ value, onChange, from, to, max = 86400 }: { value: SwimIntegerRange; onChange: (value: SwimIntegerRange) => void; from: string; to: string; max?: number }) {
  return <div className="grid min-w-0 grid-cols-2 gap-2"><NumberField label={from} value={value.minimum} max={max} onChange={minimum => onChange({ ...value, minimum: minimum ?? 0 })} /><NumberField label={to} value={value.maximum} max={max} onChange={maximum => onChange({ ...value, maximum: maximum ?? 0 })} /></div>;
}
export function SpanPicker({ text, spans, onChange, whole = false }: { text: string; spans: SwimSourceSpan[]; onChange: (spans: SwimSourceSpan[]) => void; whole?: boolean }) {
  const textarea = useRef<HTMLTextAreaElement>(null);
  const [open, setOpen] = useState(false);
  const [selection, setSelection] = useState<SwimSourceSpan | null>(null);
  const points = Array.from(text);
  return <div className="space-y-2 text-sm">
    {whole ? <button type="button" className={button} onClick={() => onChange([{ start: 0, end: points.length }])}>Привязать весь исходник</button> : null}
    <details onToggle={event => setOpen(event.currentTarget.open)}>
      <summary className="cursor-pointer text-ink-soft focus:ring-2 focus:ring-accent">Привязка к исходнику ({spans.length})</summary>
      {open ? <div className="mt-2 space-y-2"><Field label="Выделите фрагмент исходника">{id => <textarea ref={textarea} id={id} className={`${input} min-h-40`} readOnly value={text} onSelect={() => {
        const element = textarea.current;
        setSelection(element && element.selectionEnd > element.selectionStart ? { start: Array.from(text.slice(0, element.selectionStart)).length, end: Array.from(text.slice(0, element.selectionEnd)).length } : null);
      }} />}</Field><button type="button" className={button} disabled={!selection} onClick={() => { if (selection) onChange([...spans, selection]); }}>Привязать выделенный фрагмент</button>
        {spans.map((span, index) => <div className="rounded-lg bg-surface-muted p-2" key={index}><p className="whitespace-pre-wrap break-words text-ink-soft">{points.slice(span.start, span.end).join("")}</p><button type="button" className={`${button} mt-1`} onClick={() => onChange(spans.filter((_, at) => at !== index))}>Убрать привязку {index + 1}</button></div>)}
      </div> : null}
    </details>
  </div>;
}

export function newNode(kind: SwimV2NodeInput["kind"] = "swim", id = crypto.randomUUID()): SwimV2NodeInput {
  if (kind === "rest") return { kind, id, mode: "open", seconds: null, breaths: null, instructions: "", source_spans: [] };
  if (kind === "unresolved") return { kind, id, question: "", instructions: "", source_spans: [] };
  if (kind === "group") return { kind, id, name: "", repeat: { kind: "count", count: { minimum: 1, maximum: 1 } }, steps: [], last_rest: "unspecified", instructions: "", source_spans: [] };
  return { kind, id, name: "", quantity: { kind: "open" }, stroke: "unspecified", equipment: [], effort: null, instructions: "", source_spans: [] };
}

function EffortFields({ value, onChange }: { value: SwimSubjectiveEffortV2 | null | undefined; onChange: (value: SwimSubjectiveEffortV2 | null) => void }) {
  return <div className="space-y-2"><label className="flex min-h-8 items-center gap-2 text-sm text-ink"><input type="checkbox" checked={!!value} onChange={event => onChange(event.target.checked ? { kind: "subjective", start_percent: 0, end_percent: 0, scope: "within_node" } : null)} />Задать субъективное усилие</label>
    {value ? <><div className="grid grid-cols-2 gap-2"><NumberField label="Усилие от, %" value={value.start_percent} min={0} max={100} onChange={start => onChange({ ...value, start_percent: start ?? 0 })} /><NumberField label="Усилие до, %" value={value.end_percent} min={0} max={100} onChange={end => onChange({ ...value, end_percent: end ?? 0 })} /></div><Choice label="Изменение усилия" value={value.scope} options={[["within_node", "Внутри отрезка"], ["across_repetitions", "От повтора к повтору"]]} onChange={scope => onChange({ ...value, scope })} /></> : null}
  </div>;
}

export function NodeFields({ node, onChange, source, childrenEditable = false, kindEditable = true, renderTechnique }: { node: SwimV2NodeInput; onChange: (node: SwimV2NodeInput) => void; source: string; childrenEditable?: boolean; kindEditable?: boolean; renderTechnique?: (nodeId: string) => ReactNode }) {
  return <div className="min-w-0 space-y-3">
    {kindEditable ? <Choice label="Тип элемента" value={node.kind} options={[["swim", "Отрезок / упражнение"], ["rest", "Отдых"], ["group", "Серия / круги"], ["unresolved", "Нужно уточнение"]]} onChange={kind => onChange({ ...newNode(kind, node.id), instructions: node.instructions ?? "", source_spans: node.source_spans ?? [] })} /> : null}
    {node.kind === "swim" || node.kind === "group" ? <TextField label="Название элемента" value={node.name} required onChange={name => onChange({ ...node, name })} /> : null}
    {node.kind === "swim" ? <>
      <Choice label="Объём шага" value={node.quantity.kind} options={[["open", "Не задан"], ["distance", "Дистанция"], ["duration", "Время"], ["attempts", "Попытки"]]} onChange={kind => onChange({ ...node, quantity: kind === "distance" ? { kind, meters: 0 } : kind === "duration" ? { kind, seconds: 0 } : kind === "attempts" ? { kind, count: { minimum: 0, maximum: 0 }, distance_hint_meters: null } : { kind } })} />
      {node.quantity.kind === "distance" ? <NumberField label="Дистанция, м" max={100000} value={node.quantity.meters} onChange={meters => onChange({ ...node, quantity: { kind: "distance", meters: meters ?? 0 } })} /> : node.quantity.kind === "duration" ? <NumberField label="Длительность, с" value={node.quantity.seconds} onChange={seconds => onChange({ ...node, quantity: { kind: "duration", seconds: seconds ?? 0 } })} /> : node.quantity.kind === "attempts" ? <><RangeFields value={node.quantity.count} from="Попыток от" to="Попыток до" max={100} onChange={count => { if (node.quantity.kind === "attempts") onChange({ ...node, quantity: { ...node.quantity, count } }); }} /><NumberField label="Ориентир на попытку, м" required={false} max={100000} value={node.quantity.distance_hint_meters} onChange={distance_hint_meters => { if (node.quantity.kind === "attempts") onChange({ ...node, quantity: { ...node.quantity, distance_hint_meters } }); }} /><p className="text-sm text-ink-soft">Ориентир не становится заданной дистанцией серии.</p></> : null}
      <Choice label="Стиль" value={node.stroke ?? "unspecified"} options={[["unspecified", "Не указан"], ["freestyle", "Кроль"], ["backstroke", "На спине"], ["breaststroke", "Брасс"], ["butterfly", "Баттерфляй"], ["mixed", "Смешанный"], ["drill", "Упражнение"]]} onChange={stroke => onChange({ ...node, stroke })} />
      <fieldset><legend className="text-sm text-ink">Снаряжение задания</legend><div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">{([ ["fins", "Ласты"], ["pull_buoy", "Колобашка"], ["kickboard", "Доска"], ["paddles", "Лопатки"], ["snorkel", "Трубка"], ["other", "Другое"] ] as const).map(([item, label]) => <label key={item} className="flex min-h-8 items-center gap-2 text-sm text-ink"><input type="checkbox" checked={node.equipment?.includes(item) ?? false} onChange={event => onChange({ ...node, equipment: event.target.checked ? [...node.equipment ?? [], item] : (node.equipment ?? []).filter(value => value !== item) })} />{label}</label>)}</div></fieldset>
      <EffortFields value={node.effort} onChange={effort => onChange({ ...node, effort })} />
      {renderTechnique?.(node.id)}
    </> : node.kind === "rest" ? <>
      <Choice label="Режим отдыха" value={node.mode} options={[["open", "Произвольный / по выдохам"], ["fixed", "Точно по времени"], ["approximate", "Примерно / диапазон времени"]]} onChange={mode => onChange({ ...node, mode, seconds: mode === "open" ? null : { minimum: 0, maximum: 0 }, breaths: null })} />
      {node.mode !== "open" ? <RangeFields from="Отдых от, с" to="Отдых до, с" value={node.seconds ?? { minimum: 0, maximum: 0 }} onChange={seconds => onChange({ ...node, seconds })} /> : <><label className="flex min-h-8 items-center gap-2 text-sm text-ink"><input type="checkbox" checked={!!node.breaths} onChange={event => onChange({ ...node, breaths: event.target.checked ? { minimum: 0, maximum: 0 } : null })} />Указаны выдохи в воду</label>{node.breaths ? <RangeFields from="Выдохов от" to="Выдохов до" max={100} value={node.breaths} onChange={breaths => onChange({ ...node, breaths })} /> : null}</>}
      {node.mode === "fixed" ? <p className="text-sm text-ink-soft">Для точного отдыха укажите одинаковые границы.</p> : null}
    </> : node.kind === "group" ? <>
      <Choice label="Повторение серии" value={node.repeat.kind} options={[["count", "Число повторов"], ["time", "Временной блок"]]} onChange={kind => onChange({ ...node, repeat: kind === "count" ? { kind, count: { minimum: 1, maximum: 1 } } : { kind, seconds: 0, finish: "timer" } })} />
      {node.repeat.kind === "count" ? <RangeFields from="Повторов от" to="Повторов до" max={100} value={node.repeat.count} onChange={count => onChange({ ...node, repeat: { kind: "count", count } })} /> : <><NumberField label="Время серии, с" value={node.repeat.seconds} onChange={seconds => { if (node.repeat.kind === "time") onChange({ ...node, repeat: { ...node.repeat, seconds: seconds ?? 0 } }); }} /><Choice label="Когда закончить" value={node.repeat.finish} options={[["timer", "По таймеру"], ["current_cycle", "Закончить текущий цикл"]]} onChange={finish => { if (node.repeat.kind === "time") onChange({ ...node, repeat: { ...node.repeat, finish } }); }} /></>}
      <Choice label="Отдых после последнего повтора" value={node.last_rest ?? "unspecified"} options={[["unspecified", "Не уточнён"], ["include", "Включён"], ["omit", "Пропущен"]]} onChange={last_rest => onChange({ ...node, last_rest })} />
      <EffortFields value={node.effort} onChange={effort => onChange({ ...node, effort })} />
      {childrenEditable ? <LocalSteps nodes={node.steps} source={source} renderTechnique={renderTechnique} onChange={steps => onChange({ ...node, steps })} /> : <p className="text-sm text-ink-soft">Вложенные шаги меняются отдельно в структуре программы.</p>}
    </> : <TextField label="Вопрос разбора" value={node.question} required onChange={question => onChange({ ...node, question })} />}
    <TextField label="Инструкция" value={node.instructions ?? ""} multiline required={node.kind === "unresolved"} onChange={instructions => onChange({ ...node, instructions })} />
    <SpanPicker text={source} spans={node.source_spans ?? []} onChange={source_spans => onChange({ ...node, source_spans })} />
  </div>;
}

export function LocalSteps({ nodes, source, onChange, renderTechnique }: { nodes: SwimV2NodeInput[]; source: string; onChange: (nodes: SwimV2NodeInput[]) => void; renderTechnique?: (nodeId: string) => ReactNode }) {
  return <div className="min-w-0 space-y-3">{nodes.map((node, index) => <fieldset key={node.id} className="min-w-0 space-y-3 rounded-lg border border-surface-border p-3"><legend className="px-1 text-sm font-semibold text-ink">Элемент {index + 1}</legend><NodeFields node={node} source={source} childrenEditable renderTechnique={renderTechnique} onChange={changed => onChange(nodes.map((value, at) => at === index ? changed : value))} /><div className="flex flex-wrap gap-2"><button type="button" className={button} onClick={() => onChange(nodes.filter((_, at) => at !== index))}>Убрать элемент {index + 1}</button>{index > 0 ? <button type="button" className={button} onClick={() => { const moved = [...nodes]; [moved[index - 1], moved[index]] = [moved[index], moved[index - 1]]; onChange(moved); }}>Выше</button> : null}</div></fieldset>)}<button type="button" className={button} onClick={() => onChange([...nodes, newNode()])}>Добавить шаг</button></div>;
}

export function ContextFields({ workout, onChange }: { workout: SwimV2WorkoutInput; onChange: (workout: SwimV2WorkoutInput) => void }) {
  return <><Choice label="Среда" value={workout.environment} options={[["pool", "Бассейн"], ["open_water", "Открытая вода"]]} onChange={environment => onChange({ ...workout, environment, pool_length_meters: null })} />{workout.environment === "pool" ? <NumberField label="Длина бассейна, м" min={10} max={100} value={workout.pool_length_meters} onChange={pool_length_meters => onChange({ ...workout, pool_length_meters })} /> : null}</>;
}
