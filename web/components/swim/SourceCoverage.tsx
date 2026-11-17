"use client";

import { useRef, useState } from "react";
import { swimError, swimPost } from "@/lib/swim-api";
import type { SwimImportDraftResponse, SwimImportPatchRequest, SwimSourceSpan } from "@/lib/types";
import { TextField } from "./EditorFields";
import { button, panel, primary } from "./styles";

export function SourceCoverage({ draft, busy, onStart, onWritten, onEnd }: {
  draft: SwimImportDraftResponse; busy: boolean; onStart: () => void;
  onWritten: () => Promise<void>; onEnd: () => void;
}) {
  const [selected, setSelected] = useState<SwimSourceSpan | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const command = useRef<{ key: string; request: SwimImportPatchRequest } | null>(null);
  const source = Array.from(draft.source_text);
  async function acknowledge() {
    if (!selected || !reason.trim() || busy) return;
    const key = JSON.stringify({ revision: draft.revision, selected, reason });
    if (command.current?.key !== key) command.current = { key, request: {
      expected_revision: draft.revision, request_id: crypto.randomUUID(),
      operation: { op: "acknowledge_source", span: selected, reason },
    } };
    onStart(); setError("");
    try {
      await swimPost<SwimImportDraftResponse>(`/api/swim-imports/${encodeURIComponent(draft.import_id)}/patch`, command.current.request);
      await onWritten(); setSelected(null); setReason("");
    } catch (cause) { setError(swimError(cause)); }
    finally { onEnd(); }
  }
  return <>
    {draft.summary?.source_gaps.length ? <section className={panel} aria-label="Несопоставленные фрагменты">
      <h2 className="text-lg font-semibold text-ink">Что ещё нужно разобрать</h2>
      <p className="mt-2 text-sm text-ink-soft">Эти фрагменты сервер не нашёл в структуре. Добавьте их к шагу, уточните у Коуча или подтвердите, что это только пояснение. Подтверждённые пояснения остаются видимыми; готовность проверяет сервер при предпросмотре.</p>
      <ul className="mt-3 space-y-3">{draft.summary.source_gaps.map((span, index) => {
        // Display an exact retained receipt; do not derive merged coverage/readiness here.
        const acknowledged = draft.acknowledgements.find(ack => ack.span.start === span.start && ack.span.end === span.end);
        return <li className="rounded-lg bg-surface-muted p-3" key={`${span.start}/${span.end}`}>
        <blockquote className="whitespace-pre-wrap break-words text-sm text-ink">{source.slice(span.start, span.end).join("")}</blockquote>
        {acknowledged ? <p className="mt-2 text-sm text-ink">Подтверждено как пояснение: {acknowledged.reason}</p> : <button type="button" className={`${button} mt-2`} disabled={busy} onClick={() => { setSelected(span); setReason(""); }}>Это пояснение, а не задание</button>}
        {selected?.start === span.start && selected.end === span.end ? <form className="mt-3 space-y-2" aria-label={`Пояснение фрагмента ${index + 1}`} onSubmit={event => { event.preventDefault(); void acknowledge(); }}>
          <fieldset disabled={busy} className="space-y-2">
          <TextField label="Почему фрагмент не требует шага" value={reason} required multiline onChange={setReason} />
          <button type="submit" className={primary} disabled={busy || !reason.trim()}>Подтвердить пояснение</button>
          </fieldset>
        </form> : null}
      </li>; })}</ul>
      {error ? <p role="alert" className="mt-3 text-sm border-l-2 border-tone-warning pl-3 text-ink">{error}</p> : null}
    </section> : null}
    {draft.acknowledgements.length ? <details className={panel}><summary className="cursor-pointer text-sm text-ink focus:ring-2 focus:ring-accent">Подтверждённые пояснения ({draft.acknowledgements.length})</summary><ul className="mt-3 space-y-3">{draft.acknowledgements.map((ack, index) => <li key={index}><blockquote className="whitespace-pre-wrap break-words text-sm text-ink-soft">{source.slice(ack.span.start, ack.span.end).join("")}</blockquote><p className="mt-1 text-sm text-ink">{ack.reason}</p></li>)}</ul></details> : null}
  </>;
}
