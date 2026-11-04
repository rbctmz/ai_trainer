"use client";

import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { fetcher, postJSON } from "@/lib/api";
import type { BackupStatus } from "@/lib/types";

function timeLabel(value: string | null): string {
  if (!value) return "время не указано";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "время не указано"
    : date.toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" });
}

export function BackupStatusView({ status, loading = false, pending = false, retryError = false, onRetry }: {
  status: BackupStatus | null;
  loading?: boolean;
  pending?: boolean;
  retryError?: boolean;
  onRetry?: () => void;
}) {
  if (loading) return <p className="mb-4 text-xs text-ink-faint" role="status">Проверяем состояние резервной копии…</p>;
  if (status?.state === "disabled") {
    return <p className="mb-4 text-xs text-ink-faint" data-testid="backup-status">Автоматические резервные копии выключены.</p>;
  }
  const ready = status?.state === "ready";
  const degraded = status?.state === "degraded";
  return (
    <aside
      className={`mb-4 rounded-xl border p-3 text-sm ${ready ? "border-surface-border bg-surface text-ink-soft" : "border-tone-warning/40 bg-tone-warning/5 text-ink"}`}
      aria-label="Резервная копия"
      role="status"
      data-testid="backup-status"
    >
      <p className="font-medium">
        {ready ? "Резервная копия проверена." : degraded ? "Данные сохранены, резервная копия не обновлена." : "Состояние резервной копии неизвестно."}
      </p>
      <p className="mt-1 text-xs text-ink-soft">
        {status?.last_snapshot_at
          ? `Последняя проверенная копия: ${timeLabel(status.last_snapshot_at)}.`
          : "Время последней проверенной копии неизвестно."}
        {ready && status.last_checked_at ? ` Проверка: ${timeLabel(status.last_checked_at)}.` : ""}
      </p>
      {!ready && onRetry ? (
        <button type="button" onClick={onRetry} disabled={pending}
          className="mt-2 rounded-lg border border-surface-border bg-surface px-3 py-2 text-xs font-medium text-ink transition hover:bg-surface-muted disabled:cursor-wait disabled:opacity-60">
          {pending ? "Проверяем резервную копию…" : "Повторить проверку резервной копии"}
        </button>
      ) : null}
      {retryError ? <p className="mt-2 text-xs text-tone-warning">Не удалось проверить копию. Данные сохранять повторно не нужно.</p> : null}
    </aside>
  );
}

export function BackupStatusBanner() {
  const { data, error, isLoading, mutate } = useSWR<BackupStatus>("/api/backup/status", fetcher, {
    refreshInterval: 60_000, errorRetryInterval: 60_000,
  });
  const [pending, setPending] = useState(false);
  const [retryError, setRetryError] = useState(false);
  const checking = useRef(false);
  useEffect(() => {
    const refresh = () => { void mutate(); };
    window.addEventListener("backup-status-changed", refresh);
    return () => window.removeEventListener("backup-status-changed", refresh);
  }, [mutate]);

  async function retry() {
    if (checking.current) return;
    checking.current = true;
    setPending(true);
    setRetryError(false);
    try {
      const checked = await postJSON<BackupStatus>("/api/backup/check", {});
      setRetryError(checked.state === "degraded");
      await mutate(checked, { revalidate: false });
    } catch {
      setRetryError(true);
      await mutate().catch(() => undefined);
    } finally {
      checking.current = false;
      setPending(false);
    }
  }
  return <BackupStatusView status={error ? null : data ?? null} loading={isLoading && !error}
    pending={pending} retryError={retryError} onRetry={retry} />;
}
