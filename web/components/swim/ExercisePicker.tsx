"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { swimError } from "@/lib/swim-api";
import type { SwimExerciseListResponse, SwimExerciseReference, SwimExerciseVersionResponse } from "@/lib/types";
import { NumberField, TextField } from "./EditorFields";
import { ExerciseDefinition } from "./ExerciseDefinition";
import { button } from "./styles";

export function ExercisePicker({ nodeId, reference, onChange }: { nodeId: string; reference: SwimExerciseReference | null; onChange: (reference: SwimExerciseReference | null) => void }) {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<SwimExerciseVersionResponse | null>(null);
  const [revision, setRevision] = useState<number | null>(reference?.revision ?? null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { data, error: listError, mutate } = useSWR<SwimExerciseListResponse>(`/api/swim-exercises?q=${encodeURIComponent(query)}`, fetcher);
  function pick(version: SwimExerciseVersionResponse) {
    setPicked(version); setRevision(version.revision); setError("");
    onChange({ node_id: nodeId, exercise_id: version.exercise_id, revision: version.revision });
  }
  async function loadRevision() {
    if (!reference || !revision || loading) return;
    setLoading(true); setError("");
    try {
      // api-contract: exclude: exact private catalog UUID/revision; populated HTTP and pinned-version browser journey cover this path.
      pick(await fetcher<SwimExerciseVersionResponse>(`/api/swim-exercises/${encodeURIComponent(reference.exercise_id)}/versions/${revision}`));
    } catch (cause) { setError(swimError(cause)); }
    finally { setLoading(false); }
  }
  return <section className="min-w-0 space-y-3 rounded-lg border border-surface-border p-3" aria-label="Выбор упражнения">
    <h3 className="font-semibold text-ink">Техника из справочника</h3>
    <p className="text-sm text-ink-soft">Привязывается точная версия. Метры, отдых, инструкция задания и снаряжение в шаге остаются прежними.</p>
    <TextField label="Поиск упражнения" value={search} onChange={setSearch} />
    <button type="button" className={button} onClick={() => { setQuery(search); void mutate(); }}>Найти упражнения</button>
    {listError ? <p role="alert" className="text-sm text-tone-warning">{swimError(listError)}</p> : !data ? <p role="status" className="text-sm text-ink-soft">Загружаем упражнения…</p> : data.items.length ? <ul className="space-y-2">{data.items.map(item => <li key={item.exercise_id}><button type="button" className={`${button} text-left`} onClick={() => pick(item)}>Выбрать: {item.document.name} — {item.document.variant} · версия {item.revision}</button></li>)}</ul> : <p className="text-sm text-ink-soft">Упражнений по этому запросу нет. Создайте определение в справочнике, затем вернитесь к шагу.</p>}
    {reference ? <div className="space-y-2"><p className="text-sm font-medium text-ink">Выбрана версия {reference.revision}</p><NumberField label="Версия упражнения для просмотра" value={revision} onChange={setRevision} /><button type="button" className={button} disabled={loading || !revision} onClick={() => void loadRevision()}>Выбрать эту версию</button><button type="button" className={button} onClick={() => { onChange(null); setPicked(null); }}>Убрать привязку упражнения</button></div> : <p className="text-sm text-ink-soft">Привязки упражнения нет.</p>}
    {picked ? <ExerciseDefinition document={picked.document} /> : null}
    {error ? <p role="alert" className="text-sm text-tone-warning">{error}</p> : null}
  </section>;
}
