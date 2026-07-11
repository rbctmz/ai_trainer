"use client";

import { useState } from "react";
import { ApiError, postJSON } from "@/lib/api";
import type { AdjustResult, BuiltPlan, CoachProposalAction } from "@/lib/types";

const DAY_LABELS: Record<string, string> = {
  mon: "Пн",
  tue: "Вт",
  wed: "Ср",
  thu: "Чт",
  fri: "Пт",
  sat: "Сб",
  sun: "Вс",
};

export interface BuildPlanParams {
  goal_type: string;
  distance: string;
  event_date: string;
  available_hours: number;
  available_days?: string[] | null;
}

export interface AdjustPlanParams {
  rows: Record<string, unknown>[];
  weeks: number;
}

interface ProposalCardProps {
  proposalId: number;
  action: CoachProposalAction;
  status: string;
  params: Record<string, unknown>;
  preview: Record<string, unknown>;
  onConfirmed: (message: string) => void;
  onCancelled: (message?: string) => void;
}

interface ProposalApprovalResponse {
  proposal: { id: number; status: string };
  result: BuiltPlan | AdjustResult | RecoveryReplanResult;
}

interface RecoveryReplanResult {
  plan_id: string;
  rollback_checkpoint_id: number;
  near_term_edit?: { compact_label?: string };
  totals: { peak_tss: number; total_tss: number };
}

interface ProposalRejectResponse {
  proposal: { id: number; status: string };
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : String(value ?? "");
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value)
    ? value
    : Number(value ?? fallback) || fallback;
}

function asStringArray(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null;
  const items = value
    .map((item) => asString(item).trim())
    .filter(Boolean);
  return items.length > 0 ? items : null;
}

function asRecordList(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is Record<string, unknown> => !!item && typeof item === "object");
}

function buildPlanParams(params: Record<string, unknown>): BuildPlanParams {
  return {
    goal_type: asString(params.goal_type).trim(),
    distance: asString(params.distance).trim(),
    event_date: asString(params.event_date).trim(),
    available_hours: asNumber(params.available_hours, 10),
    available_days: asStringArray(params.available_days),
  };
}

function adjustPlanParams(params: Record<string, unknown>): AdjustPlanParams {
  return {
    rows: asRecordList(params.rows),
    weeks: asNumber(params.weeks, 1),
  };
}

function formatAvailableDays(days: string[] | null | undefined): string {
  if (!days || days.length === 0) return "Все дни";
  return days.map((day) => DAY_LABELS[day] ?? day).join(", ");
}

function buildConfirmedMessage(result: BuiltPlan): string {
  return [
    "✅ План сохранён.",
    `${result.goal.goal_type} • ${result.goal.distance}`,
    `${result.goal.weeks_to_race} нед.`,
    `пик ${result.totals.peak_tss} TSS`,
  ].join(" ");
}

function adjustConfirmedMessage(result: AdjustResult): string {
  return [
    "✅ Корректировка плана применена.",
    result.adjustment.label,
    `пик ${result.totals.peak_tss} TSS`,
  ].join(" ");
}

function recoveryConfirmedMessage(result: RecoveryReplanResult): string {
  return [
    "✅ Recovery Replan применён.",
    result.near_term_edit?.compact_label ?? "Ближняя нагрузка снижена.",
    `Откат к checkpoint #${result.rollback_checkpoint_id} доступен в истории решений.`,
  ].join(" ");
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-surface/70 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-ink-soft">{label}</div>
      <div className="mt-0.5 text-lg font-semibold text-ink">{value}</div>
    </div>
  );
}

function DeltaTile({
  label,
  previousValue,
  nextValue,
  unit,
}: {
  label: string;
  previousValue: number | null;
  nextValue: number;
  unit: string;
}) {
  const hasPrevious = previousValue != null && Number.isFinite(previousValue);
  const delta = hasPrevious ? Math.round(nextValue - (previousValue as number)) : null;
  const deltaLabel =
    delta == null ? null : delta === 0 ? "без изменений" : `${delta > 0 ? "+" : ""}${delta} ${unit}`;

  return (
    <div className="rounded-lg bg-surface/70 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-ink-soft">{label}</div>
      <div className="mt-0.5 flex items-baseline gap-1.5">
        {hasPrevious ? (
          <>
            <span className="text-sm text-ink-soft line-through decoration-ink-soft/40">
              {Math.round(previousValue as number)}
            </span>
            <span className="text-ink-soft">→</span>
          </>
        ) : null}
        <span className="text-lg font-semibold text-ink">
          {Math.round(nextValue)} {unit}
        </span>
      </div>
      {deltaLabel ? <div className="mt-0.5 text-xs text-ink-soft">{deltaLabel}</div> : null}
    </div>
  );
}

function CompletionBar({ share }: { share: number }) {
  const percent = Math.max(0, Math.min(100, Math.round(share * 100)));
  return (
    <div>
      <div className="flex items-center justify-between text-xs text-ink-soft">
        <span>Выполнение окна</span>
        <span className="font-medium text-ink">{percent}%</span>
      </div>
      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-surface/70">
        <div
          className="h-full rounded-full bg-tone-neutral transition-all"
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}

export function ProposalCard({
  proposalId,
  action,
  status,
  params,
  preview,
  onConfirmed,
  onCancelled,
}: ProposalCardProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const goal = (preview.goal as Record<string, unknown> | undefined) ?? {};
  const buildParams = action === "build_plan" ? buildPlanParams(params) : null;
  const adjustParams = action === "adjust_plan" ? adjustPlanParams(params) : null;
  const completionShare = asNumber(preview.completion_share, 0);
  const previousPeakTss =
    preview.previous_peak_tss != null ? asNumber(preview.previous_peak_tss) : null;
  const previousTotalTss =
    preview.previous_total_tss != null ? asNumber(preview.previous_total_tss) : null;
  const currentSession =
    (preview.current_session as Record<string, unknown> | undefined) ?? {};
  const recommendedSession =
    (preview.recommended_session as Record<string, unknown> | undefined) ?? {};
  const recoveryEvidence = asStringArray(preview.evidence) ?? [];

  async function handleConfirm() {
    setLoading(true);
    setError(null);

    try {
      if (action === "build_plan") {
        const response = await postJSON<ProposalApprovalResponse>(
          `/api/decisions/proposals/${proposalId}/approve`,
          {},
        );
        onConfirmed(buildConfirmedMessage(response.result as BuiltPlan));
        return;
      }

      if (action === "recovery_replan") {
        const response = await postJSON<ProposalApprovalResponse>(
          `/api/decisions/proposals/${proposalId}/approve`,
          {},
        );
        onConfirmed(recoveryConfirmedMessage(response.result as RecoveryReplanResult));
        return;
      }

      const response = await postJSON<ProposalApprovalResponse>(
        `/api/decisions/proposals/${proposalId}/approve`,
        {},
      );
      onConfirmed(adjustConfirmedMessage(response.result as AdjustResult));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось применить изменение");
    } finally {
      setLoading(false);
    }
  }

  async function handleReject() {
    setLoading(true);
    setError(null);

    try {
      await postJSON<ProposalRejectResponse>(
        `/api/decisions/proposals/${proposalId}/reject`,
        {},
      );
      onCancelled("Отклонено: план не изменён.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось отклонить предложение");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-card border border-tone-neutral/30 bg-tone-neutral/10 p-4 shadow-card">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-ink">
            {action === "build_plan"
              ? "Предложение нового плана"
              : action === "recovery_replan"
                ? "Recovery Replan"
                : "Предложение корректировки"}
          </div>
          <p className="mt-1 text-xs text-ink-soft">
            Изменение попадёт в активный план только после подтверждения.
          </p>
        </div>
        <span className="rounded-full bg-surface/80 px-2 py-1 text-[11px] font-medium text-tone-neutral">
          {status === "pending" ? "Нужен confirm" : status}
        </span>
      </div>

      {action === "build_plan" ? (
        <>
          <ul className="mt-3 space-y-1 text-sm text-ink-soft">
            <li>
              Цель: {asString(goal.goal_type || buildParams?.goal_type)} •{" "}
              {asString(goal.distance || buildParams?.distance)}
            </li>
            <li>Старт: {asString(goal.event_date || buildParams?.event_date)}</li>
            <li>Часов в неделю: {buildParams?.available_hours ?? "—"}</li>
            <li>Доступные дни: {formatAvailableDays(buildParams?.available_days)}</li>
          </ul>

          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {preview.total_weeks != null ? (
              <StatTile label="Недель" value={`${asNumber(preview.total_weeks)}`} />
            ) : null}
            {preview.target_weekly_tss != null ? (
              <StatTile label="Цель/нед" value={`${asNumber(preview.target_weekly_tss)} TSS`} />
            ) : null}
            {preview.peak_tss != null ? (
              <StatTile label="Пик" value={`${asNumber(preview.peak_tss)} TSS`} />
            ) : null}
            {preview.total_tss != null ? (
              <StatTile label="Всего" value={`${asNumber(preview.total_tss)} TSS`} />
            ) : null}
          </div>

          {preview.forecast_message ? (
            <p className="mt-3 text-sm text-ink-soft">{asString(preview.forecast_message)}</p>
          ) : null}
        </>
      ) : action === "recovery_replan" ? (
        <>
          <p className="mt-3 text-sm text-ink-soft">{asString(preview.reason)}</p>
          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
            <div className="rounded-lg bg-surface/70 px-3 py-2">
              <div className="text-[11px] uppercase tracking-wide text-ink-soft">Как есть</div>
              <div className="mt-1 text-sm font-medium text-ink">
                {asString(currentSession.name)} · {asNumber(currentSession.tss)} TSS
              </div>
              <div className="mt-0.5 text-xs text-ink-soft">
                роль {asString(currentSession.role)} · риск {asString(preview.severity)}
              </div>
            </div>
            <div className="rounded-lg border border-tone-success/30 bg-tone-success/10 px-3 py-2">
              <div className="text-[11px] uppercase tracking-wide text-tone-success">
                Рекомендация
              </div>
              <div className="mt-1 text-sm font-medium text-ink">
                {asString(recommendedSession.name)} · {asNumber(recommendedSession.tss)} TSS
              </div>
              <div className="mt-0.5 text-xs text-ink-soft">
                роль {asString(recommendedSession.role)} · Δ {asNumber(recommendedSession.delta_tss)} TSS
              </div>
            </div>
          </div>
          {recoveryEvidence.length > 0 ? (
            <ul className="mt-3 space-y-1 text-xs text-ink-soft">
              {recoveryEvidence.map((item) => (
                <li key={item}>• {item}</li>
              ))}
            </ul>
          ) : null}
          <p className="mt-3 text-xs text-ink-faint">
            Снятый объём не догоняется автоматически. Исходный checkpoint сохраняется для отката.
          </p>
        </>
      ) : (
        <>
          <ul className="mt-3 space-y-1 text-sm text-ink-soft">
            <li>Недель для пересборки: {adjustParams?.weeks ?? "—"}</li>
            {preview.adjustment_label || preview.adjustment_status ? (
              <li>Статус: {asString(preview.adjustment_label || preview.adjustment_status)}</li>
            ) : null}
            {preview.missed_sessions != null ? (
              <li>Пропущено сессий: {asNumber(preview.missed_sessions)}</li>
            ) : null}
          </ul>

          {preview.completion_share != null ? (
            <div className="mt-3">
              <CompletionBar share={completionShare} />
            </div>
          ) : null}

          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
            {preview.peak_tss != null ? (
              <DeltaTile
                label="Пик"
                previousValue={previousPeakTss}
                nextValue={asNumber(preview.peak_tss)}
                unit="TSS"
              />
            ) : null}
            {preview.total_tss != null ? (
              <DeltaTile
                label="Всего"
                previousValue={previousTotalTss}
                nextValue={asNumber(preview.total_tss)}
                unit="TSS"
              />
            ) : null}
          </div>

          {preview.forecast_message ? (
            <p className="mt-3 text-sm text-ink-soft">{asString(preview.forecast_message)}</p>
          ) : null}
        </>
      )}

      {error ? (
        <div className="mt-3 rounded-lg border border-tone-danger/30 bg-tone-danger/10 px-3 py-2 text-sm text-tone-danger">
          {error}
        </div>
      ) : null}

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={handleConfirm}
          disabled={loading}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-foreground transition hover:bg-accent/90 disabled:opacity-40"
        >
          {loading ? "Сохраняю…" : "Подтвердить"}
        </button>
        <button
          type="button"
          onClick={handleReject}
          disabled={loading}
          className="rounded-lg border border-surface-border bg-surface px-4 py-2 text-sm font-medium text-ink-soft transition hover:bg-surface-muted disabled:opacity-40"
        >
          Отменить
        </button>
      </div>
    </div>
  );
}
