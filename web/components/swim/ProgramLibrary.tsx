"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { swimError } from "@/lib/swim-api";
import type { SwimProgramAnyVersionResponse, SwimProgramListResponse } from "@/lib/types";
import { ProgramStructure, ProgramSummary, metres } from "./ProgramStructure";
import { SourceView } from "./SourceView";
import { ResponsiveDisclosure } from "./ResponsiveDisclosure";
import { button, input, panel } from "./styles";

export function ProgramLibrary() {
  const { data, error, mutate } = useSWR<SwimProgramListResponse>("/api/swim-programs", fetcher);
  return <section className={panel} aria-label="Сохранённые программы">
    <h2 className="text-lg font-semibold text-ink">Сохранённые программы</h2>
    {error ? <div role="alert" className="mt-2 text-sm border-l-2 border-tone-warning pl-3 text-ink">{swimError(error)} <button type="button" className={button} onClick={() => void mutate()}>Повторить чтение библиотеки</button></div> : !data ? <p role="status" className="mt-2 text-sm text-ink-soft">Загружаем библиотеку…</p> : data.items.length ? <ul className="mt-3 space-y-3">{data.items.map(item => <li key={item.program_id}>
      <Link className="break-words text-sm text-accent underline" href={`/coach/swim?program=${item.program_id}&revision=${item.revision}`}>{item.title}</Link>
      <p className="mt-1 text-sm text-ink-soft">Версия {item.revision} · тренировок: {item.workout_count} · {item.distance_meters === null ? `Дистанция неизвестна; фиксированная часть ${metres(item.known_distance_meters)}` : metres(item.distance_meters)}</p>
    </li>)}</ul> : <p className="mt-2 text-sm text-ink-soft">После подтверждения программа появится здесь.</p>}
  </section>;
}

export function SavedProgram({ programId, revision }: { programId: string; revision: string | null }) {
  const router = useRouter();
  const [requested, setRequested] = useState("");
  const invalid = revision !== null && !/^[1-9]\d*$/.test(revision);
  // api-contract: exclude immutable selected-ID/history read; populated V1/V2 HTTP and browser readback cover this path.
  const { data, error, mutate } = useSWR<SwimProgramAnyVersionResponse>(invalid ? null : `/api/swim-programs/${encodeURIComponent(programId)}${revision ? `/versions/${revision}` : ""}`, fetcher);
  if (invalid) return <p role="alert" className={panel}>Номер версии должен быть положительным целым числом.</p>;
  if (error) return <div role="alert" className={panel}>{swimError(error)} <button type="button" className={button} onClick={() => void mutate()}>Повторить чтение версии</button></div>;
  if (!data) return <p role="status" className="text-sm text-ink-soft">Читаем сохранённую версию…</p>;
  return <>
    <section className={panel} aria-label="Сохранённая версия">
      <h2 className="break-words text-xl font-semibold text-ink">{data.document.title}</h2>
      <p role="status" className="mt-2 text-sm text-ink">Сохранённая версия {data.revision} · {new Date(data.confirmed_at).toLocaleString("ru-RU")}</p>
      <p className="mt-1 text-sm text-ink-soft">Прочитана из библиотеки. Для повторного открытия Коуч не вызывается.</p>
      <form className="mt-3 flex flex-wrap items-end gap-2" onSubmit={event => { event.preventDefault(); if (/^[1-9]\d*$/.test(requested)) router.push(`/coach/swim?program=${programId}&revision=${requested}`); }}>
        <label className="min-w-0 text-sm text-ink">Версия для открытия<input className={`${input} mt-1 max-w-40`} type="number" min="1" step="1" required value={requested} onChange={event => setRequested(event.target.value)} /></label>
        <button type="submit" className={button}>Открыть версию</button>
        <Link className={button} href={`/coach/swim?program=${programId}`}>Последняя версия</Link>
        <Link className={button} href={`/planning/swim?program=${data.program_id}&revision=${data.revision}`}>Назначить даты</Link>
      </form>
    </section>
    <ProgramSummary document={data.document} summary={data.summary} />
    <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]"><ResponsiveDisclosure title="Исходник сохранённой программы"><SourceView text={data.document.source_text} /></ResponsiveDisclosure><ProgramStructure document={data.document} summary={data.summary} showSummary={false} /></div>
  </>;
}
