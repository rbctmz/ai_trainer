"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, isDemo } from "@/lib/api";
import { streamSwimCoach, swimError } from "@/lib/swim-api";
import type { SwimCoachEvent, SwimImportDraftResponse } from "@/lib/types";
import { button, input, panel, primary } from "./styles";

type Line = { role: "user" | "assistant"; text: string };

export function SwimDialogue({ draft, busy, onStart, onFinish }: {
  draft: SwimImportDraftResponse; busy: boolean; onStart: () => void;
  onFinish: () => Promise<void>;
}) {
  const [message, setMessage] = useState("");
  const [chatId, setChatId] = useState<string | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState("");
  const [ready, setReady] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const bufferKey = `swim-dialogue-${isDemo() ? "demo" : "real"}-${draft.import_id}`;
  useEffect(() => {
    try {
      const buffer = JSON.parse(sessionStorage.getItem(bufferKey) || "null");
      if (buffer && typeof buffer.message === "string") setMessage(buffer.message);
      if (buffer && typeof buffer.chatId === "string") setChatId(buffer.chatId);
      // A browser transcript is only reading context, never a draft/save receipt.
      if (buffer && Array.isArray(buffer.lines)) setLines(buffer.lines.filter((line: Line) =>
        (line.role === "user" || line.role === "assistant") && typeof line.text === "string"));
    } catch { setError("Буфер диалога недоступен. Актуальная структура читается с сервера."); }
    setReady(true);
    return () => controller.current?.abort();
  }, [bufferKey]);
  useEffect(() => {
    if (!ready) return;
    try { sessionStorage.setItem(bufferKey, JSON.stringify({ message, chatId, lines })); }
    catch { /* The server still retains source and draft. */ }
  }, [ready, bufferKey, message, chatId, lines]);

  async function send(text: string) {
    if (busy || !ready || !text.trim()) return;
    onStart();
    setError("");
    setProgress("Коуч работает с исходником и текущим черновиком…");
    setLines(previous => [...previous, { role: "user", text }]);
    const abort = new AbortController();
    controller.current = abort;
    let answer = "";
    let failure: string | null = null;
    let unavailable = false;
    try {
      await streamSwimCoach({ message: text, import_id: draft.import_id,
        expected_revision: draft.revision, request_id: crypto.randomUUID(), chat_id: chatId,
      }, (event: SwimCoachEvent) => {
        if (event.type === "meta") setChatId(event.chat_id);
        if (event.type === "tool_call") setProgress(`${event.name}: ${event.status === "done" ? "выполнено" : "не выполнено"}`);
        if (event.type === "token") answer += event.content;
        if (event.type === "swim_import") {
          failure = event.status === "error" ? event.code || "swim_coach_tool_failed" : null;
          unavailable = event.readback_status === "unavailable";
        }
      }, abort.signal);
      if (answer) setLines(previous => [...previous, { role: "assistant", text: answer }]);
      if (failure) setError(swimError(new ApiError(422, "swim turn", failure)));
      if (unavailable) setError("В ответе Коуча нет актуального чтения результата. Продолжайте после обновления черновика с сервера.");
      // No automatic resend on ambiguous transport outcome; read the real draft.
      setMessage("");
    } catch (cause) {
      if (!abort.signal.aborted) setError(swimError(cause));
    } finally {
      if (!abort.signal.aborted) {
        setProgress("");
        await onFinish();
      }
      controller.current = null;
    }
  }

  return <section className={panel} aria-label="Диалог о программе">
    <h2 className="text-lg font-semibold text-ink">Разобрать с Коучем</h2>
    <p className="mt-1 text-sm text-ink-soft">Коуч уточняет и меняет черновик. Сохранение программы подтверждаете вы после предпросмотра.</p>
    {!draft.document ? <button type="button" disabled={!ready || busy} className={`${primary} mt-3`} onClick={() => void send("Разбери весь сохранённый исходник тренера. Неясные места оставь вопросами; сохрани все тренировки и серии.")}>Разобрать с Коучем</button> : null}
    {lines.length ? <div className="mt-4 space-y-3" aria-label="История разбора">{lines.map((line, index) => <div key={index} className="min-w-0 rounded-lg bg-surface-muted p-3"><p className="text-sm font-medium text-ink">{line.role === "user" ? "Вы" : "Коуч"}</p><p className="mt-1 whitespace-pre-wrap break-words text-sm text-ink-soft">{line.text}</p></div>)}</div> : null}
    {progress ? <p role="status" className="mt-3 text-sm text-ink-soft">{progress}</p> : null}
    {error ? <p role="alert" className="mt-3 text-sm border-l-2 border-tone-warning pl-3 text-ink">{error}</p> : null}
    <form className="mt-4 space-y-2" onSubmit={event => { event.preventDefault(); void send(message); }}>
      <label htmlFor="swim-coach-message" className="block text-sm text-ink">Запрос Коучу</label>
      <textarea id="swim-coach-message" className={`${input} min-h-24`} disabled={!ready || busy} value={message} onChange={event => setMessage(event.target.value)} placeholder="Уточните задание или опишите одну правку" />
      <button type="submit" disabled={!ready || busy || !message.trim()} className={button}>Отправить Коучу</button>
    </form>
    {lines.length ? <button type="button" className={`${button} mt-2`} disabled={busy} onClick={() => { setLines([]); setMessage(""); setChatId(null); }}>Очистить буфер диалога</button> : null}
  </section>;
}
