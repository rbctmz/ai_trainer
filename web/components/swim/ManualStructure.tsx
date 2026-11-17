"use client";

import { useEffect, useState } from "react";
import { isDemo } from "@/lib/api";
import { swimError, swimPost } from "@/lib/swim-api";
import type { SwimImportDraftResponse, SwimImportParseRequest } from "@/lib/types";
import { ContextFields, LocalSteps, SpanPicker, TextField } from "./EditorFields";
import { button, panel, primary } from "./styles";

type Staging = { request: SwimImportParseRequest; open: boolean };

export function ManualStructure({ draft, busy, onStart, onWritten, onEnd, onOpenChange }: {
  draft: SwimImportDraftResponse; busy: boolean; onStart: () => void;
  onWritten: () => Promise<void>; onEnd: () => void;
  onOpenChange: (open: boolean) => void;
}) {
  const key = `swim-manual-${isDemo() ? "demo" : "real"}-${draft.import_id}`;
  const [staging, setStaging] = useState<Staging | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    try {
      const raw = JSON.parse(sessionStorage.getItem(key) || "null");
      if (raw?.request?.content && Array.isArray(raw.request.content.workouts)) setStaging(raw);
    } catch { setError("Буфер ручной формы недоступен. Исходник сохранён на сервере."); }
    setReady(true);
  }, [key]);
  useEffect(() => {
    if (!ready || !staging) return;
    try { sessionStorage.setItem(key, JSON.stringify(staging)); }
    catch { setError("Браузер не смог сохранить буфер формы. Запишите готовую структуру перед закрытием страницы."); }
  }, [key, staging, ready]);
  useEffect(() => { onOpenChange(!!staging?.open); }, [staging?.open, onOpenChange]);
  if (draft.document) return null;
  const content = staging?.request.content;
  const change = (next: SwimImportParseRequest["content"]) => setStaging({ open: true, request: { expected_revision: draft.revision, request_id: crypto.randomUUID(), content: next } });
  async function submit() {
    if (!staging || busy) return;
    onStart(); setError("");
    try {
      await swimPost<SwimImportDraftResponse>(`/api/swim-imports/${encodeURIComponent(draft.import_id)}/parse`, staging.request);
      try { sessionStorage.removeItem(key); } catch { /* No canonical data is lost. */ }
      setStaging(null);
      await onWritten();
    } catch (cause) { setError(swimError(cause)); }
    finally { onEnd(); }
  }
  return <section className={staging?.open ? panel : ""} aria-label="Ручная структура">
    {!staging?.open ? <button type="button" className={button} disabled={!ready || busy} onClick={() => setStaging(staging ? { ...staging, open: true } : { open: true, request: { request_id: crypto.randomUUID(), expected_revision: draft.revision, content: { title: "", source_spans: [], workouts: [], exercise_references: [] } } })}>{content ? "Продолжить ручную структуру" : "Создать структуру вручную"}</button> : content ? <form className="space-y-4" onSubmit={event => { event.preventDefault(); void submit(); }}>
      <h2 className="text-lg font-semibold text-ink">Структура без AI</h2>
      <p className="text-sm text-ink-soft">Заполните все тренировки и серии. Свяжите их с исходником; незаданные величины оставляйте незаданными. До записи это восстанавливаемый буфер формы.</p>
      <fieldset className="min-w-0 space-y-4" disabled={busy}>
        <TextField label="Название программы" required value={content.title} onChange={title => change({ ...content, title })} />
        <SpanPicker text={draft.source_text} spans={content.source_spans ?? []} onChange={source_spans => change({ ...content, source_spans })} whole />
        {content.workouts.map((workout, index) => {
          const update = (changed: typeof workout) => change({ ...content, workouts: content.workouts.map((item, at) => at === index ? changed : item) });
          return <article className="min-w-0 space-y-3 rounded-lg border border-surface-border p-3" aria-label={`Ручная тренировка ${index + 1}`} key={workout.id}>
            <h3 className="font-semibold text-ink">Тренировка {index + 1}</h3>
            <TextField label="Название тренировки" required value={workout.title} onChange={title => update({ ...workout, title })} />
            <ContextFields workout={workout} onChange={update} />
            <SpanPicker text={draft.source_text} spans={workout.source_spans ?? []} onChange={source_spans => update({ ...workout, source_spans })} />
            <LocalSteps source={draft.source_text} nodes={workout.steps} onChange={steps => update({ ...workout, steps })} />
            <button type="button" className={button} onClick={() => change({ ...content, workouts: content.workouts.filter((_, at) => at !== index) })}>Убрать тренировку {index + 1} из формы</button>
          </article>;
        })}
        <button type="button" className={button} onClick={() => change({ ...content, workouts: [...content.workouts, { id: crypto.randomUUID(), title: "", environment: "pool", pool_length_meters: null, source_spans: [], steps: [] }] })}>Добавить тренировку</button>
        <p className="text-sm text-ink-soft">Диапазоны вводятся обеими границами. В серии с указанным последним отдыхом он должен быть отдельным последним шагом.</p>
        <div className="flex flex-wrap gap-2"><button type="submit" className={primary} disabled={!content.workouts.length}>Записать структуру черновика</button><button type="button" className={button} onClick={() => setStaging({ ...staging, open: false })}>Свернуть форму</button></div>
      </fieldset>
    </form> : null}
    {error ? <p role="alert" className="mt-3 text-sm text-tone-warning">{error}</p> : null}
  </section>;
}
