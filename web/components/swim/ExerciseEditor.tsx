"use client";

import { useEffect, useState } from "react";
import { isDemo } from "@/lib/api";
import { swimError, swimPost } from "@/lib/swim-api";
import type { SwimExerciseConfirmRequest, SwimExerciseDocument, SwimExercisePreviewResponse, SwimExerciseVersionResponse } from "@/lib/types";
import { Choice, NumberField, TextField } from "./EditorFields";
import { ExerciseDefinition } from "./ExerciseDefinition";
import { button, panel, primary } from "./styles";

export function ExerciseEditor({ initial, baseRevision, onSaved, onClose }: { initial: SwimExerciseDocument; baseRevision: number; onSaved: (version: SwimExerciseVersionResponse) => void; onClose: () => void }) {
  const [document, setDocument] = useState(initial);
  const [aliases, setAliases] = useState(initial.aliases.join("\n"));
  const [preview, setPreview] = useState<SwimExercisePreviewResponse | null>(null);
  const [confirmation, setConfirmation] = useState<SwimExerciseConfirmRequest | null>(null);
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const key = `swim-exercise-form-${isDemo() ? "demo" : "real"}-${initial.id}-${baseRevision}`;
  useEffect(() => {
    try {
      const buffer = JSON.parse(sessionStorage.getItem(key) || "null");
      if (buffer?.document?.id === initial.id && typeof buffer.aliases === "string") { setDocument(buffer.document); setAliases(buffer.aliases); }
    } catch { setError("Буфер формы недоступен. Сверьте определение перед подтверждением."); }
    setReady(true);
  }, [key, initial.id]);
  useEffect(() => {
    if (!ready) return;
    try { sessionStorage.setItem(key, JSON.stringify({ document, aliases })); }
    catch { setError("Не удалось сохранить буфер формы в браузере."); }
  }, [ready, key, document, aliases]);
  async function prepare() {
    if (busy) return;
    setBusy(true); setError("");
    try {
      const result = await swimPost<SwimExercisePreviewResponse>("/api/swim-exercises/preview", { document: { ...document, aliases: aliases.split("\n").filter(alias => alias.trim()) } });
      setPreview(result); setConfirmation({ document: result.document, fingerprint: result.fingerprint, base_revision: baseRevision, request_id: crypto.randomUUID(), confirm: true });
    } catch (cause) { setError(swimError(cause)); }
    finally { setBusy(false); }
  }
  async function confirm() {
    if (!confirmation || busy) return;
    setBusy(true); setError("");
    try {
      const version = await swimPost<SwimExerciseVersionResponse>("/api/swim-exercises/confirm", confirmation);
      try { sessionStorage.removeItem(key); } catch { /* Saved version remains server-owned. */ }
      onSaved(version);
    } catch (cause) { setError(`${swimError(cause)} Повтор подтверждает этот же предпросмотр.`); }
    finally { setBusy(false); }
  }
  if (preview) return <section className={`${panel} space-y-4`} aria-label="Предпросмотр упражнения">
    <h2 className="text-lg font-semibold text-ink">Проверьте определение упражнения</h2>
    <ExerciseDefinition document={preview.document} />
    <p className="text-sm text-ink-soft">Определение не содержит дозировку. Уже сохранённые программы сохранят свои версии техники.</p>
    <div className="flex flex-wrap gap-2"><button type="button" className={primary} disabled={busy} onClick={() => void confirm()}>Подтвердить сохранение упражнения</button><button type="button" className={button} disabled={busy} onClick={() => { setPreview(null); setConfirmation(null); }}>Вернуться к определению</button></div>
    {error ? <p role="alert" className="text-sm text-tone-warning">{error}</p> : null}
  </section>;
  return <section className={panel} aria-label="Определение упражнения"><form className="space-y-4" onSubmit={event => { event.preventDefault(); void prepare(); }}>
    <h2 className="text-lg font-semibold text-ink">{baseRevision ? "Новая версия упражнения" : "Новое упражнение"}</h2>
    <fieldset disabled={busy || !ready} className="min-w-0 space-y-3">
      <TextField label="Название упражнения" required value={document.name} onChange={name => setDocument({ ...document, name })} />
      <TextField label="Вариант" required value={document.variant} onChange={variant => setDocument({ ...document, variant })} />
      <TextField label="Другие названия — по одному в строке" multiline value={aliases} onChange={setAliases} />
      <TextField label="Инструкция техники" required multiline value={document.instructions} onChange={instructions => setDocument({ ...document, instructions })} />
      <Choice label="Стиль техники" value={document.stroke} options={[["unspecified", "Не указан"], ["drill", "Упражнение"], ["freestyle", "Кроль"], ["backstroke", "На спине"], ["breaststroke", "Брасс"], ["butterfly", "Баттерфляй"], ["mixed", "Смешанный"]]} onChange={stroke => setDocument({ ...document, stroke })} />
      <fieldset><legend className="text-sm text-ink">Где выполняется</legend><div className="mt-1 flex flex-wrap gap-x-4">{([["pool", "Бассейн"], ["open_water", "Открытая вода"]] as const).map(([value, label]) => <label key={value} className="flex min-h-8 items-center gap-2 text-sm text-ink"><input type="checkbox" checked={document.environments.includes(value)} onChange={event => setDocument({ ...document, environments: event.target.checked ? [...document.environments, value] : document.environments.filter(item => item !== value) })} />{label}</label>)}</div></fieldset>
      <fieldset><legend className="text-sm text-ink">Снаряжение варианта</legend><div className="mt-1 flex flex-wrap gap-x-4">{([["fins", "Ласты"], ["pull_buoy", "Колобашка"], ["kickboard", "Доска"], ["paddles", "Лопатки"], ["snorkel", "Трубка"], ["other", "Другое"]] as const).map(([value, label]) => <label key={value} className="flex min-h-8 items-center gap-2 text-sm text-ink"><input type="checkbox" checked={document.equipment.includes(value)} onChange={event => setDocument({ ...document, equipment: event.target.checked ? [...document.equipment, value] : document.equipment.filter(item => item !== value) })} />{label}</label>)}</div></fieldset>
      <TextField label="Название источника упражнения" value={document.source_label ?? ""} onChange={source_label => setDocument({ ...document, source_label: source_label || null })} />
      <TextField label="Исходный текст упражнения" multiline value={document.source_text ?? ""} onChange={source_text => setDocument({ ...document, source_text: source_text || null })} />
      {document.video_cues.map((cue, index) => <fieldset key={index} className="space-y-2 rounded-lg border border-surface-border p-3"><legend className="text-sm text-ink">Видео-фрагмент {index + 1}</legend><TextField label="Название видео" required value={cue.source_label} onChange={source_label => setDocument({ ...document, video_cues: document.video_cues.map((item, at) => at === index ? { ...item, source_label } : item) })} /><div className="grid grid-cols-2 gap-2"><NumberField label="Начало, с" min={0} value={cue.start_seconds} onChange={start_seconds => setDocument({ ...document, video_cues: document.video_cues.map((item, at) => at === index ? { ...item, start_seconds: start_seconds ?? 0 } : item) })} /><NumberField label="Конец, с" value={cue.end_seconds} onChange={end_seconds => setDocument({ ...document, video_cues: document.video_cues.map((item, at) => at === index ? { ...item, end_seconds: end_seconds ?? 0 } : item) })} /></div><button type="button" className={button} onClick={() => setDocument({ ...document, video_cues: document.video_cues.filter((_, at) => at !== index) })}>Убрать видео-фрагмент</button></fieldset>)}
      <button type="button" className={button} onClick={() => setDocument({ ...document, video_cues: [...document.video_cues, { source_label: "", start_seconds: 0, end_seconds: 0 }] })}>Добавить видео-фрагмент</button>
      <div className="flex flex-wrap gap-2"><button type="submit" className={primary}>Предпросмотр упражнения</button><button type="button" className={button} onClick={onClose}>Закрыть определение</button></div>
    </fieldset>
    {error ? <p role="alert" className="text-sm text-tone-warning">{error}</p> : null}
  </form></section>;
}
