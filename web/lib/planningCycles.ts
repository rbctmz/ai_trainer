/** Typed cycle transport for the M4 UI handoff; state decisions stay on the server. */
import { fetcher, postJSON } from "./api";
import type {
  CloseCycleRequest,
  CycleCommandResponse,
  CycleContext,
  CycleHistoryResponse,
  ResolveConstraintScopeRequest,
  SetEventOutcomeRequest,
} from "@/lib/types";

export function readCurrentCycle(): Promise<CycleContext> {
  return fetcher<CycleContext>("/api/planning/cycles/current");
}

export function readCycleHistory(): Promise<CycleHistoryResponse> {
  return fetcher<CycleHistoryResponse>("/api/planning/cycles");
}

export function readCycle(cycle_id: string): Promise<CycleContext> {
  return fetcher<CycleContext>(`/api/planning/cycles/${encodeURIComponent(cycle_id)}`);
}

export function closeCycle(cycle_id: string, request: CloseCycleRequest): Promise<CycleCommandResponse> {
  return postJSON<CycleCommandResponse>(`/api/planning/cycles/${encodeURIComponent(cycle_id)}/close`, request);
}

export function setEventOutcome(cycle_id: string, request: SetEventOutcomeRequest): Promise<CycleCommandResponse> {
  return postJSON<CycleCommandResponse>(`/api/planning/cycles/${encodeURIComponent(cycle_id)}/event-outcome`, request);
}

export function resolveConstraintScope(request: ResolveConstraintScopeRequest): Promise<CycleCommandResponse> {
  return postJSON<CycleCommandResponse>("/api/planning/cycles/constraint-scope", request);
}
