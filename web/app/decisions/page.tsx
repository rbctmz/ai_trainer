"use client";

import { useState } from "react";
import useSWR from "swr";
import { ApiError, fetcher, postJSON } from "@/lib/api";
import { redirect } from "next/navigation";
import { showDevTools } from "@/lib/flags";
import type {
  CoachDecisionsResponse,
  CoachDriftReport,
  CoachProposal,
  RecoveryConflictRule,
  RecoveryDecision,
} from "@/lib/types";
import { DecisionEntry } from "@/components/ui/DecisionEntry";
import { ProposalCard } from "@/components/ui/ProposalCard";

const MUTATING_RECOVERY_VARIANTS = new Set(["downgrade_today", "transfer_1_3d"]);

export default function DecisionsPage() {
  // Agent audit log (issue #254): hidden from beta testers unless the dev flag
  // is on. redirect() is not a return, so the hooks below stay unconditional
  // (showDevTools is a build-time constant).
  if (!showDevTools) redirect("/today");

  const { data, error, isLoading, mutate } = useSWR<CoachDecisionsResponse>(
    "/api/decisions?days=30",
    fetcher,
  );
  const [notice, setNotice] = useState<string | null>(null);
  const pendingProposalDays = data?.pending_proposal_days ?? [];
  const recoveryDays = data?.recovery_days ?? [];
  const historyProposalDays = (data?.proposal_days ?? [])
    .map((day) => ({
      ...day,
      proposals: day.proposals.filter((proposal) => proposal.status !== "pending"),
    }))
    .filter((day) => day.proposals.length > 0);
  const pendingProposalCount =
    data?.pending_proposal_count ??
    pendingProposalDays.reduce((total, day) => total + day.proposals.length, 0);

  return (
    <main className="space-y-5">
      <h1 className="text-2xl font-bold text-ink">Решения коуча</h1>

      {isLoading ? <div className="h-40 animate-pulse rounded-card bg-surface" /> : null}
      {error ? (
        <div className="rounded-card border border-tone-danger/30 bg-tone-danger/10 p-4 text-sm text-tone-danger">
          Не удалось загрузить решения. Проверьте, что ./run_web.sh запущен.
        </div>
      ) : null}
      {notice ? (
        <div className="rounded-card border border-tone-success/30 bg-tone-success/10 p-4 text-sm text-tone-success">
          {notice}
        </div>
      ) : null}

      {data?.drift_report ? <DriftReportCard report={data.drift_report} /> : null}

      {data?.has_data ? (
        <div className="space-y-4">
          {pendingProposalDays.length > 0 ? (
            <section className="rounded-card border border-accent/30 bg-accent/10 p-4 shadow-card">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-sm font-semibold uppercase tracking-wide text-accent">
                    Ожидают подтверждения
                  </h2>
                  <p className="mt-1 text-sm text-ink-soft">
                    Эти изменения не попадут в план, пока ты явно не подтвердишь их.
                  </p>
                </div>
                <span className="rounded-full bg-surface/80 px-2 py-1 text-xs font-medium text-ink-soft">
                  {pendingProposalCount}
                </span>
              </div>
              <div className="mt-4 space-y-4">
                {pendingProposalDays.map((day) => (
                  <div key={`pending-${day.date}`} className="space-y-3">
                    <div className="text-xs font-medium uppercase tracking-wide text-ink-faint">
                      {day.date}
                    </div>
                    {day.proposals.map((proposal) => (
                      <ProposalCard
                        key={proposal.id}
                        proposalId={proposal.id}
                        action={proposal.action}
                        status={proposal.status}
                        params={proposal.params}
                        preview={proposal.preview}
                        onConfirmed={(message) => {
                          setNotice(message);
                          void mutate();
                        }}
                        onCancelled={(message) => {
                          setNotice(message ?? "Отклонено: план не изменён.");
                          void mutate();
                        }}
                      />
                    ))}
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          {recoveryDays.map((day) => (
            <section
              key={`recovery-${day.date}`}
              className="rounded-card border border-surface-border bg-surface p-4 shadow-card"
            >
              <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">
                {day.date} · Recovery loop
              </h2>
              <div className="mt-2 divide-y divide-surface-border">
                {day.recovery_decisions.map((decision) => (
                  <RecoveryDecisionEntry key={decision.id} decision={decision} />
                ))}
              </div>
            </section>
          ))}

          {historyProposalDays.map((day) => (
            <section
              key={`proposals-${day.date}`}
              className="rounded-card border border-surface-border bg-surface p-4 shadow-card"
            >
              <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">
                {day.date} · предложения
              </h2>
              <div className="mt-2 divide-y divide-surface-border">
                {day.proposals.map((proposal) => (
                  <ProposalEntry
                    key={proposal.id}
                    proposal={proposal}
                    onChanged={(message) => {
                      setNotice(message);
                      void mutate();
                    }}
                  />
                ))}
              </div>
            </section>
          ))}

          {data.days.map((day) => (
            <section
              key={day.date}
              className="rounded-card border border-surface-border bg-surface p-4 shadow-card"
            >
              <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">
                {day.date}
              </h2>
              <div className="mt-2">
                {day.decisions.map((decision) => (
                  <DecisionEntry key={decision.id} decision={decision} />
                ))}
              </div>
            </section>
          ))}
        </div>
      ) : null}

      {data && !data.has_data ? (
        <div className="rounded-card border border-surface-border bg-surface p-6 text-center text-sm text-ink-soft shadow-card">
          No decisions logged yet
        </div>
      ) : null}
    </main>
  );
}

function DriftReportCard({ report }: { report: CoachDriftReport }) {
  const ready = report.state === "ready";
  return (
    <section className="rounded-card border border-surface-border bg-surface p-4 shadow-card">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">
            Directional drift
          </h2>
          <p className="mt-1 text-sm text-ink-soft">
            {ready
              ? `Проверено связанных изменений: ${report.compared_count}. Противоречий: ${report.mismatch_count}.`
              : `Недостаточно явно связанных применённых изменений для сверки. Подтверждённых no-op: ${report.no_change_count}.`}
          </p>
        </div>
        <span className="rounded-full border border-surface-border px-2 py-1 text-xs font-medium text-ink-soft">
          {ready ? `${report.mismatch_count} drift` : "data gap"}
        </span>
      </div>

      {report.mismatches.length > 0 ? (
        <div className="mt-3 divide-y divide-surface-border border-t border-surface-border">
          {report.mismatches.map((item) => (
            <div key={`${item.decision_id}-${item.proposal_id}`} className="py-3 text-sm">
              <div className="font-medium text-ink">
                Decision #{item.decision_id} {item.decision_type} · proposal #{item.proposal_id} {item.action}
              </div>
              <div className="mt-1 text-ink-soft">
                Checkpoint #{item.base_checkpoint_id} → #{item.applied_checkpoint_id} · {item.total_tss_before} → {item.total_tss_after} TSS ({item.total_tss_delta > 0 ? "+" : ""}{item.total_tss_delta})
              </div>
            </div>
          ))}
        </div>
      ) : null}

      {report.data_gap_count > 0 ? (
        <div className="mt-2 text-xs text-ink-faint">
          Непроверяемых записей: {report.data_gap_count}
        </div>
      ) : null}
    </section>
  );
}

function ProposalEntry({
  proposal,
  onChanged,
}: {
  proposal: CoachProposal;
  onChanged: (message: string) => void;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const label =
    proposal.action === "build_plan"
      ? "Новый план"
      : proposal.action === "recovery_replan"
        ? "Recovery Replan"
        : proposal.action === "create_plan_constraint" /* label */
          ? "Новое ограничение"
          : proposal.action === "retract_plan_constraint" /* label */
            ? "Снятие ограничения"
            : proposal.action === "repair_plan_day" /* label */
              ? "Восстановление дня"
              : "Корректировка плана";
  const goal = proposal.preview?.goal as Record<string, unknown> | undefined;
  const recommended = proposal.preview?.recommended_session as
    | Record<string, unknown>
    | undefined;
  const current = proposal.preview?.current_session as
    | Record<string, unknown>
    | undefined;
  const recoveryResult = proposal.result ?? {};
  const selectedRecoveryKind = String(recoveryResult.selected_kind ?? "downgrade_today");
  const oldSessionId = String(recoveryResult.old_session_id ?? "");
  const newSessionId = String(recoveryResult.new_session_id ?? "");
  const newSessionLabel = String(recoveryResult.new_session_label ?? "");
  const affectedDates = Array.isArray(recoveryResult.affected_dates)
    ? recoveryResult.affected_dates.map(String)
    : [];
  const hasRecoveryNumbers =
    typeof recommended?.tss === "number" &&
    typeof recommended?.duration_minutes === "number" &&
    typeof current?.tss === "number" &&
    typeof current?.duration_minutes === "number";
  const recoverySummary =
    selectedRecoveryKind === "keep"
      ? "План оставлен без изменений"
      : selectedRecoveryKind === "transfer_1_3d"
        ? [newSessionLabel, affectedDates.join(" → ")].filter(Boolean).join(" · ")
        : hasRecoveryNumbers
          ? `${String(recommended?.name ?? "Снижение нагрузки")} · ${recommended?.tss} TSS · ${recommended?.duration_minutes} мин (было ${current?.tss} TSS · ${current?.duration_minutes} мин)`
          : `${String(recommended?.name ?? "Снижение нагрузки")} · ${String(recommended?.tss ?? "—")} TSS`;
  // Identity handoff stays available as evidence (tooltip), never the main summary text.
  const transferIdentityTitle =
    selectedRecoveryKind === "transfer_1_3d" && oldSessionId && newSessionId
      ? oldSessionId + " → " + newSessionId
      : undefined;
  const canRollbackRecovery =
    proposal.action === "recovery_replan"
    && proposal.status === "approved"
    && MUTATING_RECOVERY_VARIANTS.has(selectedRecoveryKind);
  const summary =
    proposal.action === "build_plan"
      ? [
          String(goal?.goal_type ?? proposal.params.goal_type ?? ""),
          String(goal?.distance ?? proposal.params.distance ?? ""),
        ]
          .filter(Boolean)
          .join(" • ")
      : proposal.action === "recovery_replan"
        ? recoverySummary
        : proposal.action === "create_plan_constraint"
          ? [
              String(proposal.preview.date ?? proposal.params.date ?? ""),
              String(proposal.preview.sport ?? proposal.params.sport ?? "весь день"),
              String(proposal.preview.note ?? proposal.params.note ?? ""),
            ].filter(Boolean).join(" • ")
          : proposal.action === "retract_plan_constraint"
            ? `${String(proposal.preview.date ?? proposal.params.date ?? "")} • constraint #${String(proposal.params.constraint_id ?? "—")}`
            : proposal.action === "repair_plan_day"
              ? `${String(proposal.preview.date ?? proposal.params.date ?? "")} • восстановление из версии #${String(proposal.preview.donor_checkpoint_id ?? "—")}`
              : String(proposal.preview.adjustment_label ?? proposal.preview.adjustment_status ?? "");

  async function handleRollback() {
    setLoading(true);
    setError(null);
    try {
      await postJSON(`/api/decisions/proposals/${proposal.id}/rollback`, {});
      onChanged("Recovery Replan откатан: предыдущая версия плана снова активна.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось откатить Recovery Replan");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="py-3 text-sm">
      <div className="flex items-center justify-between gap-3">
        <div className="font-medium text-ink">{label}</div>
        <span className="rounded-full border border-surface-border px-2 py-0.5 text-xs text-ink-soft">
          {proposal.status}
        </span>
      </div>
      {summary ? (
        <div className="mt-1 text-ink-soft" title={transferIdentityTitle}>
          {summary}
        </div>
      ) : null}
      <div className="mt-1 text-xs text-ink-faint">
        {proposal.time || proposal.date}
      </div>
      {canRollbackRecovery ? (
        <button
          type="button"
          onClick={handleRollback}
          disabled={loading}
          className="mt-2 rounded-lg border border-surface-border px-3 py-1.5 text-xs font-medium text-ink-soft hover:bg-surface-muted disabled:opacity-40"
        >
          {loading ? "Откатываю…" : "Откатить Recovery Replan"}
        </button>
      ) : null}
      {error ? <div className="mt-2 text-xs text-tone-danger">{error}</div> : null}
    </div>
  );
}

// Fallback for API payloads that predate `conflict_rules`: derive the same
// deduped severity·rule projection the API now ships, so a rule that recurs
// across several days never renders as repeated identical lines.
function deriveConflictRules(rawConflicts: unknown): RecoveryConflictRule[] {
  if (!Array.isArray(rawConflicts)) return [];
  const seen = new Set<string>();
  const rules: RecoveryConflictRule[] = [];
  for (const item of rawConflicts) {
    if (!item || typeof item !== "object") continue;
    const conflict = item as Record<string, unknown>;
    const severity = String(conflict.severity ?? "");
    const kind = String(conflict.kind ?? "readiness conflict");
    const key = `${severity} ${kind}`;
    if (seen.has(key)) continue;
    seen.add(key);
    rules.push({ severity, kind });
  }
  return rules;
}

function RecoveryDecisionEntry({ decision }: { decision: RecoveryDecision }) {
  const report = decision.report ?? {};
  const readiness = (report.readiness as Record<string, unknown> | undefined) ?? {};
  const conflictRules = decision.conflict_rules ?? deriveConflictRules(report.conflicts);
  const outcomeLabel =
    decision.outcome === "conflict"
      ? "Конфликт"
      : decision.outcome === "data_gap"
        ? "Недостаточно данных"
        : "Без вмешательства";
  const toneClass =
    decision.outcome === "conflict"
      ? "text-tone-warning"
      : decision.outcome === "data_gap"
        ? "text-ink-soft"
        : "text-tone-success";

  return (
    <div className="py-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className={`font-medium ${toneClass}`}>{outcomeLabel}</div>
        <div className="text-xs text-ink-faint">{decision.time || decision.date}</div>
      </div>
      <p className="mt-1 text-ink-soft">{decision.reason}</p>
      <div className="mt-1 text-xs text-ink-faint">
        Readiness {String(readiness.score ?? "—")} · {String(readiness.status ?? "unknown")} · confidence {String(readiness.confidence ?? "—")}
      </div>
      {conflictRules.length > 0 ? (
        <div className="mt-2 text-xs text-ink-soft">
          {conflictRules.map((rule, index) => (
            <div key={`${decision.id}-${index}`}>
              {rule.severity} · {rule.kind || "readiness conflict"}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
