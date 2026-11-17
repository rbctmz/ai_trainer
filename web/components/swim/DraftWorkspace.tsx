"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, fetcher, isDemo } from "@/lib/api";
import { swimError, swimPost } from "@/lib/swim-api";
import type { SwimImportDraftResponse, SwimImportPreviewResponse, SwimProgramAnyVersionResponse } from "@/lib/types";
import { ProgramStructure, ProgramSummary } from "./ProgramStructure";
import { SourceView } from "./SourceView";
import { SwimDialogue } from "./SwimDialogue";
import { ManualStructure } from "./ManualStructure";
import { DraftEditor } from "./DraftEditor";
import type { EditTarget } from "./DraftEditor";
import { SourceCoverage } from "./SourceCoverage";
import { ResponsiveDisclosure } from "./ResponsiveDisclosure";
import { button, panel, primary } from "./styles";

export function DraftWorkspace({ draft, reload, onSaved, readError = false }: {
  draft: SwimImportDraftResponse; reload: () => Promise<void>;
  onSaved: (version: SwimProgramAnyVersionResponse) => void;
  readError?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [readPending, setNeedsRead] = useState(false);
  const needsRead = readPending || readError;
  const [preview, setPreview] = useState<SwimImportPreviewResponse | null>(null);
  const [ambiguous, setAmbiguous] = useState(false);
  const [editing, setEditing] = useState<EditTarget | null>(null);
  const [manualOpen, setManualOpen] = useState(false);
  const [editorReady, setEditorReady] = useState(false);
  const editTrigger = useRef<HTMLElement | null>(null);
  const editKey = `swim-editor-target-${isDemo() ? "demo" : "real"}-${draft.import_id}`;
  useEffect(() => {
    try {
      const target = JSON.parse(sessionStorage.getItem(editKey) || "null");
      if (target && (["node", "add", "workout"].includes(target.kind) && typeof target.id === "string" || target.kind === "title")) setEditing(target);
    } catch { /* A missing browser buffer does not alter the server draft. */ }
    setEditorReady(true);
  }, [editKey]);
  useEffect(() => {
    if (!editorReady) return;
    try { if (editing) sessionStorage.setItem(editKey, JSON.stringify(editing)); else sessionStorage.removeItem(editKey); }
    catch { setError("Буфер правки недоступен. Не закрывайте страницу с незаписанными изменениями."); }
  }, [editing, editorReady, editKey]);
  useEffect(() => { setPreview(null); setAmbiguous(false); }, [draft.revision]);
  function edit(target: EditTarget) {
    if (busy || needsRead || editing !== null) return;
    editTrigger.current = document.activeElement as HTMLElement | null;
    setEditing(target); setPreview(null);
  }
  function closeEditor() { setEditing(null); requestAnimationFrame(() => editTrigger.current?.focus()); }

  async function refresh() {
    try { await reload(); setNeedsRead(false); setError(""); }
    catch { setNeedsRead(true); setError("Не удалось прочитать актуальный черновик. Повторите чтение перед продолжением."); }
  }
  async function prepare() {
    if (busy || needsRead) return;
    setBusy(true); setError(""); setPreview(null); setAmbiguous(false);
    try {
      // api-contract: exclude selected private UUID/CAS; populated HTTP and whole browser confirmation cover this path.
      const current = await fetcher<SwimImportDraftResponse>(`/api/swim-imports/${encodeURIComponent(draft.import_id)}`);
      if (current.revision !== draft.revision) { await refresh(); throw new ApiError(409, "draft changed", "swim_import_stale"); }
      let base = 0;
      try {
        // api-contract: exclude selected private UUID; only explicit404 means no existing library version.
        base = (await fetcher<SwimProgramAnyVersionResponse>(`/api/swim-programs/${encodeURIComponent(draft.program_id)}`)).revision;
      } catch (cause) { if (!(cause instanceof ApiError && cause.status === 404)) throw cause; }
      setPreview(await swimPost<SwimImportPreviewResponse>(`/api/swim-imports/${encodeURIComponent(draft.import_id)}/preview`, {
        draft_revision: draft.revision, base_library_revision: base, request_id: crypto.randomUUID(),
      }));
    } catch (cause) { setError(swimError(cause)); }
    finally { setBusy(false); }
  }
  async function confirm() {
    if (!preview || busy || needsRead) return;
    setBusy(true); setError("");
    try {
      const version = await swimPost<SwimProgramAnyVersionResponse>("/api/swim-programs/confirm", { preview_id: preview.preview_id, confirm: true });
      onSaved(version);
    } catch (cause) {
      setAmbiguous(true);
      setError(`${swimError(cause)} Результат сохранения проверьте в библиотеке или повторите подтверждение этого же предпросмотра.`);
    } finally { setBusy(false); }
  }
  return <>
    <section className={panel} aria-label="Программа тренера">
      <h2 className="break-words text-xl font-semibold text-ink">{draft.document?.title || draft.source_week_label || draft.source_label || "Исходник тренера"}</h2>
      <p role="status" className="mt-1 text-sm text-ink-soft">Источник сохранён · {draft.document ? "Черновик программы" : "Структура ещё не разобрана"}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className={primary} disabled={!editorReady || busy || needsRead || !draft.document || preview !== null || editing !== null || manualOpen} onClick={() => void prepare()}>Подготовить предпросмотр</button>
        <button type="button" className={button} disabled={busy} onClick={() => void refresh()}>Обновить черновик</button>
        {draft.document ? <button type="button" className={button} disabled={busy || needsRead || preview !== null || editing !== null} onClick={() => edit({ kind: "title" })}>Изменить название программы</button> : null}
      </div>
      {busy ? <p role="status" className="mt-3 text-sm text-ink-soft">Ожидаем подтверждение сервера…</p> : null}
      {error ? <p role="alert" className="mt-3 text-sm border-l-2 border-tone-warning pl-3 text-ink">{error}</p> : null}
    </section>
    {!preview && draft.document && draft.summary ? <ProgramSummary document={draft.document} summary={draft.summary} /> : null}
    {!draft.document ? <ManualStructure draft={draft} busy={busy || needsRead} onStart={() => { setBusy(true); setError(""); }} onWritten={refresh} onEnd={() => setBusy(false)} onOpenChange={setManualOpen} /> : null}
    {editing && draft.document ? <DraftEditor key={JSON.stringify(editing)} draft={draft} target={editing} busy={busy || needsRead} onStart={() => { setBusy(true); setPreview(null); setError(""); }} onWritten={refresh} onEnd={() => setBusy(false)} onClose={closeEditor} /> : null}
    {preview && preview.draft_revision === draft.revision ? <section className={`${panel} space-y-4`} aria-label="Предпросмотр сохранения">
      <div><h2 className="text-xl font-semibold text-ink">Проверьте всю программу</h2><p className="mt-2 text-sm text-ink-soft">Будет сохранена эта версия всех тренировок. Предпросмотр действителен до {new Date(preview.expires_at).toLocaleString("ru-RU")}.</p></div>
      <ProgramSummary document={preview.document} summary={preview.summary} />
      <ResponsiveDisclosure title="Сравнить с исходником"><SourceView text={preview.document.source_text} /></ResponsiveDisclosure>
      <ProgramStructure document={preview.document} summary={preview.summary} showSummary={false} />
      <div className="flex flex-wrap gap-2"><button type="button" className={primary} disabled={busy || needsRead} onClick={() => void confirm()}>{ambiguous ? "Повторить подтверждение" : "Подтвердить сохранение программы"}</button><button type="button" className={button} disabled={busy} onClick={() => { setPreview(null); setAmbiguous(false); }}>{ambiguous ? "Вернуться к черновику" : "Вернуться к правкам"}</button></div>
    </section> : <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
      <ResponsiveDisclosure title="Исходник и диалог с Коучем" initiallyOpen={!draft.document}><SourceView text={draft.source_text} /><SwimDialogue draft={draft} busy={busy || needsRead || editing !== null || manualOpen} onStart={() => { setBusy(true); setPreview(null); setError(""); }} onFinish={async () => { await refresh(); setBusy(false); }} /></ResponsiveDisclosure>
      <div className="min-w-0 space-y-4">{draft.document && draft.summary ? <><ProgramStructure document={draft.document} summary={draft.summary} showSummary={false} editingDisabled={busy || needsRead || editing !== null} onEditNode={id => edit({ kind: "node", id })} onAddNode={id => edit({ kind: "add", id })} onEditWorkout={id => edit({ kind: "workout", id })} /><SourceCoverage draft={draft} busy={busy || needsRead || editing !== null} onStart={() => { setBusy(true); setPreview(null); setError(""); }} onWritten={refresh} onEnd={() => setBusy(false)} /></> : <div className={panel}><h2 className="text-lg font-semibold text-ink">Структура программы</h2><p className="mt-2 text-sm text-ink-soft">Разберите исходник с Коучем или задайте структуру вручную. Все тренировки будут в одном черновике.</p></div>}</div>
    </div>}
  </>;
}
