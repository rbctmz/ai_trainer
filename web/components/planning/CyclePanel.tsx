"use client";

import { useEffect, useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { ApiError, fetcher } from "@/lib/api";
import { closeCycle, readCycleHistory, resolveConstraintScope, setEventOutcome } from "@/lib/planningCycles";
import type { CloseCycleRequest, CoachConstraint, PlanningConstraintsResponse, CycleContext, CycleHistoryResponse, EventOutcome, ResolveConstraintScopeRequest, SetEventOutcomeRequest } from "@/lib/types";

export const CYCLE_LABELS: Record<CycleContext["state"], string> = {
  no_current: "Текущего цикла нет", scheduled: "Цикл запланирован", in_progress: "Подготовка идёт",
  period_ended: "Период закончился", closed: "Цикл закрыт", indeterminate: "Состояние цикла не определено",
};
const OUTCOMES: Array<{value: EventOutcome; label: string}> = [
  {value: "unspecified", label: "Не указано"}, {value: "did_not_participate", label: "Не участвовал"}, {value: "participated", label: "Участвовал"},
];
type Command =
  | {kind: "close"; cycle: string; request: CloseCycleRequest}
  | {kind: "outcome"; cycle: string; request: SetEventOutcomeRequest}
  | {kind: "scope"; request: ResolveConstraintScopeRequest};

export function CycleState({context}: {context: CycleContext}) {
  return <div>
    <h2 className="text-lg font-semibold text-ink">{CYCLE_LABELS[context.state]}</h2>
    {context.start_date && context.end_date ? <p className="mt-1 text-sm text-ink-soft">Период: {context.start_date} — {context.end_date}</p> : null}
    {context.state === "period_ended" ? <p className="mt-2 text-sm text-ink-soft">Период подготовки закончился. Выполнение плана и участие в старте требуют отдельных данных.</p> : null}
    {context.state === "no_current" ? <p className="mt-2 text-sm text-ink-soft">Можно начать новый цикл. Сохранённые планы и результаты доступны в истории.</p> : null}
    {context.state === "indeterminate" ? <p className="mt-2 text-sm text-ink-soft">В сохранённом плане недостаточно согласованных данных. Назначения и редактирование недоступны; история сохраняется.</p> : null}
  </div>;
}

export function CyclePanel({context, locked, onLockChange, onStartNew}: {
  context: CycleContext; locked: boolean; onLockChange: (value: boolean) => void; onStartNew: () => void;
}) {
  const {mutate} = useSWRConfig();
  const {data: history, error: historyError} = useSWR<CycleHistoryResponse>("/api/planning/cycles", readCycleHistory);
  const {data: constraints} = useSWR<PlanningConstraintsResponse>("/api/planning/constraints?days=365", fetcher);
  const [closing, setClosing] = useState(false);
  const [outcomes, setOutcomes] = useState<Record<string, EventOutcome>>({});
  const [command, setCommand] = useState<Command | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const [uncertain, setUncertain] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const ownLock = busy || uncertain;
  useEffect(() => {onLockChange(ownLock);}, [ownLock, onLockChange]);

  async function execute(next: Command) {
    if (inFlight.current) return;
    inFlight.current = true;
    setCommand(next); setBusy(true); setError(null); setDone(null);
    try {
      const response = next.kind === "close" ? await closeCycle(next.cycle, next.request)
        : next.kind === "outcome" ? await setEventOutcome(next.cycle, next.request)
        : await resolveConstraintScope(next.request);
      // The command's result can be historical on replay; refresh current selection.
      setUncertain(false); setCommand(null); setClosing(false); setOutcomes({});
      setDone(response.result.effect === "closed" ? "Цикл закрыт. История и результаты сохранены." : response.result.effect === "event_outcome_set" ? "Исход сохранён. Цикл не открывается повторно." : "Область ограничения сохранена.");
      await mutate(key => typeof key === "string" && (key.startsWith("/api/planning/") || key.startsWith("/api/today/")));
    } catch (e) {
      const knownRefusal = e instanceof ApiError && ["cycle_stale", "cycle_not_current", "invalid_cycle_request", "event_not_found", "event_ambiguous", "constraint_stale", "constraint_not_found", "invalid_event_outcome", "constraint_scope_required", "cycle_closed"].includes(e.code ?? "");
      setError(e instanceof ApiError ? e.message : "Ответ сервера не получен.");
      if (knownRefusal) {setCommand(null); setUncertain(false); await mutate("/api/planning/status"); await mutate("/api/planning/cycles");}
      else setUncertain(true);
    } finally {inFlight.current = false; setBusy(false);}
  }

  function close() {
    if (!context.cycle_id || !context.cycle_revision) return;
    void execute({kind: "close", cycle: context.cycle_id, request: {
      command_id: crypto.randomUUID(), confirm: true, expected_selection_revision: context.selection_revision,
      expected_cycle_revision: context.cycle_revision, expected_checkpoint_id: context.checkpoint_id,
      event_outcomes: Object.entries(outcomes).map(([event_key, outcome]) => ({event_key, outcome})),
    }});
  }

  return <section aria-label="Цикл подготовки" className="rounded-card border border-surface-border bg-surface p-5 shadow-card space-y-4">
    <CycleState context={context} />
    {done ? <p role="status" className="text-sm text-tone-success">{done}</p> : null}
    {error ? <p role="alert" className="text-sm text-tone-warning">{error}</p> : null}
    {uncertain && command ? <div role="status" className="space-y-2 text-sm text-ink-soft">
      <p>Результат действия неизвестен. Повторите проверку; исходная команда сохранена.</p>
      <button type="button" disabled={busy} onClick={() => void execute(command)} className="rounded-lg border border-surface-border px-3 py-2">Повторить проверку действия</button>
    </div> : null}
    <fieldset disabled={locked || ownLock} className="space-y-3 disabled:opacity-60">
      <div className="flex flex-wrap gap-2">
        {context.allowed_actions.includes("start_new") ? <button type="button" onClick={onStartNew} className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-foreground">Начать новый цикл</button> : null}
        {context.allowed_actions.includes("close") ? <button type="button" onClick={() => {setClosing(true); setDone(null); setError(null);}} className="rounded-lg border border-surface-border px-3 py-2 text-sm text-ink">Закрыть цикл</button> : null}
      </div>
      {closing ? <div className="rounded-lg border border-surface-border p-3 space-y-3">
        <p className="text-sm text-ink">Закрыть выбранный цикл? Текущего плана не станет. История и выполненные тренировки сохранятся; новый план не создаётся.</p>
        <p className="text-sm text-ink-soft">Участие можно оставить неуказанным.</p>
        {context.events.filter(event => !event.is_ambiguous).map(event => <label key={event.event_key} className="block text-sm text-ink-soft">
          {event.label || "Старт"} · {event.date}
          <select aria-label={`Участие: ${event.label || "Старт"}`} value={outcomes[event.event_key] ?? event.outcome} onChange={e => setOutcomes({...outcomes, [event.event_key]: e.target.value as EventOutcome})} className="ml-2 rounded border border-surface-border bg-surface p-2 text-ink">
            {OUTCOMES.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>)}
        <div className="flex flex-wrap gap-2"><button type="button" onClick={close} className="rounded-lg bg-accent px-3 py-2 text-sm text-accent-foreground">Подтвердить закрытие</button>
        <button type="button" onClick={() => {setClosing(false); setOutcomes({});}} className="rounded-lg border border-surface-border px-3 py-2 text-sm">Отмена закрытия</button></div>
      </div> : null}
      <details className="text-sm text-ink-soft">
        <summary className="cursor-pointer py-2 font-medium text-ink">История циклов</summary>
        {historyError ? <p role="alert">История сейчас недоступна. Попробуйте обновить страницу.</p> : !history ? <p>Загрузка истории…</p> : !history.cycles.length ? <p>Сохранённых циклов пока нет.</p> : history.cycles.map(cycle => <div key={cycle.cycle_id} className="border-t border-surface-border py-3 space-y-2">
          <p className="font-medium text-ink">{CYCLE_LABELS[cycle.state]} · {cycle.start_date ?? "Начало неизвестно"} — {cycle.end_date ?? "Конец неизвестен"}{cycle.is_selected ? " · выбран" : ""}</p>
          {cycle.events.map(event => <div key={event.event_key} className="space-y-1">
            <p>{event.label || "Старт"} · {event.date} · {OUTCOMES.find(option => option.value === event.outcome)?.label}</p>
            {cycle.allowed_actions.includes("set_event_outcome") && !event.is_ambiguous ? <OutcomeControl key={`${cycle.cycle_revision}-${event.event_key}`} label={event.label || "Старт"} initial={event.outcome} onSave={outcome => {
              if (cycle.cycle_id && cycle.cycle_revision) void execute({kind: "outcome", cycle: cycle.cycle_id, request: {command_id: crypto.randomUUID(), confirm: true, expected_cycle_revision: cycle.cycle_revision, event_key: event.event_key, outcome}});
            }} /> : null}
          </div>)}
        </div>)}
      </details>
      {(constraints?.constraints ?? []).filter(row => row.cycle_scope === "unknown").map(row => <ScopeControl key={`${row.id}-${row.constraint_fingerprint}`} row={row} cycles={history?.cycles ?? []} onSave={request => void execute({kind: "scope", request})} />)}
    </fieldset>
  </section>;
}

function OutcomeControl({label, initial, onSave}: {label: string; initial: EventOutcome; onSave: (value: EventOutcome) => void}) {
  const [value, setValue] = useState(initial);
  return <div className="flex flex-wrap gap-2">
    <select aria-label={`Исход: ${label}`} value={value} onChange={e => setValue(e.target.value as EventOutcome)} className="rounded border border-surface-border bg-surface p-2 text-ink">{OUTCOMES.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select>
    <button type="button" disabled={value === initial} onClick={() => onSave(value)} className="rounded-lg border border-surface-border px-3 py-2 disabled:opacity-40">Сохранить исход</button>
  </div>;
}
function ScopeControl({row, cycles, onSave}: {row: CoachConstraint; cycles: CycleContext[]; onSave: (request: ResolveConstraintScopeRequest) => void}) {
  const [scope, setScope] = useState("");
  return <div className="rounded-lg border border-tone-warning/30 p-3 space-y-2 text-sm text-ink-soft">
    <p>Не определена область ограничения на {row.date}. До уточнения оно может блокировать новый план.</p>
    <label>Применять ограничение к<select aria-label={`Область ограничения на ${row.date}`} value={scope} onChange={e => setScope(e.target.value)} className="mt-2 block w-full min-w-0 rounded border border-surface-border bg-surface p-2 text-ink"><option value="">Выберите область</option><option value="athlete">Спортсмену в указанные даты</option>{cycles.filter(cycle => cycle.cycle_id).map(cycle => <option key={cycle.cycle_id} value={cycle.cycle_id!}>Циклу {cycle.start_date ?? "с неизвестным началом"} — {cycle.end_date ?? "с неизвестным концом"}</option>)}</select></label>
    <button type="button" disabled={!scope || !row.constraint_fingerprint} onClick={() => onSave({command_id: crypto.randomUUID(), confirm: true, constraint_id: row.id, expected_constraint_fingerprint: row.constraint_fingerprint!, ...(scope === "athlete" ? {scope: "athlete" as const} : {scope: "cycle" as const, cycle_id: scope})})} className="block rounded-lg border border-surface-border px-3 py-2 disabled:opacity-40">Подтвердить область</button>
  </div>;
}
