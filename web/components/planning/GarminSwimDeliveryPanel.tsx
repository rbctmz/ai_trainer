"use client";

import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { button, primary } from "@/components/swim/styles";
import { ApiError, fetcher, postJSON } from "@/lib/api";
import type {
  GarminSwimConfirmed, GarminSwimLeaf, GarminSwimPreview, GarminSwimRead, SwimCalendarRow,
} from "@/lib/types";

const labels: Record<string, string> = {
  free: "кроль", backstroke: "на спине", mixed: "смешанный стиль", any_stroke: "любой стиль",
  drill: "упражнение", kick: "работа ногами", fins: "ласты", kickboard: "доска",
  paddles: "лопатки", pull_buoy: "колобашка",
};

function detail(step: GarminSwimLeaf) {
  if (step.type === "rest") return `Отдых ${step.duration_seconds} с`;
  const tags = [step.stroke, step.drill, step.equipment].filter((value): value is string => !!value);
  return [`${step.distance_meters} м`, ...new Set(tags.map(tag => labels[tag] ?? tag))].join(" · ");
}

function Leaf({ step }: { step: GarminSwimLeaf }) {
  return <li className="break-words"><span className="font-medium">{detail(step)}</span>
    {step.description ? <p className="whitespace-pre-line text-ink-soft">{step.description}</p> : null}
  </li>;
}

export function GarminSwimDeliveryPanel({ row, checkpointId, editable }: {
  row: SwimCalendarRow;
  checkpointId: number;
  editable: boolean;
}) {
  const { data, mutate } = useSWR<GarminSwimRead>(
    `/api/planning/swim-calendar/garmin-delivery?assignment_id=${encodeURIComponent(row.assignment_id)}`, fetcher,
  );
  const [preview, setPreview] = useState<GarminSwimPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const [possiblySent, setPossiblySent] = useState(false);
  const [backupWarning, setBackupWarning] = useState(false);
  const draftHeading = useRef<HTMLHeadingElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const pendingId = useRef<string | null>(null);
  const receipt = data?.receipt;
  const stale = !!preview && preview.checkpoint_id !== checkpointId;
  useEffect(() => { if (preview) draftHeading.current?.focus(); }, [preview]);

  async function prepare() {
    if (busy || !editable || !data?.enabled || receipt) return;
    setBusy(true);
    setProblem("");
    pendingId.current ??= crypto.randomUUID();
    try {
      const result = await postJSON<GarminSwimPreview>("/api/planning/swim-calendar/garmin-delivery/preview", {
        request_id: pendingId.current, assignment_id: row.assignment_id, expected_checkpoint_id: checkpointId,
      });
      setPreview(result);
      pendingId.current = null;
    } catch (error) {
      setProblem(error instanceof ApiError ? error.message : "Не удалось подготовить шаги Garmin.");
      if (error instanceof ApiError && error.status < 500) pendingId.current = null;
      void mutate();
    } finally {
      setBusy(false);
    }
  }

  async function confirm(previewId: string, readback: boolean) {
    if (busy || !data?.enabled || (!readback && !possiblySent && (!editable || stale))) return;
    setBusy(true);
    setProblem("");
    try {
      const result = await postJSON<GarminSwimConfirmed>("/api/planning/swim-calendar/garmin-delivery/confirm", {
        preview_id: previewId, confirm: true,
      });
      await mutate({ enabled: data.enabled, receipt: result }, false);
      setBackupWarning(result.backup.state === "degraded");
      setPreview(null);
      setPossiblySent(false);
      requestAnimationFrame(() => heading.current?.focus());
    } catch (error) {
      const unknown = !(error instanceof ApiError) || error.status >= 500;
      setPossiblySent(unknown);
      setProblem(unknown ? "Ответ потерян. Уточните результат этого подтверждения." : error.message);
      void mutate();
    } finally {
      setBusy(false);
    }
  }

  if (!data?.enabled && !receipt) return null;
  return <section aria-label="Прямая отправка в Garmin" className="space-y-2 border-t border-surface-border pt-3 text-sm">
    <h4 ref={heading} tabIndex={-1} className="font-medium text-ink">Garmin Connect напрямую</h4>
    {problem ? <p role="alert" className="text-ink">{problem}</p> : null}
    {backupWarning ? <p role="status">Квитанция сохранена, резервная копия не обновилась.</p> : null}
    {receipt ? <div role="status" className="space-y-1 text-ink">
      <p>{receipt.workout_verified ? "Тренировка сверена в Garmin Connect."
        : receipt.workout_id ? "Garmin создал тренировку, сверка шагов не подтверждена."
          : "Результат отправки в Garmin пока неизвестен."}</p>
      <p>{receipt.calendar_verified ? `Назначение в календаре Garmin сверено на ${receipt.target_date}.`
        : "Назначение в календаре Garmin не подтверждено."}</p>
      <p>Синхронизация с часами проверяется отдельно.</p>
      {receipt.workout_url ? <a className="underline" href={receipt.workout_url} target="_blank" rel="noreferrer">Открыть тренировку в Garmin</a> : null}
      {(receipt.status === "uncertain" || receipt.status === "workout_verified") ? <div><button type="button" className={button} disabled={busy || !data?.enabled}
        onClick={() => void confirm(receipt.preview_id, true)}>Сверить результат Garmin</button></div> : null}
    </div> : preview ? <>
      <h5 ref={draftHeading} tabIndex={-1} className="font-medium text-ink">Предпросмотр Garmin</h5>
      <p>{preview.name} · {preview.schedule_date} · бассейн {preview.pool_length_meters} м · {preview.distance_meters} м · версия {preview.assignment.program_revision}</p>
      {preview.fixed_rest_count ? <p>Пауз: {preview.fixed_rest_count} · всего {preview.fixed_rest_seconds} с</p> : null}
      <ol aria-label="Группы и шаги Garmin" className="max-h-80 list-decimal space-y-2 overflow-y-auto pl-5">
        {preview.steps.map((step, index) => step.type === "repeat"
          ? <li key={index}>
            <span className="font-medium">{step.repetitions} ×</span>
            {step.skip_last_rest ? <span className="text-ink-soft"> · последний отдых пропущен</span> : null}
            <ol className="list-decimal space-y-1 pl-6">{step.steps.map((child, i) => <Leaf key={i} step={child} />)}</ol>
          </li> : <Leaf key={index} step={step} />)}
      </ol>
      {stale && !possiblySent ? <p role="alert">Календарь изменился. Обновите предпросмотр Garmin.</p> : null}
      <div className="flex flex-wrap gap-2">
        <button type="button" className={primary} disabled={busy || (!possiblySent && (!editable || stale))}
          onClick={() => void confirm(preview.preview_id, false)}>
          {busy ? "Проверяем отправку…" : possiblySent ? "Уточнить результат Garmin" : "Подтвердить отправку в Garmin"}
        </button>
        <button type="button" className={button} disabled={busy} onClick={() => {
          setPreview(null); setProblem(""); setPossiblySent(false);
          requestAnimationFrame(() => heading.current?.focus());
        }}>Закрыть предпросмотр Garmin</button>
      </div>
    </> : <button type="button" className={primary} disabled={busy || !editable} onClick={() => void prepare()}>
      {busy ? "Готовим шаги…" : "Предпросмотр прямой отправки"}
    </button>}
  </section>;
}
