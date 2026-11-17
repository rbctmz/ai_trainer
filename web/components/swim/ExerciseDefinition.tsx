import type { SwimExerciseDocument } from "@/lib/types";

const equipment: Record<string, string> = { fins: "Ласты", pull_buoy: "Колобашка", kickboard: "Доска", paddles: "Лопатки", snorkel: "Трубка", other: "Другое" };
const strokes: Record<string, string> = { unspecified: "Не указан", freestyle: "Кроль", backstroke: "На спине", breaststroke: "Брасс", butterfly: "Баттерфляй", mixed: "Смешанный", drill: "Упражнение" };
export function videoTime(seconds: number): string { return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`; }

export function ExerciseDefinition({ document }: { document: SwimExerciseDocument }) {
  return <div className="min-w-0 space-y-3 text-sm">
    <h3 className="break-words text-lg font-semibold text-ink">{document.name} — {document.variant}</h3>
    <p className="whitespace-pre-wrap break-words text-ink">{document.instructions}</p>
    <p className="text-ink-soft">Стиль: {strokes[document.stroke]} · {document.environments.map(value => value === "pool" ? "Бассейн" : "Открытая вода").join(", ")}</p>
    {document.equipment.length ? <p className="text-ink-soft">Снаряжение варианта: {document.equipment.map(item => equipment[item]).join(", ")}</p> : null}
    {document.aliases.length ? <p className="break-words text-ink-soft">Также называется: {document.aliases.join("; ")}</p> : null}
    {document.source_label ? <p className="break-words text-ink-soft">Источник: {document.source_label}</p> : null}
    {document.source_text ? <details><summary className="cursor-pointer text-ink-soft focus:ring-2 focus:ring-accent">Исходник упражнения</summary><blockquote className="mt-2 whitespace-pre-wrap break-words border-l-2 border-surface-border pl-3 text-ink-soft">{document.source_text}</blockquote></details> : null}
    {document.video_cues.map((cue, index) => <p className="break-words text-ink-soft" key={index}>Видео «{cue.source_label}»: {videoTime(cue.start_seconds)} — {videoTime(cue.end_seconds)}</p>)}
  </div>;
}
