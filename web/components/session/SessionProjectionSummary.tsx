"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { SessionProjection } from "@/lib/types";

const STATUS_LABELS: Record<SessionProjection["projection_status"], string> = {
  matched: "сопоставлено",
  partial: "выполнено частично",
  needs_confirmation: "нужно уточнить",
  unmatched: "факт не найден",
  data_gap: "данных недостаточно",
};

function loadLabel(value: number | null): string {
  return value == null ? "—" : `${Math.round(value)} TSS`;
}

export function SessionProjectionSummary({
  sessionId,
  projection: suppliedProjection,
  compact = false,
}: {
  sessionId: string | null | undefined;
  projection?: SessionProjection | null;
  compact?: boolean;
}) {
  const shouldFetch = Boolean(sessionId) && suppliedProjection === undefined;
  // api-contract: manual: /api/planning/session-projection/{session_id}
  const { data, error, isLoading } = useSWR<SessionProjection>(
    shouldFetch
      ? `/api/planning/session-projection/${encodeURIComponent(sessionId ?? "")}`
      : null,
    fetcher,
  );
  const projection = suppliedProjection ?? data ?? null;

  if (!sessionId && !projection) return null;
  if (isLoading && !projection) {
    return <p className="mt-2 text-xs text-ink-faint">Сверяем план и факт…</p>;
  }
  if (error || !projection) {
    return (
      <p className="mt-2 text-xs text-ink-faint">
        Единая проекция план/факт пока недоступна.
      </p>
    );
  }

  const extraLoad =
    projection.load.other_matched_tss + projection.load.additional_unmatched_tss;

  return (
    <div
      data-session-projection={projection.session_id}
      className={`${compact ? "mt-2 px-2.5 py-2" : "mt-3 p-3"} rounded-lg border border-surface-border bg-surface-muted/40`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <span className="font-medium text-ink">План → факт</span>
        <span className="text-ink-soft">{STATUS_LABELS[projection.projection_status]}</span>
      </div>
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs tabular-nums text-ink-soft">
        <span>план {loadLabel(projection.load.planned_tss)}</span>
        <span>эта сессия {loadLabel(projection.load.matched_tss)}</span>
        <span>итог дня {loadLabel(projection.load.day_total_tss)}</span>
        {extraLoad > 0 ? <span>другая нагрузка +{Math.round(extraLoad)} TSS</span> : null}
      </div>
      {!compact ? (
        <details className="mt-2 text-[11px] text-ink-faint">
          <summary className="cursor-pointer">Источник и ревизия</summary>
          <div className="mt-1 break-all">
            session {projection.session_id} · checkpoint {projection.evidence_revision.planning_checkpoint_id ?? "—"}
            {projection.evidence_revision.match_revision != null
              ? ` · match r${projection.evidence_revision.match_revision}`
              : ""}
            {projection.evidence_revision.feedback_revision != null
              ? ` · feedback r${projection.evidence_revision.feedback_revision}`
              : ""}
          </div>
        </details>
      ) : null}
    </div>
  );
}
