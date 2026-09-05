import type { ReactNode } from "react";

type ShowcaseState = "normal" | "loading" | "empty" | "error";

const STATE_LABELS: Record<ShowcaseState, string> = {
  normal: "Normal",
  loading: "Loading",
  empty: "Empty",
  error: "Error",
};

export function ShowcaseStateCard({
  state,
  title,
  children,
}: {
  state: ShowcaseState;
  title: string;
  children?: ReactNode;
}) {
  return (
    <article className="min-w-0 rounded-card border border-surface-border bg-surface p-4 shadow-card">
      <header className="mb-3 flex items-center justify-between gap-2 border-b border-surface-border pb-3">
        <h3 className="text-sm font-semibold text-ink">
          {title}
          <span className="sr-only"> — состояние {STATE_LABELS[state]}</span>
        </h3>
        <span
          aria-hidden="true"
          className="rounded-full bg-surface-muted px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-ink-soft"
        >
          {STATE_LABELS[state]}
        </span>
      </header>

      {state === "normal" ? children : null}
      {state === "loading" ? (
        <div role="status" aria-live="polite" className="space-y-3">
          <span className="sr-only">Компонент загружается</span>
          <div className="h-4 w-2/3 animate-pulse rounded bg-surface-muted" />
          <div className="h-16 animate-pulse rounded-lg bg-surface-muted" />
          <div className="h-3 w-1/2 animate-pulse rounded bg-surface-muted" />
        </div>
      ) : null}
      {state === "empty" ? (
        <div
          role="status"
          className="rounded-lg border border-dashed border-surface-border bg-surface-muted p-5 text-center"
        >
          <div className="text-sm font-medium text-ink">Пока нет данных</div>
          <p className="mt-1 text-xs leading-relaxed text-ink-soft">
            После первой синхронизации здесь появится содержимое компонента.
          </p>
        </div>
      ) : null}
      {state === "error" ? (
        <div
          role="alert"
          className="rounded-lg border border-tone-danger/30 bg-tone-danger/10 p-4"
        >
          <div className="text-sm font-medium text-tone-danger">Не удалось загрузить данные</div>
          <p className="mt-1 text-xs leading-relaxed text-ink-soft">
            Проверьте соединение и повторите попытку. Сохранённые данные не изменены.
          </p>
        </div>
      ) : null}
    </article>
  );
}
