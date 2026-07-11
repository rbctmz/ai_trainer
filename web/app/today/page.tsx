"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { TodayResponse } from "@/lib/types";
import { ProposalCard } from "@/components/ui/ProposalCard";

const STATE_META: Record<
  string,
  { title: string; icon: string; tone: string }
> = {
  silence: { title: "План в силе", icon: "✓", tone: "text-tone-success" },
  conflict: { title: "Есть предложение", icon: "!", tone: "text-tone-warning" },
  data_gap: { title: "Данных недостаточно", icon: "…", tone: "text-ink-soft" },
  no_plan: { title: "Плана нет", icon: "→", tone: "text-ink-soft" },
};

function formatHumanDate(iso: string): string {
  try {
    const formatted = new Intl.DateTimeFormat("ru-RU", {
      weekday: "long",
      day: "numeric",
      month: "long",
    }).format(new Date(`${iso}T00:00:00`));
    return formatted.charAt(0).toUpperCase() + formatted.slice(1);
  } catch {
    return iso;
  }
}

export default function TodayPage() {
  const { data, error, isLoading, mutate } = useSWR<TodayResponse>(
    "/api/today",
    fetcher,
  );
  const [notice, setNotice] = useState<string | null>(null);

  const state = data?.state ?? "silence";
  const meta = STATE_META[state] ?? STATE_META.silence;
  const readiness = data?.readiness ?? null;
  const session = data?.session ?? null;
  const proposal = data?.pending_proposal ?? null;
  const yesterday = data?.yesterday ?? null;

  return (
    <main className="mx-auto max-w-2xl space-y-5">
      {isLoading ? <div className="h-48 animate-pulse rounded-card bg-surface" /> : null}
      {error ? (
        <div className="rounded-card border border-tone-danger/30 bg-tone-danger/10 p-4 text-sm text-tone-danger">
          Не удалось загрузить «Сегодня». Проверьте, что ./run_web.sh запущен.
        </div>
      ) : null}
      {notice ? (
        <div className="rounded-card border border-tone-success/30 bg-tone-success/10 p-4 text-sm text-tone-success">
          {notice}
        </div>
      ) : null}

      {data ? (
        <>
          <header>
            <p className="text-sm text-ink-faint">{formatHumanDate(data.date)}</p>
            <div className="mt-1 flex items-center gap-2">
              <span className={`text-xl font-bold ${meta.tone}`}>{meta.icon}</span>
              <h1 className="text-2xl font-bold text-ink">{meta.title}</h1>
            </div>
            {data.reason ? (
              <p className="mt-1 text-sm text-ink-soft">{data.reason}</p>
            ) : null}
          </header>

          {state === "no_plan" ? (
            <div className="rounded-card border border-surface-border bg-surface p-6 text-center shadow-card">
              <p className="text-sm text-ink-soft">
                Построй план — и этот экран каждое утро будет отвечать на вопрос
                «что сегодня делать?».
              </p>
              <Link
                href="/planning"
                className="mt-3 inline-block rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-foreground"
              >
                Открыть планирование
              </Link>
            </div>
          ) : null}

          {state === "conflict" && proposal ? (
            <ProposalCard
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
          ) : null}

          {state !== "no_plan" ? (
            <section className="rounded-card border border-surface-border bg-surface p-4 shadow-card">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-faint">
                Сегодня по плану
              </h2>
              {session ? (
                <div className="mt-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-lg font-semibold text-ink">{session.name}</span>
                    {session.is_key ? (
                      <span className="rounded-full bg-accent/10 px-2 py-0.5 text-xs font-medium text-accent">
                        ключевая
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-0.5 text-sm text-ink-soft">
                    {[session.role_label, session.sport_label, `${session.tss} TSS`]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>
              ) : (
                <p className="mt-1 text-sm text-ink-soft">
                  Плановой сессии нет — день отдыха.
                </p>
              )}
            </section>
          ) : null}

          {readiness ? (
            <details className="rounded-card border border-surface-border bg-surface p-4 shadow-card">
              <summary className="cursor-pointer text-sm font-medium text-ink">
                Готовность {Math.round(readiness.score)}/100
                <span className="ml-2 text-xs font-normal text-ink-faint">
                  почему — {readiness.drivers.length || readiness.factors.length} факторов
                </span>
              </summary>
              <div className="mt-3 space-y-1.5 text-sm text-ink-soft">
                {(readiness.drivers.length > 0 ? readiness.drivers : readiness.factors).map(
                  (item, index) => {
                    const evidence = String(
                      (item as Record<string, unknown>).evidence ?? "",
                    );
                    return evidence ? <p key={index}>• {evidence}</p> : null;
                  },
                )}
                {readiness.tsb &&
                readiness.tsb.tsb != null &&
                !(readiness.drivers.length > 0 ? readiness.drivers : readiness.factors).some(
                  (item) => (item as Record<string, unknown>).key === "tsb",
                ) ? (
                  <p>
                    • TSB {readiness.tsb.tsb} (CTL {readiness.tsb.ctl ?? "—"}, окно{" "}
                    {readiness.tsb.window_days} дн.)
                  </p>
                ) : null}
                {readiness.confidence != null ? (
                  <p className="text-xs text-ink-faint">
                    confidence {readiness.confidence}
                    {readiness.stale ? " · данные устарели" : ""}
                  </p>
                ) : null}
              </div>
            </details>
          ) : null}

          {yesterday ? (
            <p className="border-t border-surface-border pt-3 text-sm text-ink-faint">
              Вчера: {yesterday.activities}{" "}
              {yesterday.activities === 1 ? "активность" : "активности"} ·{" "}
              {yesterday.minutes} мин · {yesterday.tss} TSS
              {yesterday.sports.length ? ` · ${yesterday.sports.join(", ")}` : ""}
            </p>
          ) : null}
        </>
      ) : null}
    </main>
  );
}
