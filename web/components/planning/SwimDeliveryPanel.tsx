"use client";

import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { button, primary } from "@/components/swim/styles";
import { ApiError, fetcher, isDemo, postJSON } from "@/lib/api";
import type {
  SwimCalendarRow, SwimDeliveryConfirmed, SwimDeliveryPreview, SwimDeliveryRead, SwimDeliveryReceipt,
  SwimDeliveryStep,
} from "@/lib/types";

function errorMessage(error: unknown): string {
  return error instanceof ApiError && error.code
    ? error.message
    : "Ответ не получен. Можно повторить то же подтверждение и проверить квитанцию.";
}

function range(bounds: number[]): string {
  return bounds[0] === bounds[1] ? String(bounds[0]) : bounds.join("–");
}

function stepLabel(step: SwimDeliveryStep): string {
  if (step.clock === "distance") return `${step.distance_meters} м`;
  if (step.clock === "time") return `Отдых ${step.duration_seconds} с`;
  if (step.source_rest_breaths) return `Отдых по Lap · выдохи ${range(step.source_rest_breaths)}`;
  if (step.source_rest_seconds) return `Отдых по Lap · ориентир ${range(step.source_rest_seconds)} с`;
  return "Отдых по Lap";
}

function Receipt({ receipt }: { receipt: SwimDeliveryReceipt }) {
  if (receipt.status === "provider_verified") {
    return <div role="status" className="space-y-1 text-sm text-ink">
      <p className="font-medium">Тренировка сверена в Intervals.icu</p>
      <p>Дата отправки в календаре — {receipt.target_date}. Проверьте получение и шаги на Garmin FR255.</p>
    </div>;
  }
  let detail = "Intervals.icu ещё не подтвердил состояние события.";
  if (receipt.reason === "step_mismatch") detail = `Шаг ${receipt.step_number} отличается от предпросмотра.`;
  if (receipt.reason === "total_distance") detail = "Общая дистанция отличается от предпросмотра.";
  if (receipt.reason === "pool_length") detail = "Длина бассейна отличается от предпросмотра.";
  if (receipt.reason === "step_count") detail = "Количество шагов отличается от предпросмотра.";
  if (receipt.reason === "provider_push_errors") detail = "Intervals.icu сообщил об ошибке передачи.";
  if (receipt.reason === "provider_identity_mismatch") detail = "Дата или идентичность события изменилась.";
  return <div role="status" className="space-y-1 text-sm text-ink">
    <p className="font-medium">Доставка не подтверждена</p>
    <p>{detail}</p>
  </div>;
}

export function SwimDeliveryPanel({ row, checkpointId, editable, onClose }: {
  row: SwimCalendarRow;
  checkpointId: number;
  editable: boolean;
  onClose: () => void;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const previewHeading = useRef<HTMLHeadingElement>(null);
  const requestId = useRef<string | null>(null);
  const { data, error, mutate } = useSWR<SwimDeliveryRead>(
    `/api/planning/swim-calendar/delivery?assignment_id=${encodeURIComponent(row.assignment_id)}`, fetcher,
  );
  const [preview, setPreview] = useState<SwimDeliveryPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const [ambiguous, setAmbiguous] = useState(false);
  const [backupWarning, setBackupWarning] = useState(false);
  const receipt = data?.receipt;
  const demo = isDemo();
  const stale = preview && preview.checkpoint_id !== checkpointId;

  useEffect(() => { heading.current?.focus(); }, []);
  useEffect(() => { if (preview) previewHeading.current?.focus(); }, [preview]);

  async function prepare() {
    if (!editable || busy || receipt) return;
    setBusy(true);
    setProblem("");
    requestId.current ??= crypto.randomUUID();
    try {
      const next = await postJSON<SwimDeliveryPreview>("/api/planning/swim-calendar/delivery/preview", {
        request_id: requestId.current, assignment_id: row.assignment_id, expected_checkpoint_id: checkpointId,
      });
      requestId.current = null;
      setPreview(next);
    } catch (error) {
      setProblem(errorMessage(error));
      if (error instanceof ApiError && error.status < 500) requestId.current = null;
      void mutate();
    } finally {
      setBusy(false);
    }
  }

  async function confirm(previewId: string, readbackOnly: boolean) {
    if (busy || demo) return;
    if (!readbackOnly && !ambiguous && (!editable || stale)) return;
    setBusy(true);
    setProblem("");
    try {
      const result = await postJSON<SwimDeliveryConfirmed>("/api/planning/swim-calendar/delivery/confirm", {
        preview_id: previewId, confirm: true,
      });
      await mutate({ receipt: result }, false);
      setPreview(null);
      setAmbiguous(false);
      setBackupWarning(result.backup.state === "degraded");
      requestAnimationFrame(() => heading.current?.focus());
    } catch (error) {
      setProblem(errorMessage(error));
      setAmbiguous(!(error instanceof ApiError) || error.status >= 500);
      void mutate();
    } finally {
      setBusy(false);
    }
  }

  return <section aria-label="Доставка на Garmin" className="mt-3 min-w-0 space-y-3 rounded-lg border border-surface-border bg-surface-muted p-3">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h3 ref={heading} tabIndex={-1} className="font-medium text-ink">Garmin FR255 через Intervals.icu</h3>
      <button className={button} type="button" disabled={busy} onClick={onClose}>Закрыть доставку</button>
    </div>
    {problem ? <p role="alert" className="border-l-2 border-tone-warning pl-2 text-sm text-ink">{problem}</p> : null}
    {backupWarning ? <p role="status" className="text-sm text-ink">Квитанция сохранена, резервная копия не обновилась.</p> : null}
    {receipt ? <>
      <Receipt receipt={receipt} />
      {receipt.status === "provider_unverified" && !demo ? <button className={button} type="button" disabled={busy}
        onClick={() => void confirm(receipt.preview_id, true)}>Сверить результат отправки</button> : null}
    </> : preview ? <>
      <h4 ref={previewHeading} tabIndex={-1} className="font-medium text-ink">Предпросмотр отправки</h4>
      <p className="text-sm text-ink">{preview.title} · {preview.target_date} · бассейн {preview.pool_length_meters} м · {preview.distance_meters} м · версия {preview.assignment.program_revision}</p>
      <p className="text-sm text-ink-soft">Шаги перечислены в порядке выполнения. Снаряжение и техника передаются текстом. Отображение на часах проверяется отдельно.</p>
      {preview.unspecified_last_rest_group_ids.length > 0 ? <p className="border-l-2 border-tone-warning pl-2 text-sm text-ink">
        Для части серий последний отдых отдельно не оговорён. В список включены все явно записанные паузы.
      </p> : null}
      <ol aria-label="Шаги для Intervals.icu" className="max-h-80 list-decimal space-y-2 overflow-y-auto rounded-md border border-surface-border py-2 pl-8 pr-3 text-sm">
        {preview.steps.map((step, index) => <li key={index} className="break-words text-ink">
          <span className="font-medium">{stepLabel(step)}</span>
          {step.rounds.length ? <span className="text-ink-soft"> · {step.rounds.map(item => `${item.name} ${item.number}/${item.total}`).join(" / ")}</span> : null}
          <p className="text-ink-soft">{step.cue}</p>
        </li>)}
      </ol>
      {stale && !ambiguous ? <p role="alert" className="text-sm text-ink">Календарь изменился. Сформируйте свежий предпросмотр.</p> : null}
      {demo ? <p className="text-sm text-ink-soft">В учебном режиме доступен предпросмотр.</p> : null}
      <div className="flex flex-wrap gap-2">
        {!demo ? <button className={primary} type="button" disabled={busy || (!ambiguous && (!editable || !!stale))}
          onClick={() => void confirm(preview.preview_id, false)}>
          {busy ? "Сверяем доставку…" : ambiguous ? "Повторить подтверждение отправки" : "Подтвердить отправку в Intervals.icu"}
        </button> : null}
        <button className={button} type="button" disabled={busy} onClick={() => {
          setPreview(null); setAmbiguous(false); setProblem("");
          requestAnimationFrame(() => heading.current?.focus());
        }}>Закрыть предпросмотр</button>
      </div>
    </> : error ? <>
      <p role="alert" className="text-sm text-ink">Не удалось прочитать квитанцию отправки.</p>
      <button type="button" className={button} onClick={() => void mutate()}>Повторить чтение</button>
    </> : data ? <button type="button" className={primary} disabled={!editable || busy} onClick={() => void prepare()}>
      {busy ? "Готовим шаги…" : "Проверить отправку"}
    </button> : <p role="status" className="text-sm text-ink-soft">Читаем состояние доставки…</p>}
  </section>;
}
