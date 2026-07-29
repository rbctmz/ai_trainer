"use client";

import { useState } from "react";
import { ApiError, postJSON } from "@/lib/api";
import type { AdjustResult, BuiltPlan, CoachProposalAction, RebalanceConfirmResult } from "@/lib/types";

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
  base_checkpoint_id?: number;
  preview_fingerprint?: string;
  as_of?: string;
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
  result: BuiltPlan | AdjustResult | RebalanceConfirmResult | RecoveryReplanResult;
}

type RecoveryVariantKind = "keep" | "downgrade_today" | "transfer_1_3d";

interface RecoveryReplanResult {
  selected_kind: RecoveryVariantKind;
  plan_id?: string | null;
  rollback_checkpoint_id?: number | null;
  near_term_edit?: { compact_label?: string };
  totals?: { peak_tss: number; total_tss: number };
  old_session_id?: string;
  new_session_id?: string;
  affected_dates?: string[];
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

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

const RECOVERY_VARIANT_LABELS: Record<RecoveryVariantKind, string> = {
  keep: "Оставить как есть",
  downgrade_today: "Снизить нагрузку сегодня",
  transfer_1_3d: "Перенести на 1–3 дня",
};

const RECOVERY_REJECTION_LABELS: Record<string, string> = {
  unavailable: "день недоступен",
  protected: "защищённая дата",
  hard_collision: "уже есть тяжёлая сессия",
  recovery_spacing: "недостаточно восстановления",
  occasion_limit: "слишком много сессий в день",
  day_tss_ceiling: "превышен дневной TSS",
  day_duration_ceiling: "превышена длительность дня",
  cross_week_boundary: "перенос через границу недели запрещён",
};

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
    base_checkpoint_id: params.base_checkpoint_id != null ? asNumber(params.base_checkpoint_id) : undefined,
    preview_fingerprint: params.preview_fingerprint ? asString(params.preview_fingerprint) : undefined,
    as_of: params.as_of ? asString(params.as_of) : undefined,
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

function adjustConfirmedMessage(result: AdjustResult | RebalanceConfirmResult): string {
  if (!("adjustment" in result)) {
    return [
      "✅ Future-only пересборка применена.",
      `Δ ${result.preview.future_tss_delta} TSS`,
      `checkpoint #${result.applied_checkpoint_id}`,
    ].join(" ");
  }
  return [
    "✅ Корректировка плана применена.",
    result.adjustment.label,
    `пик ${result.totals.peak_tss} TSS`,
  ].join(" ");
}

function keepConfirmedMessage(): string {
  return "✅ Решение сохранено: план оставлен без изменений.";
}

function transferConfirmedMessage(result: RecoveryReplanResult): string {
  const dates = (result.affected_dates ?? []).join(" → ");
  return [
    "✅ Ключевая сессия перенесена.",
    dates ? `Даты: ${dates}.` : "",
    result.old_session_id && result.new_session_id
      ? `Identity: ${result.old_session_id} → ${result.new_session_id}.`
      : "",
  ].filter(Boolean).join(" ");
}

function downgradeConfirmedMessage(result: RecoveryReplanResult): string {
  return [
    "✅ Recovery Replan применён.",
    result.near_term_edit?.compact_label ?? "Ближняя нагрузка снижена.",
    result.rollback_checkpoint_id != null
      ? `Откат к checkpoint #${result.rollback_checkpoint_id} доступен в истории решений.`
      : "",
  ].filter(Boolean).join(" ");
}

function recoveryConfirmedMessage(result: RecoveryReplanResult): string {
  if (result.selected_kind === "keep") return keepConfirmedMessage();
  if (result.selected_kind === "transfer_1_3d") return transferConfirmedMessage(result);
  return downgradeConfirmedMessage(result);
}

function sessionLabel(session: Record<string, unknown>): string {
  const name = asString(session.name || session.template_name || session.sport_label || "Сессия");
  const tss = session.tss ?? session.total_tss;
  return tss == null ? name : `${name} · ${asNumber(tss)} TSS`;
}

function daySessionsLabel(value: unknown): string {
  const sessions = asRecordList(value);
  if (sessions.length === 0) return "нет тренировки";
  return sessions.map(sessionLabel).join(" + ");
}

function isRecoveryVariantKind(value: unknown): value is RecoveryVariantKind {
  return value === "keep" || value === "downgrade_today" || value === "transfer_1_3d";
}

function confirmLabel(kind: RecoveryVariantKind): string {
  return kind === "keep"
    ? "Оставить план"
    : kind === "transfer_1_3d"
      ? "Подтвердить перенос"
      : "Подтвердить снижение";
}

function signedDelta(value: unknown, unit: string): string {
  if (value == null) return "не меняется по этому варианту";
  const number = asNumber(value);
  return `${number > 0 ? "+" : ""}${number} ${unit}`;
}

function readinessLabel(whyIntervene: Record<string, unknown>): string {
  const readiness = asRecord(whyIntervene.readiness);
  const score = readiness.score == null ? "—" : asString(readiness.score);
  const status = asString(readiness.status || "unknown");
  return `${score}/100 · ${status}`;
}

function conflictLabel(whyIntervene: Record<string, unknown>): string {
  const conflict = asRecord(whyIntervene.conflict);
  return [conflict.date, conflict.sport_label, conflict.role, conflict.tss != null ? `${conflict.tss} TSS` : null]
    .filter(Boolean)
    .map(asString)
    .join(" · ");
}

function variantDescription(
  variant: Record<string, unknown>,
  currentSession: Record<string, unknown>,
  recommendedSession: Record<string, unknown>,
): string {
  const kind = asString(variant.kind);
  if (kind === "keep") return sessionLabel(asRecord(variant.session || currentSession));
  if (kind === "downgrade_today") {
    return sessionLabel(asRecord(variant.session || recommendedSession));
  }
  return `${asString(variant.source_date)} → ${asString(variant.target_date)}`;
}

function candidateLabel(candidate: Record<string, unknown>): string {
  const reasons = Array.isArray(candidate.rejected_reasons)
    ? candidate.rejected_reasons.map((reason) => RECOVERY_REJECTION_LABELS[asString(reason)] ?? asString(reason))
    : [];
  return `${asString(candidate.date)} · ${candidate.eligible ? "подходит" : reasons.join(", ")}`;
}

function mutationLabel(protection: Record<string, unknown>): string {
  return protection.mutates_plan ? "План изменится только после подтверждения" : "План не изменяется";
}

function variantCardClass(selected: boolean): string {
  return selected
    ? "border-accent bg-accent/10"
    : "border-surface-border bg-surface/70 hover:bg-surface-muted";
}

function variantRadioClass(selected: boolean): string {
  return selected ? "border-accent bg-accent" : "border-surface-border bg-surface";
}

function safeRecoveryVariants(
  raw: Record<string, unknown>[],
  currentSession: Record<string, unknown>,
  recommendedSession: Record<string, unknown>,
): Record<string, unknown>[] {
  const available = raw.filter((item) => isRecoveryVariantKind(item.kind));
  if (available.length > 0) return available;
  return [{ kind: "downgrade_today", session: recommendedSession, current_session: currentSession }];
}

function recommendedRecoveryKind(
  whatChanges: Record<string, unknown>,
  availableRecoveryVariants: Record<string, unknown>[],
): RecoveryVariantKind {
  const recommended = whatChanges.recommended_kind;
  if (
    isRecoveryVariantKind(recommended)
    && availableRecoveryVariants.some((item) => item.kind === recommended)
  ) {
    return recommended;
  }
  const marked = availableRecoveryVariants.find((item) => item.recommended);
  return isRecoveryVariantKind(marked?.kind) ? marked.kind : "downgrade_today";
}

function variantProtection(
  whatIsProtected: Record<string, unknown>,
  kind: RecoveryVariantKind,
  preview: Record<string, unknown>,
): Record<string, unknown> {
  const byVariant = asRecord(whatIsProtected.by_variant);
  const explicit = asRecord(byVariant[kind]);
  if (Object.keys(explicit).length > 0) return explicit;
  if (kind === "keep") {
    return { weekly_tss_delta: 0, weekly_duration_delta_minutes: 0, mutates_plan: false };
  }
  return {
    weekly_tss_delta: kind === "transfer_1_3d" ? 0 : preview.total_delta_tss,
    weekly_duration_delta_minutes: kind === "transfer_1_3d" ? 0 : null,
    mutates_plan: true,
  };
}

function recoveryEvidenceItems(
  whyIntervene: Record<string, unknown>,
  preview: Record<string, unknown>,
): string[] {
  return asStringArray(whyIntervene.evidence) ?? asStringArray(preview.evidence) ?? [];
}

function transferDayChanges(selectedVariant: Record<string, unknown>): Record<string, unknown>[] {
  return asRecordList(selectedVariant.day_changes);
}

function selectedRecoveryVariant(
  availableRecoveryVariants: Record<string, unknown>[],
  selectedVariantKind: RecoveryVariantKind,
): Record<string, unknown> {
  return availableRecoveryVariants.find((item) => item.kind === selectedVariantKind) ?? {};
}

function recoveryCandidates(whatIsProtected: Record<string, unknown>): Record<string, unknown>[] {
  return asRecordList(whatIsProtected.candidates);
}

function recoveryReason(whyIntervene: Record<string, unknown>, preview: Record<string, unknown>): string {
  return asString(whyIntervene.reason || preview.reason);
}

function recoverySeverity(whyIntervene: Record<string, unknown>, preview: Record<string, unknown>): string {
  return asString(whyIntervene.severity || preview.severity || "не определено");
}

function recoveryProtectionSummary(selectedProtection: Record<string, unknown>): string[] {
  return [
    `Недельный TSS: ${signedDelta(selectedProtection.weekly_tss_delta, "TSS")}`,
    `Длительность недели: ${signedDelta(selectedProtection.weekly_duration_delta_minutes, "мин")}`,
    mutationLabel(selectedProtection),
  ];
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
  const [showEvidence, setShowEvidence] = useState(false);

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
  const whyIntervene = asRecord(preview.why_intervene);
  const whatChanges = asRecord(preview.what_changes);
  const whatIsProtected = asRecord(preview.what_is_protected);
  const availableRecoveryVariants = safeRecoveryVariants(
    asRecordList(whatChanges.variants ?? preview.variants),
    currentSession,
    recommendedSession,
  );
  const recommendedKind = recommendedRecoveryKind(whatChanges, availableRecoveryVariants);
  const [selectedVariantKind, setSelectedVariantKind] = useState<RecoveryVariantKind>(recommendedKind);
  const [selectedProposalId, setSelectedProposalId] = useState(proposalId);
  const effectiveSelectedVariantKind =
    selectedProposalId === proposalId &&
    availableRecoveryVariants.some((item) => item.kind === selectedVariantKind)
      ? selectedVariantKind
      : recommendedKind;
  const selectedVariant = selectedRecoveryVariant(
    availableRecoveryVariants,
    effectiveSelectedVariantKind,
  );
  const selectedProtection = variantProtection(
    whatIsProtected,
    effectiveSelectedVariantKind,
    preview,
  );
  const recoveryEvidence = recoveryEvidenceItems(whyIntervene, preview);
  const candidates = recoveryCandidates(whatIsProtected);

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
        const params = new URLSearchParams();
        params.set("variant_kind", effectiveSelectedVariantKind);
        const response = await postJSON<ProposalApprovalResponse>(
          `/api/decisions/proposals/${proposalId}/approve?${params.toString()}`,
          {},
        );
        onConfirmed(recoveryConfirmedMessage(response.result as RecoveryReplanResult));
        return;
      }

      const response = await postJSON<ProposalApprovalResponse>(
        `/api/decisions/proposals/${proposalId}/approve`,
        {},
      );
      onConfirmed(adjustConfirmedMessage(response.result as AdjustResult | RebalanceConfirmResult));
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
          <section className="mt-3 rounded-lg bg-surface/60 px-3 py-3">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-soft">
              Почему вмешиваемся
            </h3>
            <p className="mt-1 text-sm text-ink">{recoveryReason(whyIntervene, preview)}</p>
            <div className="mt-1 text-xs text-ink-soft">
              Готовность {readinessLabel(whyIntervene)} · риск {recoverySeverity(whyIntervene, preview)}
            </div>
            {conflictLabel(whyIntervene) ? (
              <div className="mt-1 text-xs text-ink-faint">{conflictLabel(whyIntervene)}</div>
            ) : null}
          </section>

          <section className="mt-3">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-soft">
              Что меняется
            </h3>
            <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
              {availableRecoveryVariants.map((variant) => {
                const kind = variant.kind as RecoveryVariantKind;
                const selected = kind === effectiveSelectedVariantKind;
                return (
                  <button
                    key={kind}
                    type="button"
                    onClick={() => {
                      setSelectedProposalId(proposalId);
                      setSelectedVariantKind(kind);
                    }}
                    aria-pressed={selected}
                    className={`rounded-lg border px-3 py-2 text-left transition ${variantCardClass(selected)}`}
                  >
                    <span className="flex items-center gap-2 text-sm font-medium text-ink">
                      <span className={`h-3 w-3 rounded-full border ${variantRadioClass(selected)}`} />
                      {RECOVERY_VARIANT_LABELS[kind]}
                    </span>
                    <span className="mt-1 block text-xs text-ink-soft">
                      {variantDescription(variant, currentSession, recommendedSession)}
                    </span>
                    {kind === recommendedKind ? (
                      <span className="mt-1 block text-[11px] font-medium text-tone-success">
                        Рекомендовано
                      </span>
                    ) : null}
                  </button>
                );
              })}
            </div>

            {effectiveSelectedVariantKind === "transfer_1_3d" ? (
              <div className="mt-2 space-y-2">
                {transferDayChanges(selectedVariant).map((change) => (
                  <div key={asString(change.date)} className="rounded-lg bg-surface/70 px-3 py-2 text-xs">
                    <div className="font-medium text-ink">{asString(change.date)}</div>
                    <div className="mt-1 text-ink-soft">
                      {daySessionsLabel(change.before_sessions)} → {daySessionsLabel(change.after_sessions)}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="mt-2 rounded-lg bg-surface/70 px-3 py-2 text-sm text-ink-soft">
                {effectiveSelectedVariantKind === "keep"
                  ? sessionLabel(asRecord(selectedVariant.session || currentSession))
                  : `${sessionLabel(currentSession)} → ${sessionLabel(asRecord(selectedVariant.session || recommendedSession))}`}
              </div>
            )}
          </section>

          <section className="mt-3 rounded-lg border border-tone-success/20 bg-tone-success/5 px-3 py-3">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-tone-success">
              Что защищено
            </h3>
            <ul className="mt-2 space-y-1 text-xs text-ink-soft">
              {recoveryProtectionSummary(selectedProtection).map((item) => (
                <li key={item}>• {item}</li>
              ))}
            </ul>
            <button
              type="button"
              onClick={() => setShowEvidence((value) => !value)}
              aria-expanded={showEvidence}
              className="mt-2 text-xs font-medium text-accent hover:underline"
            >
              {showEvidence ? "Скрыть доказательства" : "Показать доказательства"}
            </button>
            {showEvidence ? (
              <div className="mt-2 space-y-2 border-t border-surface-border pt-2 text-xs text-ink-soft">
                {recoveryEvidence.length > 0 ? (
                  <ul className="space-y-1">
                    {recoveryEvidence.map((item) => (
                      <li key={item}>• {item}</li>
                    ))}
                  </ul>
                ) : null}
                {candidates.length > 0 ? (
                  <div>
                    <div className="font-medium text-ink">Проверенные даты</div>
                    <ul className="mt-1 space-y-1">
                      {candidates.map((candidate) => (
                        <li key={asString(candidate.date)}>• {candidateLabel(candidate)}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            ) : null}
          </section>
          <p className="mt-3 text-xs text-ink-faint">
            Никакой вариант не применяется автоматически. Подтверждение относится только к выбранному варианту.
          </p>
        </>
      ) : (
        <>
          <ul className="mt-3 space-y-1 text-sm text-ink-soft">
            <li>Недель для пересборки: {adjustParams?.weeks ?? "—"}</li>
            {preview.coverage != null ? (
              <li>
                Evidence coverage: {Math.round(asNumber(preview.coverage) * 100)}% · matched {asNumber(preview.matched_count)}/{asNumber(preview.planned_session_count)}
              </li>
            ) : null}
            {preview.adjustment_label || preview.adjustment_status ? (
              <li>Статус: {asString(preview.adjustment_label || preview.adjustment_status)}</li>
            ) : null}
            {preview.reason ? <li>Причина: {asString(preview.reason)}</li> : null}
            {preview.missed_sessions != null ? (
              <li>Пропущено сессий: {asNumber(preview.missed_sessions)}</li>
            ) : null}
          </ul>

          {Array.isArray(preview.changes) && preview.changes.length > 0 ? (
            <div className="mt-3 space-y-2">
              {asRecordList(preview.changes).map((item) => (
                <div key={asString(item.session_id)} className="flex justify-between rounded-lg bg-surface/70 px-3 py-2 text-sm">
                  <span>{asString(item.date)} · easy</span>
                  <span>{asNumber(item.before_tss)} → {asNumber(item.after_tss)} TSS</span>
                </div>
              ))}
              <p className="text-xs text-ink-faint">Прошлое, сегодня и protected dates не меняются.</p>
            </div>
          ) : null}

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
          {loading
            ? "Сохраняю…"
            : action === "recovery_replan"
              ? confirmLabel(effectiveSelectedVariantKind)
              : "Подтвердить"}
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
