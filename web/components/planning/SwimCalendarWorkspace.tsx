"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { ApiError, fetcher, postJSON } from "@/lib/api";
import type {
  CycleContext, PlanningHistory, SwimCalendarOperation, SwimCalendarPreview, SwimCalendarRead,
  SwimCalendarReceipt, SwimCalendarRow, SwimProgramAnyVersionResponse, SwimProgramListResponse,
} from "@/lib/types";
import { button, input, panel, primary } from "@/components/swim/styles";
import { ProgramWorkoutSteps } from "@/components/swim/ProgramStructure";
import { AuthoredSwimRow } from "./AuthoredSwimRow";
import { SwimDeliveryPanel } from "./SwimDeliveryPanel";

type Edit = { kind: "move" | "substitute"; row: SwimCalendarRow };
type Pending = { expected_checkpoint_id: number; operation: SwimCalendarOperation; request_id: string };

function numericId(value: string | null): number | null {
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 && String(parsed) === value ? parsed : null;
}

function message(error: unknown) {
  return error instanceof ApiError && error.code
    ? error.message
    : "Не удалось получить ответ. Повторите действие или обновите календарь.";
}

export function SwimCalendarWorkspace() {
  const params = useSearchParams();
  const selected = numericId(params.get("checkpoint"));
  const program = params.get("program");
  const revision = numericId(params.get("revision"));
  return <Calendar key={params.toString()} selectedCheckpoint={selected} programId={program} revision={revision} />;
}

function Calendar({ selectedCheckpoint, programId, revision }: {
  selectedCheckpoint: number | null;
  programId: string | null;
  revision: number | null;
}) {
  const { mutate: refreshOther } = useSWRConfig();
  const { data, error, mutate } = useSWR<SwimCalendarRead>("/api/planning/swim-calendar", fetcher);
  const { data: cycle, error: cycleError, mutate: refreshCycle } = useSWR<CycleContext>("/api/planning/cycles/current", fetcher);
  // api-contract: exclude private selected checkpoint read; populated HTTP/browser acceptance covers this query.
  const historical = useSWR<SwimCalendarRead>(selectedCheckpoint ? `/api/planning/swim-calendar?checkpoint_id=${selectedCheckpoint}` : null, fetcher);
  const { data: history } = useSWR<PlanningHistory>("/api/planning/history", fetcher);
  const [edit, setEdit] = useState<Edit | null>(null);
  const [delivery, setDelivery] = useState<string | null>(null);
  const deliveryOrigin = useRef<HTMLButtonElement | null>(null);
  const [moveDate, setMoveDate] = useState("");
  const [rollback, setRollback] = useState("");
  const [preview, setPreview] = useState<SwimCalendarPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [problem, setProblem] = useState("");
  const [ambiguous, setAmbiguous] = useState(false);
  const pending = useRef<Pending | null>(null);
  const previewHeading = useRef<HTMLHeadingElement | null>(null);
  const origin = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (preview) previewHeading.current?.focus();
  }, [preview]);
  const current = !!data?.checkpoint_id && cycle?.checkpoint_id === data.checkpoint_id
    && cycle.cycle_id === data.cycle_id && cycle.is_selected
    && (cycle.state === "scheduled" || cycle.state === "in_progress")
    && !error && !cycleError;
  const editable = current && !busy && !preview && !selectedCheckpoint;

  async function propose(operation: SwimCalendarOperation) {
    const checkpoint = data?.checkpoint_id;
    if (!editable || !checkpoint) return;
    const previous = pending.current;
    const body = { expected_checkpoint_id: checkpoint, operation };
    const request = previous?.expected_checkpoint_id === checkpoint
      && JSON.stringify(previous.operation) === JSON.stringify(operation)
      ? previous : { ...body, request_id: crypto.randomUUID() };
    pending.current = request;
    origin.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setBusy(true);
    setProblem("");
    setNotice("");
    try {
      setPreview(await postJSON<SwimCalendarPreview>("/api/planning/swim-calendar/preview", request));
      pending.current = null;
    } catch (err) {
      setProblem(message(err));
      if (err instanceof ApiError && err.code === "cycle_stale") void Promise.allSettled([mutate(), refreshCycle()]);
    } finally {
      setBusy(false);
    }
  }

  async function apply() {
    if (!preview || busy) return;
    if (!ambiguous && (!current || preview.base_checkpoint_id !== data?.checkpoint_id)) return;
    setBusy(true);
    setProblem("");
    try {
      const receipt = await postJSON<SwimCalendarReceipt>("/api/planning/swim-calendar/confirm", {
        preview_id: preview.preview_id, confirm: true,
      });
      setPreview(null);
      setEdit(null);
      setAmbiguous(false);
      setNotice(`Календарь обновлён · версия плана ${receipt.checkpoint_id}`);
      await Promise.allSettled([
        mutate(), refreshCycle(), refreshOther("/api/planning/week-by-week"),
        refreshOther("/api/planning/status"), refreshOther("/api/planning/history"),
      ]);
    } catch (err) {
      const unknown = !(err instanceof ApiError) || err.status >= 500;
      setAmbiguous(unknown);
      setProblem(unknown ? "Результат сохранения неизвестен. Повторите подтверждение этого предпросмотра." : message(err));
      if (!unknown && err instanceof ApiError && err.code === "cycle_stale") void Promise.allSettled([mutate(), refreshCycle()]);
    } finally {
      setBusy(false);
    }
  }

  const shown = selectedCheckpoint ? historical.data : data;
  const rows = [...(shown?.assignments ?? [])].sort((a, b) => a.date.localeCompare(b.date));
  const versions = history?.items.filter(item => item.cycle_id === data?.cycle_id
    && item.checkpoint_id && item.checkpoint_id !== data?.checkpoint_id) ?? [];
  const min = cycle ? [cycle.athlete_day, cycle.start_date ?? ""].sort().at(-1) : undefined;
  return <main className="space-y-4">
    <h1 className="text-2xl font-bold text-ink">Календарь тренировок тренера</h1>
    <nav className="flex flex-wrap gap-3 text-sm text-ink">
      <Link href="/planning" className="underline">План</Link>
      <Link href="/coach/swim" className="underline">Библиотека программ</Link>
      {selectedCheckpoint ? <Link href="/planning/swim" className="underline">Текущий календарь</Link> : null}
    </nav>

    {(selectedCheckpoint ? historical.error : error || cycleError) ? <div className={panel} role="alert">
      Не удалось прочитать календарь.{" "}
      <button type="button" className={button} onClick={() => void Promise.allSettled([mutate(), refreshCycle(), historical.mutate()])}>Повторить чтение</button>
    </div> : null}
    {notice ? <p role="status" className="text-sm text-ink">{notice}</p> : null}
    {problem ? <p role="alert" className="border-l-2 border-tone-warning pl-3 text-sm text-ink">{problem}</p> : null}

    {programId && revision && !selectedCheckpoint ? <div hidden={!!preview}>
      <PlaceForm programId={programId} revision={revision}
        min={min} max={cycle?.end_date ?? undefined} disabled={!editable} onPropose={propose} />
    </div> : null}
    {preview ? <section className={panel} aria-label="Предпросмотр календаря">
      <h2 ref={previewHeading} tabIndex={-1} className="font-semibold text-ink focus:outline-none">Предпросмотр календаря</h2>
      <div className="mt-3 space-y-3">
        {preview.changes.map(({ before, after }) => <div key={(after ?? before)?.assignment_id}
          className="grid min-w-0 gap-3 rounded-lg border border-surface-border p-3 sm:grid-cols-2">
          <div><h3 className="mb-1 text-sm font-medium text-ink">Было</h3>
            {before ? <ReviewedWorkout row={before} /> : <p className="text-sm text-ink-soft">Без назначения</p>}</div>
          <div><h3 className="mb-1 text-sm font-medium text-ink">Станет</h3>
            {after ? <ReviewedWorkout row={after} /> : <p className="text-sm text-ink-soft">Без назначения</p>}</div>
        </div>)}
      </div>
      {preview.warnings.length ? <ul className="mt-3 list-inside space-y-1 border-l-2 border-tone-warning pl-3 text-sm text-ink">
        {preview.warnings.map(warning => <li key={`${warning.date}:${warning.code}`}>{warning.date} · {warning.code === "load_uncertain"
          ? "Общая нагрузка на день неизвестна." : "На этот день уже есть другие тренировки."}</li>)}
      </ul> : null}
      {!ambiguous && data?.checkpoint_id !== preview.base_checkpoint_id
        ? <p className="mt-3 text-sm text-ink-soft">Цикл изменился. Подготовьте свежий предпросмотр.</p> : null}
      <div className="mt-4 flex flex-wrap gap-2">
        <button type="button" className={primary} disabled={busy || (!ambiguous && (!current || data?.checkpoint_id !== preview.base_checkpoint_id))}
          onClick={() => void apply()}>{ambiguous ? "Повторить подтверждение" : "Подтвердить изменения календаря"}</button>
        <button type="button" className={button} disabled={busy} onClick={() => {
          setPreview(null); setProblem(""); setAmbiguous(false);
          requestAnimationFrame(() => origin.current?.focus());
        }}>
          {ambiguous ? "Вернуться к календарю" : "Вернуться к правкам"}
        </button>
      </div>
    </section> : null}

    <section className={panel} aria-label={selectedCheckpoint ? "Исторические назначения" : "Текущие назначения"}>
      <h2 className="font-semibold text-ink">{selectedCheckpoint ? `Назначения в версии плана ${selectedCheckpoint}` : "Назначенные тренировки"}</h2>
      {cycle && !current && !selectedCheckpoint && !error && !cycleError && data
        ? <p className="mt-2 text-sm text-ink-soft">Для назначения дат нужен открытый текущий цикл.</p> : null}
      {!shown && !(selectedCheckpoint ? historical.error : error)
        ? <p role="status" className="mt-2 text-sm text-ink-soft">Читаем назначения…</p>
        : shown && !rows.length ? <p className="mt-2 text-sm text-ink-soft">Назначений пока нет.</p> : null}
      <ul className="mt-3 space-y-3">
        {rows.map(row => <li key={row.assignment_id} className="rounded-lg border border-surface-border p-3">
          <AuthoredSwimRow row={row} showDate />
          {!selectedCheckpoint && row.date >= (cycle?.athlete_day ?? "") ? <div className="mt-2 flex flex-wrap gap-2">
            <button type="button" className={button} disabled={!editable} aria-label={`Перенести: ${row.title}`}
              onClick={() => { setEdit({ kind: "move", row }); setMoveDate(row.date); }}>Перенести</button>
            <button type="button" className={button} disabled={!editable} aria-label={`Заменить: ${row.title}`}
              onClick={() => setEdit({ kind: "substitute", row })}>Заменить</button>
            <button type="button" className={button} disabled={!editable} aria-label={`Убрать: ${row.title}`}
              onClick={() => void propose({ kind: "remove", assignment_id: row.assignment_id })}>Убрать</button>
            <button type="button" className={button} disabled={!editable} aria-label={`Доставка на Garmin: ${row.title}`}
              aria-expanded={delivery === row.assignment_id} onClick={event => {
                deliveryOrigin.current = event.currentTarget;
                setEdit(null);
                setDelivery(row.assignment_id);
              }}>Доставка на Garmin</button>
          </div> : null}
          {!selectedCheckpoint && delivery === row.assignment_id && data?.checkpoint_id ? <SwimDeliveryPanel
            key={row.assignment_id} row={row} checkpointId={data.checkpoint_id} editable={editable}
            onClose={() => {
              setDelivery(null);
              requestAnimationFrame(() => deliveryOrigin.current?.focus());
            }} /> : null}
          {edit?.row.assignment_id === row.assignment_id && !preview ? <div className="mt-3">
            {edit.kind === "move" ? <form className="flex flex-wrap items-end gap-2" onSubmit={event => {
              event.preventDefault();
              if (moveDate) void propose({ kind: "move", assignment_id: row.assignment_id, date: moveDate });
            }}>
              <label className="text-sm text-ink">Новая дата<input className={`${input} mt-1`} type="date"
                min={min} max={cycle?.end_date ?? undefined} value={moveDate} required onChange={event => setMoveDate(event.target.value)} /></label>
              <button className={primary} type="submit" disabled={!editable || moveDate === row.date}>Проверить перенос</button>
            </form> : <SubstituteForm key={row.assignment_id} row={row} disabled={!editable} onPropose={propose} />}
            <button type="button" className={`${button} mt-2`} onClick={() => setEdit(null)}>Закрыть форму</button>
          </div> : null}
        </li>)}
      </ul>
    </section>

    {!selectedCheckpoint && versions.length ? <section className={panel} aria-label="История назначений">
      <h2 className="font-semibold text-ink">История назначений</h2>
      <label className="mt-2 block max-w-lg text-sm text-ink">Версия плана
        <select className={`${input} mt-1`} aria-label="Версия плана" value={rollback} onChange={event => setRollback(event.target.value)}>
          <option value="">Выберите версию</option>
          {versions.map(item => <option key={item.checkpoint_id} value={item.checkpoint_id ?? ""}>
            {item.date_label} · {item.source_label} · версия {item.checkpoint_id}
          </option>)}
        </select>
      </label>
      {numericId(rollback) ? <div className="mt-3 flex flex-wrap gap-2">
        <Link className={button} href={`/planning/swim?checkpoint=${rollback}`}>Открыть назначения версии</Link>
        <button type="button" className={button} disabled={!editable}
          onClick={() => { const id = numericId(rollback); if (id) void propose({ kind: "rollback", checkpoint_id: id }); }}>
          Проверить возврат к этой версии
        </button>
      </div> : null}
    </section> : null}
  </main>;
}

function useProgram(programId: string, revision: number | null) {
  // api-contract: exclude immutable selected library version read; populated swim HTTP and browser readback cover it.
  return useSWR<SwimProgramAnyVersionResponse>(programId && revision
    ? `/api/swim-programs/${encodeURIComponent(programId)}/versions/${revision}` : null, fetcher);
}

function ReviewedWorkout({ row }: { row: SwimCalendarRow }) {
  const [open, setOpen] = useState(false);
  const { data, error } = useProgram(row.program_id, open ? row.program_revision : null);
  return <>
    <AuthoredSwimRow row={row} showDate />
    <details className="mt-2" onToggle={event => setOpen(event.currentTarget.open)}>
      <summary className="cursor-pointer text-sm text-ink">Серии и упражнения</summary>
      {open ? <div className="mt-2">
        {error || (data && data.fingerprint !== row.program_fingerprint)
          ? <p role="alert" className="text-sm text-ink">Не удалось прочитать точную версию тренировки.</p>
          : data ? <ProgramWorkoutSteps document={data.document} workoutId={row.workout_id} />
          : <p role="status" className="text-sm text-ink-soft">Читаем тренировку…</p>}
      </div> : null}
    </details>
  </>;
}

function PlaceForm({ programId, revision, min, max, disabled, onPropose }: {
  programId: string; revision: number; min?: string; max?: string;
  disabled: boolean; onPropose: (operation: SwimCalendarOperation) => Promise<void>;
}) {
  const { data, error } = useProgram(programId, revision);
  const [dates, setDates] = useState<Record<string, string>>({});
  const selected = Object.fromEntries(Object.entries(dates).filter(([, value]) => !!value));
  return <section className={panel} aria-label="Назначить даты">
    <h2 className="font-semibold text-ink">{data?.document.title ?? "Назначить даты"}</h2>
    {error ? <p role="alert" className="mt-2 text-sm text-ink">Сохранённая версия недоступна.</p>
      : !data ? <p role="status" className="mt-2 text-sm text-ink-soft">Читаем версию программы…</p> : <>
        <p className="mt-1 text-sm text-ink-soft">Версия {data.revision}{data.document.source_week_label ? ` · неделя тренера «${data.document.source_week_label}»` : ""}</p>
        <form className="mt-3 space-y-3" onSubmit={event => {
          event.preventDefault();
          void onPropose({ kind: "place", program_id: data.program_id, program_revision: data.revision, dates: selected });
        }}>
          <div className="grid gap-3 sm:grid-cols-2">
            {data.document.workouts.map(workout => <label className="min-w-0 break-words text-sm text-ink" key={workout.id}>
              {workout.title}
              <input className={`${input} mt-1`} aria-label={`Дата: ${workout.title}`} type="date" min={min} max={max}
                value={dates[workout.id] ?? ""} onChange={event => setDates({ ...dates, [workout.id]: event.target.value })} />
            </label>)}
          </div>
          <button type="submit" className={primary} disabled={disabled || !Object.keys(selected).length}>Проверить назначения</button>
        </form>
      </>}
  </section>;
}

function SubstituteForm({ row, disabled, onPropose }: {
  row: SwimCalendarRow; disabled: boolean; onPropose: (operation: SwimCalendarOperation) => Promise<void>;
}) {
  const { data: library, error } = useSWR<SwimProgramListResponse>("/api/swim-programs", fetcher);
  const [programId, setProgramId] = useState(row.program_id);
  const [revision, setRevision] = useState(String(row.program_revision));
  const [workout, setWorkout] = useState("");
  const { data: program, error: programError } = useProgram(programId, numericId(revision));
  return <form className="space-y-2" onSubmit={event => {
    event.preventDefault();
    if (program && workout) void onPropose({
      kind: "substitute", assignment_id: row.assignment_id,
      program_id: program.program_id, program_revision: program.revision, workout_id: workout,
    });
  }}>
    {error || programError ? <p role="alert" className="text-sm text-ink">Не удалось открыть версию программы.</p> : null}
    <div className="grid gap-2 sm:grid-cols-3">
      <label className="min-w-0 text-sm text-ink">Программа замены
        <select className={`${input} mt-1`} aria-label="Программа замены" value={programId} onChange={event => {
          const selected = library?.items.find(item => item.program_id === event.target.value);
          if (selected) { setProgramId(selected.program_id); setRevision(String(selected.revision)); setWorkout(""); }
        }}>
          {library?.items.map(item => <option key={item.program_id} value={item.program_id}>{item.title}</option>)}
        </select>
      </label>
      <label className="text-sm text-ink">Версия программы
        <input className={`${input} mt-1`} type="number" min={1} required value={revision}
          onChange={event => { setRevision(event.target.value); setWorkout(""); }} />
      </label>
      <label className="min-w-0 text-sm text-ink">Тренировка замены
        <select className={`${input} mt-1`} aria-label="Тренировка замены" required value={workout} onChange={event => setWorkout(event.target.value)}>
          <option value="">Выберите тренировку</option>
          {program?.document.workouts.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
        </select>
      </label>
    </div>
    <button type="submit" className={primary} disabled={disabled || !program || !workout}>Проверить замену</button>
  </form>;
}
