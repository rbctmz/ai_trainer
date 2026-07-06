"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { CoachDecisionsResponse, CoachProposal } from "@/lib/types";
import { DecisionEntry } from "@/components/ui/DecisionEntry";
import { ProposalCard } from "@/components/ui/ProposalCard";

export default function DecisionsPage() {
  const { data, error, isLoading, mutate } = useSWR<CoachDecisionsResponse>(
    "/api/decisions?days=30",
    fetcher,
  );
  const [notice, setNotice] = useState<string | null>(null);
  const pendingProposalDays = data?.pending_proposal_days ?? [];
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
                  <ProposalEntry key={proposal.id} proposal={proposal} />
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

function ProposalEntry({ proposal }: { proposal: CoachProposal }) {
  const label =
    proposal.action === "build_plan" ? "Новый план" : "Корректировка плана";
  const goal = proposal.preview?.goal as Record<string, unknown> | undefined;
  const summary =
    proposal.action === "build_plan"
      ? [
          String(goal?.goal_type ?? proposal.params.goal_type ?? ""),
          String(goal?.distance ?? proposal.params.distance ?? ""),
        ]
          .filter(Boolean)
          .join(" • ")
      : String(proposal.preview.adjustment_label ?? proposal.preview.adjustment_status ?? "");

  return (
    <div className="py-3 text-sm">
      <div className="flex items-center justify-between gap-3">
        <div className="font-medium text-ink">{label}</div>
        <span className="rounded-full border border-surface-border px-2 py-0.5 text-xs text-ink-soft">
          {proposal.status}
        </span>
      </div>
      {summary ? <div className="mt-1 text-ink-soft">{summary}</div> : null}
      <div className="mt-1 text-xs text-ink-faint">
        {proposal.time || proposal.date}
      </div>
    </div>
  );
}
