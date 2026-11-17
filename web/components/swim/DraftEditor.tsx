"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, isDemo } from "@/lib/api";
import { swimError, swimPost } from "@/lib/swim-api";
import type { SwimExerciseReference, SwimImportDraftResponse, SwimImportPatchOperation, SwimV2NodeInput, SwimV2WorkoutInput } from "@/lib/types";
import { Choice, ContextFields, NodeFields, NumberField, TextField, newNode } from "./EditorFields";
import { button, panel, primary } from "./styles";
import { ExercisePicker } from "./ExercisePicker";

export type EditTarget = { kind: "node" | "add" | "workout"; id: string } | { kind: "title" };

function allNodes(nodes: SwimV2NodeInput[]): SwimV2NodeInput[] {
  return nodes.flatMap(node => [node, ...(node.kind === "group" ? allNodes(node.steps) : [])]);
}

export function DraftEditor({ draft, target, busy, onStart, onWritten, onEnd, onClose }: {
  draft: SwimImportDraftResponse; target: EditTarget; busy: boolean; onStart: () => void;
  onWritten: () => Promise<void>; onEnd: () => void; onClose: () => void;
}) {
  const document = draft.document!;
  const nodes = document.workouts.flatMap(workout => allNodes(workout.steps));
  const groups = nodes.filter((item): item is Extract<SwimV2NodeInput, { kind: "group" }> => item.kind === "group");
  const selected = target.kind === "node" ? nodes.find(node => node.id === target.id) : undefined;
  const selectedWorkout = target.kind === "workout" ? document.workouts.find(workout => workout.id === target.id) : undefined;
  const [node, setNode] = useState<SwimV2NodeInput>(() => structuredClone(selected ?? newNode()));
  const [workout, setWorkout] = useState<SwimV2WorkoutInput>(() => structuredClone(selectedWorkout ?? document.workouts[0]));
  const [title, setTitle] = useState(document.title);
  const [field, setField] = useState<"context" | "title">("context");
  const [action, setAction] = useState<"edit" | "move" | "remove" | "binding">("edit");
  const [reference, setReference] = useState<SwimExerciseReference | null>(() => {
    const binding = selected ? document.exercise_bindings.find(item => item.node_id === selected.id) : null;
    return binding ? { node_id: binding.node_id, exercise_id: binding.exercise_id, revision: binding.revision } : null;
  });
  const [destination, setDestination] = useState(target.kind === "add" ? target.id : document.workouts[0].id);
  const children = document.workouts.find(item => item.id === destination)?.steps ?? groups.find(item => item.id === destination)?.steps ?? [];
  const [position, setPosition] = useState(children.length + 1);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const revision = useRef(draft.revision);
  const command = useRef<{ key: string; request: { expected_revision: number; request_id: string; operation: SwimImportPatchOperation } } | null>(null);
  const region = useRef<HTMLElement>(null);
  const bufferKey = `swim-edit-form-${isDemo() ? "demo" : "real"}-${draft.import_id}-${target.kind}-${"id" in target ? target.id : "title"}`;
  useEffect(() => {
    try {
      const buffer = JSON.parse(sessionStorage.getItem(bufferKey) || "null");
      if (buffer?.node?.id && buffer.workout?.id && typeof buffer.revision === "number") {
        setNode(buffer.node); setWorkout(buffer.workout); setTitle(buffer.title); setField(buffer.field);
        setAction(buffer.action); setDestination(buffer.destination); setPosition(buffer.position);
        if ("reference" in buffer) setReference(buffer.reference);
        revision.current = buffer.revision; command.current = buffer.command;
      }
    } catch { setError("Не удалось восстановить буфер правки. Сверьте поля с исходником."); }
    setReady(true); region.current?.focus();
  }, [bufferKey]);
  useEffect(() => {
    if (!ready) return;
    try { sessionStorage.setItem(bufferKey, JSON.stringify({ node, workout, title, field, action, destination, position, reference, revision: revision.current, command: command.current })); }
    catch { setError("Буфер правки не сохранён. Не закрывайте страницу с незаписанными изменениями."); }
  }, [ready, bufferKey, node, workout, title, field, action, destination, position, reference]);
  function close() { try { sessionStorage.removeItem(bufferKey); } catch { /* Server history is unaffected. */ } onClose(); }
  let operation: SwimImportPatchOperation;
  if (target.kind === "title") operation = { op: "set_title", title };
  else if (target.kind === "workout") operation = field === "title" ? { op: "set_title", title: workout.title, workout_id: workout.id } : { op: "set_context", workout_id: workout.id, environment: workout.environment, pool_length_meters: workout.pool_length_meters };
  else if (target.kind === "add") operation = { op: "add_node", parent_id: destination, index: position - 1, node };
  else if (action === "binding") operation = { op: "set_binding", node_id: target.id, reference };
  else if (action === "remove") operation = { op: "remove_node", node_id: target.id };
  else if (action === "move") operation = { op: "move_node", node_id: target.id, parent_id: destination, index: position - 1 };
  else operation = { op: selected?.kind === "unresolved" && node.kind !== "unresolved" ? "resolve_node" : "replace_node", node_id: target.id, node };
  async function submit() {
    if (busy) return;
    if (revision.current !== draft.revision) { setError("Черновик изменился во время правки. Скопируйте нужные значения, закройте форму и откройте актуальный элемент."); return; }
    onStart(); setError("");
    const key = JSON.stringify(operation);
    if (!command.current || command.current.key !== key) command.current = { key, request: { expected_revision: revision.current, request_id: crypto.randomUUID(), operation } };
    try {
      await swimPost<SwimImportDraftResponse>(`/api/swim-imports/${encodeURIComponent(draft.import_id)}/patch`, command.current.request);
      await onWritten(); close();
    } catch (cause) {
      setError(swimError(cause));
      if (cause instanceof ApiError && cause.status === 409) setError(`${swimError(cause)} Введённые значения остаются в этой форме.`);
    } finally { onEnd(); }
  }
  const heading = target.kind === "node" ? "Правка элемента" : target.kind === "add" ? "Новый элемент" : target.kind === "workout" ? "Правка тренировки" : "Название программы";
  return <section ref={region} tabIndex={-1} className={`${panel} focus:outline-none focus:ring-2 focus:ring-accent`} aria-label={heading}>
    <form className="space-y-4" onSubmit={event => { event.preventDefault(); void submit(); }}>
      <h2 className="text-lg font-semibold text-ink">{heading}</h2>
      <fieldset className="min-w-0 space-y-3" disabled={busy || !ready}>
        {target.kind === "title" ? <TextField label="Название программы" value={title} required onChange={setTitle} /> : target.kind === "workout" ? <><Choice label="Что изменить" value={field} options={[["context", "Среду и бассейн"], ["title", "Название"]]} onChange={setField} />{field === "title" ? <TextField label="Название тренировки" required value={workout.title} onChange={title => setWorkout({ ...workout, title })} /> : <ContextFields workout={workout} onChange={setWorkout} />}</> : <>
          {target.kind === "node" ? <Choice label="Действие с элементом" value={action} options={[["edit", "Изменить"], ["move", "Переместить"], ["remove", "Удалить из черновика"], ...(selected?.kind === "swim" ? [["binding", "Техника из справочника"] as const] : [])]} onChange={setAction} /> : null}
          {action === "binding" && target.kind === "node" ? <ExercisePicker nodeId={target.id} reference={reference} onChange={setReference} /> : null}
          {target.kind === "add" || action === "move" ? <><Choice label="Куда добавить" value={destination} options={[...document.workouts.map(item => [item.id, item.title] as const), ...groups.map(item => [item.id, item.name] as const)]} onChange={value => { setDestination(value); setPosition(1); }} /><NumberField label="Позиция в списке" value={position} max={101} onChange={value => setPosition(value ?? 0)} /></> : null}
          {target.kind === "add" || action === "edit" ? <NodeFields node={node} source={draft.source_text} onChange={setNode} kindEditable={target.kind === "add" || selected?.kind === "unresolved"} childrenEditable={target.kind === "add" || selected?.kind === "unresolved"} /> : action === "remove" ? <p className="text-sm border-l-2 border-tone-warning pl-3 text-ink">Элемент и вложенные шаги будут удалены из текущего черновика. Исходник и предыдущие серверные ревизии сохраняются.</p> : null}
        </>}
        <div className="flex flex-wrap gap-2"><button type="submit" className={primary}>{action === "remove" && target.kind === "node" ? "Подтвердить удаление элемента" : "Применить правку"}</button><button type="button" className={button} onClick={close}>Отменить правку</button></div>
      </fieldset>
      {error ? <p role="alert" className="text-sm border-l-2 border-tone-warning pl-3 text-ink">{error}</p> : null}
    </form>
  </section>;
}
