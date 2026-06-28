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
  action: CoachProposalAction;
  params: Record<string, unknown>;
  preview: Record<string, unknown>;
  onConfirmed: (message: string) => void;
  onCancelled: () => void;
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

export function ProposalCard({
  action,
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

  async function handleConfirm() {
    setLoading(true);
    setError(null);

    try {
      if (action === "build_plan") {
        const response = await postJSON<BuiltPlan>("/api/planning/build", {
          ...buildParams,
          persist: true,
        });
        onConfirmed(buildConfirmedMessage(response));
        return;
      }

      const response = await postJSON<AdjustResult>("/api/planning/adjust", {
        ...adjustParams,
        persist: true,
      });
      onConfirmed(adjustConfirmedMessage(response));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось применить изменение");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-card border border-blue-200 bg-blue-50 p-4 shadow-card">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-ink">
            {action === "build_plan" ? "Предложение нового плана" : "Предложение корректировки"}
          </div>
          <p className="mt-1 text-xs text-ink-soft">
            Изменение попадёт в активный план только после подтверждения.
          </p>
        </div>
        <span className="rounded-full bg-white/80 px-2 py-1 text-[11px] font-medium text-tone-neutral">
          Нужен confirm
        </span>
      </div>

      <ul className="mt-3 space-y-1 text-sm text-ink">
        {action === "build_plan" ? (
          <>
            <li>
              Цель: {asString(goal.goal_type || buildParams?.goal_type)} •{" "}
              {asString(goal.distance || buildParams?.distance)}
            </li>
            <li>Старт: {asString(goal.event_date || buildParams?.event_date)}</li>
            <li>Часов в неделю: {buildParams?.available_hours ?? "—"}</li>
            <li>Доступные дни: {formatAvailableDays(buildParams?.available_days)}</li>
            {preview.total_weeks != null ? <li>Недель: {asNumber(preview.total_weeks)}</li> : null}
            {preview.target_weekly_tss != null ? (
              <li>Цель/нед: {asNumber(preview.target_weekly_tss)} TSS</li>
            ) : null}
            {preview.peak_tss != null ? <li>Пик: {asNumber(preview.peak_tss)} TSS</li> : null}
            {preview.total_tss != null ? <li>Всего: {asNumber(preview.total_tss)} TSS</li> : null}
            {preview.forecast_message ? (
              <li className="pt-1 text-ink-soft">{asString(preview.forecast_message)}</li>
            ) : null}
          </>
        ) : (
          <>
            <li>Недель для пересборки: {adjustParams?.weeks ?? "—"}</li>
            {preview.adjustment_label || preview.adjustment_status ? (
              <li>
                Статус: {asString(preview.adjustment_label || preview.adjustment_status)}
              </li>
            ) : null}
            {preview.missed_sessions != null ? (
              <li>Пропущено сессий: {asNumber(preview.missed_sessions)}</li>
            ) : null}
            {preview.completion_share != null ? (
              <li>Выполнение: {Math.round(completionShare * 100)}%</li>
            ) : null}
            {preview.peak_tss != null ? <li>Новый пик: {asNumber(preview.peak_tss)} TSS</li> : null}
            {preview.total_tss != null ? (
              <li>Новый общий объём: {asNumber(preview.total_tss)} TSS</li>
            ) : null}
            {preview.forecast_message ? (
              <li className="pt-1 text-ink-soft">{asString(preview.forecast_message)}</li>
            ) : null}
          </>
        )}
      </ul>

      {error ? (
        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-tone-danger">
          {error}
        </div>
      ) : null}

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={handleConfirm}
          disabled={loading}
          className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-white transition hover:bg-ink/90 disabled:opacity-40"
        >
          {loading ? "Сохраняю…" : "Подтвердить"}
        </button>
        <button
          type="button"
          onClick={onCancelled}
          disabled={loading}
          className="rounded-lg border border-surface-border bg-surface px-4 py-2 text-sm font-medium text-ink-soft transition hover:bg-surface-muted disabled:opacity-40"
        >
          Отменить
        </button>
      </div>
    </div>
  );
}
