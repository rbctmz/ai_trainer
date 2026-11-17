"use client";

import { useEffect, useState } from "react";
import { isDemo } from "@/lib/api";
import { swimError, swimPost } from "@/lib/swim-api";
import type { SwimImportCaptureRequest, SwimImportDraftResponse } from "@/lib/types";
import { button, input, panel, primary } from "./styles";

interface Buffer extends SwimImportCaptureRequest { source_label: string; source_week_label: string }

export function SourceCapture({ onCaptured }: { onCaptured: (draft: SwimImportDraftResponse) => void }) {
  const [value, setValue] = useState<Buffer>({ source_text: "", source_label: "", source_week_label: "", request_id: "" });
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [bufferError, setBufferError] = useState("");
  const key = `swim-source-input-${isDemo() ? "demo" : "real"}`;
  useEffect(() => {
    try {
      const saved = sessionStorage.getItem(key);
      if (saved) {
        const parsed = JSON.parse(saved) as Buffer;
        if (typeof parsed.source_text !== "string" || typeof parsed.request_id !== "string") throw new Error("invalid buffer");
        setValue({ source_text: parsed.source_text, request_id: parsed.request_id, source_label: parsed.source_label || "", source_week_label: parsed.source_week_label || "" });
      }
    } catch { setBufferError("Не удалось прочитать локальный черновик ввода. Сохранённые источники доступны в списке."); }
    setReady(true);
  }, [key]);

  function change(field: "source_text" | "source_label" | "source_week_label", text: string) {
    const next = { ...value, [field]: text, request_id: crypto.randomUUID() };
    setValue(next);
    try { sessionStorage.setItem(key, JSON.stringify(next)); setBufferError(""); }
    catch { setBufferError("Браузер не сохранил ввод для перезагрузки. Сохраните исходник на сервере."); }
  }

  async function capture(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError("");
    const payload = { ...value, request_id: value.request_id || crypto.randomUUID(), source_label: value.source_label || null, source_week_label: value.source_week_label || null };
    try {
      const result = await swimPost<SwimImportDraftResponse>("/api/swim-imports", payload);
      try { sessionStorage.removeItem(key); } catch { /* Server owns the captured source. */ }
      onCaptured(result);
    } catch (failure) { setError(swimError(failure)); }
    finally { setBusy(false); }
  }

  return <form onSubmit={capture} className={panel} aria-label="Новый исходник">
    <h2 className="text-lg font-semibold text-ink">Сообщение тренера</h2>
    <p className="mt-1 text-sm text-ink-soft">Сначала сохраните текст целиком. Затем его можно разобрать с Коучем или вручную.</p>
    <fieldset disabled={!ready || busy} className="mt-4 space-y-3">
      <div><label htmlFor="swim-source-input" className="block text-sm text-ink">Текст тренера</label><textarea id="swim-source-input" className={`${input} mt-1 min-h-52`} value={value.source_text} onChange={event => change("source_text", event.target.value)} required /></div>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm text-ink">Название источника<input className={`${input} mt-1`} value={value.source_label} onChange={event => change("source_label", event.target.value)} maxLength={200} /></label>
        <label className="text-sm text-ink">Обозначение недели<input className={`${input} mt-1`} value={value.source_week_label} onChange={event => change("source_week_label", event.target.value)} maxLength={200} /></label>
      </div>
      {bufferError ? <p role="status" className="text-sm text-tone-warning">{bufferError}</p> : null}
      {error ? <p role="alert" className="text-sm text-tone-warning">{error}</p> : null}
      <button className={primary} type="submit" disabled={!value.source_text.trim()}>{busy ? "Сохраняем…" : "Сохранить исходник"}</button>
      <button className={`${button} ml-2`} type="button" onClick={() => change("source_text", "")}>Очистить ввод</button>
    </fieldset>
  </form>;
}
