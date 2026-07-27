"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { fetcher, postJSON } from "@/lib/api";
import { syncSourceLabel } from "@/lib/sourceLabels";
import {
  SyncJobResponse,
  SyncProvidersResponse,
  SyncProviderTestResponse,
  SyncSource,
} from "@/lib/types";

type SyncControlProps = {
  onDone: () => void;
  detailed?: boolean;
};

export function SyncControl({ onDone, detailed = false }: SyncControlProps) {
  const { data, error } = useSWR<SyncProvidersResponse>("/api/sync/providers", fetcher);
  const { mutate } = useSWRConfig();
  const [selectedSource, setSelectedSource] = useState<SyncSource | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [probeMessage, setProbeMessage] = useState<string | null>(null);

  useEffect(() => {
    if (data && selectedSource === null) {
      setSelectedSource(data.recommended_source);
    }
  }, [data, selectedSource]);

  const selectedProvider = useMemo(
    () => data?.providers.find((provider) => provider.source === selectedSource) ?? null,
    [data, selectedSource],
  );
  const hasConfiguredProvider = Boolean(data?.providers.some((provider) => provider.configured));
  const canSync = Boolean(selectedProvider?.configured && !busy);

  async function sync() {
    if (!selectedSource || !selectedProvider?.configured) return;
    setBusy(true);
    setMessage(null);
    try {
      const started = await postJSON<SyncJobResponse>("/api/sync", { source: selectedSource });
      setMessage(formatSyncJob(started, selectedSource));
      const final = isTerminalSyncState(started.sync_state)
        ? started
        : await waitForSyncJob((next) => setMessage(formatSyncJob(next, selectedSource)));
      setMessage(formatSyncJob(final, selectedSource));
      if (final.sync_state === "failed") {
        throw new Error(formatSyncJob(final, selectedSource));
      }
      onDone();
      mutate(() => true);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Ошибка синхронизации");
    } finally {
      setBusy(false);
      window.setTimeout(() => setMessage(null), 6000);
    }
  }

  async function testIntervalsConnection() {
    setProbeMessage(null);
    try {
      const result = await postJSON<SyncProviderTestResponse>("/api/sync/providers/intervals/test", {});
      const calendars =
        result.calendar_count === null ? "" : ` · календарей: ${result.calendar_count}`;
      setProbeMessage(`Intervals.icu доступен${calendars}`);
    } catch (caught) {
      setProbeMessage(
        caught instanceof Error ? caught.message : "Не удалось проверить Intervals.icu",
      );
    }
  }

  if (detailed) {
    return (
      <div className="mt-5 space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          {data?.providers.map((provider) => {
            const selected = provider.source === selectedSource;
            return (
              <button
                key={provider.source}
                type="button"
                onClick={() => setSelectedSource(provider.source)}
                className={[
                  "rounded-xl border p-4 text-left transition",
                  selected
                    ? "border-accent bg-accent/10"
                    : "border-surface-border bg-surface-muted hover:border-ink-faint",
                ].join(" ")}
                aria-pressed={selected}
              >
                <span className="block text-sm font-semibold text-ink">{provider.label}</span>
                <span
                  className={[
                    "mt-1 block text-xs",
                    provider.configured ? "text-tone-success" : "text-ink-faint",
                  ].join(" ")}
                >
                  {provider.configured ? "Настроен" : "Не настроен"}
                </span>
                <span className="mt-1 block text-[11px] text-ink-faint">
                  {provider.description}
                </span>
              </button>
            );
          })}
        </div>

        {error ? (
          <p className="text-xs text-tone-danger">Не удалось проверить настройки источников.</p>
        ) : null}
        {data && !hasConfiguredProvider ? (
          <p className="rounded-lg border border-tone-warning/30 bg-tone-warning/10 p-3 text-left text-xs text-ink-soft">
            Настройте источник данных в локальном <code>.env</code>. Для
            Intervals.icu добавьте <code>INTERVALS_ICU_API_KEY</code> и задайте{" "}
            <code>PRIMARY_ACTIVITY_SOURCE=intervals</code>. Garmin Connect можно
            подключить дополнительно.
          </p>
        ) : null}

        <div className="flex flex-wrap items-center justify-center gap-3">
          <button
            type="button"
            onClick={sync}
            disabled={!canSync}
            className="rounded-lg border border-surface-border px-5 py-2 text-sm font-medium text-ink-soft transition hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy
              ? "Синхронизирую…"
              : `🔄 Синхронизировать ${selectedProvider?.label ?? "данные"}`}
          </button>
          {selectedSource === "intervals" && selectedProvider?.configured ? (
            <button
              type="button"
              onClick={testIntervalsConnection}
              className="rounded-lg px-4 py-2 text-sm font-medium text-accent transition hover:bg-accent/10"
            >
              Проверить подключение
            </button>
          ) : null}
        </div>
        {message ? <p className="text-xs text-ink-faint">{message}</p> : null}
        {probeMessage ? <p className="text-xs text-ink-soft">{probeMessage}</p> : null}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      {message ? <span className="hidden text-xs text-ink-faint sm:inline">{message}</span> : null}
      <select
        aria-label="Источник синхронизации"
        value={selectedSource ?? ""}
        onChange={(event) => setSelectedSource(event.target.value as SyncSource)}
        disabled={!data || busy}
        className="rounded-lg border border-surface-border bg-surface px-2 py-1.5 text-xs font-medium text-ink-soft disabled:opacity-50"
      >
        {data?.providers.map((provider) => (
          <option key={provider.source} value={provider.source} disabled={!provider.configured}>
            {provider.label}
            {provider.configured ? "" : " · не настроен"}
          </option>
        ))}
      </select>
      <button
        type="button"
        onClick={sync}
        disabled={!canSync}
        className="rounded-lg border border-surface-border px-3 py-1.5 text-sm font-medium text-ink-soft transition hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-50"
        title={
          selectedProvider
            ? `Синхронизировать с ${selectedProvider.label}`
            : "Выберите источник синхронизации"
        }
      >
        {busy ? "Синхронизирую…" : "🔄 Синк"}
      </button>
    </div>
  );
}

async function waitForSyncJob(
  onUpdate: (job: SyncJobResponse) => void,
): Promise<SyncJobResponse> {
  for (let attempt = 0; attempt < 240; attempt += 1) {
    const job = await fetcher<SyncJobResponse>("/api/sync");
    onUpdate(job);
    if (isTerminalSyncState(job.sync_state)) return job;
    await delay(2000);
  }
  throw new Error("Синхронизация всё ещё выполняется. Проверьте статус позже.");
}

function isTerminalSyncState(state: string): boolean {
  return state === "succeeded" || state === "partial" || state === "failed";
}

function formatSyncJob(job: SyncJobResponse, fallbackSource: SyncSource): string {
  const label = syncSourceLabel(job.source ?? fallbackSource);
  if (job.sync_state === "running") {
    const progress = job.progress;
    if (progress?.message) {
      const prefix = Number.isFinite(progress.percent) ? `${progress.percent}% · ` : "";
      return `${prefix}${progress.message}`;
    }
    return job.reused
      ? `Синхронизация ${label} уже выполняется…`
      : `Синхронизация ${label} запущена…`;
  }

  if (job.sync_state === "failed") {
    return job.error?.message || `Ошибка синхронизации ${label}`;
  }

  const result = job.result;
  if (result) {
    const detail = result.counts
      ? ` +${result.counts.new} новых, ${result.counts.updated} обновлено`
      : "";
    const notices =
      job.sync_state === "partial" ? formatSyncNotices(result.notices) : "";
    return (result.title || `Синхронизация ${label} завершена`) + detail + notices;
  }

  return job.sync_state === "partial"
    ? `Синхронизация ${label} завершена частично`
    : `Синхронизация ${label} завершена`;
}

function formatSyncNotices(notices: string[] | undefined): string {
  const actionable = (notices ?? []).filter((notice) => notice.trim()).slice(0, 2);
  return actionable.length > 0 ? ` · ${actionable.join(" · ")}` : "";
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}
