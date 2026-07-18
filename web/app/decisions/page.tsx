"use client";

import { useState } from "react";
import useSWR from "swr";
import { ApiError, fetcher, postJSON } from "@/lib/api";
import type { CoachDecisionsResponse, CoachProposal, RecoveryDecision } from "@/lib/types";
import { DecisionEntry } from "@/components/ui/DecisionEntry";
import { ProposalCard } from "@/components/ui/ProposalCard";

const MUTATING_RECOVERY_VARIANTS = new Set(["downgrade_today", "transfer_1_3d"]);

export default function DecisionsPage() {
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
        : "Корректировка плана";
  const goal = proposal.preview?.goal as Record<string, unknown> | undefined;
  const recommended = proposal.preview?.recommended_session as
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
  const recoverySummary =
    selectedRecoveryKind === "keep"
      ? "План оставлен без изменений"
      : selectedRecoveryKind === "transfer_1_3d"
        ? [newSessionLabel, affectedDates.join(" → ")].filter(Boolean).join(" · ")
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

function RecoveryDecisionEntry({ decision }: { decision: RecoveryDecision }) {
  const report = decision.report ?? {};
  const readiness = (report.readiness as Record<string, unknown> | undefined) ?? {};
  const conflicts = Array.isArray(report.conflicts)
    ? report.conflicts.filter(
        (item): item is Record<string, unknown> => !!item && typeof item === "object",
      )
    : [];
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
      {conflicts.length > 0 ? (
        <div className="mt-2 text-xs text-ink-soft">
          {conflicts.map((conflict, index) => (
            <div key={`${decision.id}-${index}`}>
              {String(conflict.severity ?? "")} · {String(conflict.kind ?? "readiness conflict")}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
