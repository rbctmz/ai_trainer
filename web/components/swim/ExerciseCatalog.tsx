"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import useSWR from "swr";
import { fetcher, isDemo } from "@/lib/api";
import { swimError } from "@/lib/swim-api";
import type { SwimExerciseDocument, SwimExerciseListResponse, SwimExerciseVersionResponse } from "@/lib/types";
import { NumberField, TextField } from "./EditorFields";
import { ExerciseDefinition } from "./ExerciseDefinition";
import { ExerciseEditor } from "./ExerciseEditor";
import { button, panel, primary } from "./styles";

export function ExerciseCatalog({ exerciseId, revision }: { exerciseId: string | null; revision: string | null }) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [version, setVersion] = useState<number | null>(null);
  const [editing, setEditing] = useState<{ document: SwimExerciseDocument; base: number } | null>(null);
  const [ready, setReady] = useState(false);
  const [bufferError, setBufferError] = useState("");
  const targetKey = `swim-catalog-edit-${isDemo() ? "demo" : "real"}-${exerciseId ?? "new"}-${revision ?? "current"}`;
  useEffect(() => {
    try {
      const buffer = JSON.parse(sessionStorage.getItem(targetKey) || "null");
      if (buffer?.document?.id && typeof buffer.base === "number") setEditing(buffer);
    } catch { setBufferError("Не удалось восстановить буфер определения упражнения."); }
    setReady(true);
  }, [targetKey]);
  useEffect(() => {
    if (!ready) return;
    try { if (editing) sessionStorage.setItem(targetKey, JSON.stringify(editing)); else sessionStorage.removeItem(targetKey); }
    catch { setBufferError("Буфер определения недоступен. Не закрывайте страницу с незаписанной правкой."); }
  }, [ready, targetKey, editing]);
  function close() { try { sessionStorage.removeItem(targetKey); } catch { /* Read-only server content remains available. */ } setEditing(null); }
  const invalid = revision !== null && !/^[1-9]\d*$/.test(revision);
  const { data: list, error: listError, mutate: refreshList } = useSWR<SwimExerciseListResponse>(`/api/swim-exercises?q=${encodeURIComponent(query)}`, fetcher);
  // api-contract: exclude: selected immutable private UUID/version; populated HTTP and catalog browser journey cover this path.
  const { data, error, mutate: refresh } = useSWR<SwimExerciseVersionResponse>(exerciseId && !invalid ? `/api/swim-exercises/${encodeURIComponent(exerciseId)}${revision ? `/versions/${revision}` : ""}` : null, fetcher);
  function newExercise() {
    setEditing({ base: 0, document: { schema_version: 1, id: crypto.randomUUID(), name: "", variant: "", aliases: [], instructions: "", stroke: "unspecified", equipment: [], environments: [], source_label: null, source_text: null, video_cues: [] } });
  }
  return <>
    <section className={panel} aria-label="Справочник упражнений">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-xl font-semibold text-ink">Справочник упражнений</h2><p className="mt-1 text-sm text-ink-soft">Версии техники, вариантов и видео-подсказок. Дозировка задаётся в программе.</p></div><button type="button" className={primary} disabled={!ready || editing !== null} onClick={newExercise}>Новое упражнение</button></div>
      {bufferError ? <p role="alert" className="mt-3 text-sm text-tone-warning">{bufferError}</p> : null}
      <form className="mt-4 space-y-2" onSubmit={event => { event.preventDefault(); setQuery(search); void refreshList(); }}><TextField label="Поиск по справочнику" value={search} onChange={setSearch} /><button type="submit" className={button}>Найти в справочнике</button></form>
      {listError ? <div role="alert" className="mt-3 text-sm text-tone-warning">{swimError(listError)} <button type="button" className={button} onClick={() => void refreshList()}>Повторить чтение справочника</button></div> : !list ? <p role="status" className="mt-3 text-sm text-ink-soft">Загружаем справочник…</p> : list.items.length ? <ul className="mt-4 space-y-3">{list.items.map(item => <li key={item.exercise_id}><Link className="break-words text-sm text-accent underline" href={`/coach/swim?catalog=1&exercise=${item.exercise_id}&exercise_revision=${item.revision}`} onClick={() => setEditing(null)}>{item.document.name} — {item.document.variant}</Link><p className="mt-1 text-sm text-ink-soft">Версия {item.revision}</p></li>)}</ul> : <p className="mt-3 text-sm text-ink-soft">Упражнений пока нет или запрос не дал результатов.</p>}
    </section>
    {editing ? <ExerciseEditor key={`${editing.document.id}/${editing.base}`} initial={editing.document} baseRevision={editing.base} onClose={close} onSaved={saved => { close(); void refreshList(); router.push(`/coach/swim?catalog=1&exercise=${saved.exercise_id}&exercise_revision=${saved.revision}`); }} /> : exerciseId ? invalid ? <p role="alert" className={panel}>Номер версии должен быть положительным целым числом.</p> : error ? <div role="alert" className={panel}>{swimError(error)} <button type="button" className={button} onClick={() => void refresh()}>Повторить чтение упражнения</button></div> : !data ? <p role="status" className="text-sm text-ink-soft">Читаем версию упражнения…</p> : <section className={`${panel} space-y-4`} aria-label="Сохранённое упражнение">
      <p role="status" className="text-sm text-ink">Упражнение · сохранённая версия {data.revision} · {new Date(data.confirmed_at).toLocaleString("ru-RU")}</p>
      <ExerciseDefinition document={data.document} />
      <button type="button" className={button} onClick={() => setEditing({ document: data.document, base: data.revision })}>Создать новую версию упражнения</button>
      <form className="space-y-2" onSubmit={event => { event.preventDefault(); if (version) router.push(`/coach/swim?catalog=1&exercise=${data.exercise_id}&exercise_revision=${version}`); }}><NumberField label="Версия упражнения для открытия" value={version} onChange={setVersion} /><div className="flex flex-wrap gap-2"><button type="submit" className={button}>Открыть версию упражнения</button><Link className={button} href={`/coach/swim?catalog=1&exercise=${data.exercise_id}`}>Последняя версия упражнения</Link></div></form>
    </section> : null}
  </>;
}
