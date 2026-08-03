"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { Markdown } from "@/components/Markdown";
import { ProposalCard } from "@/components/ui/ProposalCard";
import { ApiError, deleteJSON, fetcher, postJSON, streamCoachChat } from "@/lib/api";
import {
  ChatMessage,
  CoachProposalAction,
  ChatSummary,
  DashboardResponse,
  TodayState,
} from "@/lib/types";

interface ChatDetail {
  id: string;
  title: string;
  archived: boolean;
  created_at: string | null;
  updated_at: string | null;
  messages: ChatMessage[];
}

interface ToolFlash {
  name: string;
}

function CoachContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data: dash } = useSWR<DashboardResponse>(
    "/api/dashboard/summary",
    fetcher,
  );
  const [searchQuery, setSearchQuery] = useState("");
  const historyKey = searchQuery.trim()
    ? `/api/coach/search?q=${encodeURIComponent(searchQuery.trim())}`
    : "/api/coach/history";
  const { data: history, mutate: mutateHistory } = useSWR<{ chats: ChatSummary[] }>(
    historyKey,
    fetcher,
  );

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [partial, setPartial] = useState("");
  const [tools, setTools] = useState<ToolFlash[]>([]);
  const [proposal, setProposal] = useState<{
    proposal_id: number;
    action: CoachProposalAction;
    status: string;
    params: Record<string, unknown>;
    preview: Record<string, unknown>;
  } | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const restoredChat = useRef(false);

  const today = dash?.summary?.today;
  const suggestions = buildSuggestions(today);

  // M2 (#266): выбранный чат переживает reload/deep-link через ?chat=<id>.
  useEffect(() => {
    if (restoredChat.current) return;
    const chatParam = searchParams.get("chat");
    if (chatParam) {
      restoredChat.current = true;
      loadChat(chatParam);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  function scrollDown() {
    requestAnimationFrame(() => {
      scroller.current?.scrollTo({ top: scroller.current.scrollHeight });
    });
  }

  async function send(text: string) {
    const message = text.trim();
    if (!message || streaming) return;

    setMessages((m) => [...m, { role: "user", content: message }]);
    setDraft("");
    setPartial("");
    setTools([]);
    setStreaming(true);
    scrollDown();

    let acc = "";
    try {
      await streamCoachChat(
        { message, chat_id: activeChatId },
        (e) => {
          if (e.type === "meta") {
            setActiveChatId(e.chat_id);
            router.replace(`/coach?chat=${e.chat_id}`);
          }
          else if (e.type === "tool_call")
            setTools((t) => [...t, { name: e.name }]);
          else if (e.type === "proposal") {
            setProposal({
              proposal_id: e.proposal_id,
              action: e.action,
              status: e.status,
              params: e.params ?? {},
              preview: e.preview ?? {},
            });
          }
          else if (e.type === "token") {
            acc += e.content;
            setPartial(acc);
            scrollDown();
          } else if (e.type === "done") {
            setMessages((m) => [...m, { role: "assistant", content: acc }]);
            setPartial("");
            setStreaming(false);
            mutateHistory();
          } else if (e.type === "error") {
            setMessages((m) => [
              ...m,
              { role: "assistant", content: `⚠️ ${e.message}` },
            ]);
            setPartial("");
            setStreaming(false);
          }
        },
      );
    } catch {
      setMessages((m) => [
        ...m,
        { role: "assistant", content: "⚠️ Не удалось получить ответ. Запущен ли API?" },
      ]);
      setPartial("");
      setStreaming(false);
    }
  }

  function newChat() {
    router.replace("/coach");
    setActiveChatId(null);
    setLoadError(null);
    setMessages([]);
    setPartial("");
    setTools([]);
    setProposal(null);
  }

  async function loadChat(id: string) {
    if (streaming) return;
    try {
      const detail = await fetcher<ChatDetail>(`/api/coach/history/${id}`);
      setActiveChatId(detail.id);
      setLoadError(null);
      setMessages(
        detail.messages.map((m) => ({ role: m.role, content: m.content })),
      );
      setPartial("");
      setTools([]);
      setProposal(null);
      scrollDown();
    } catch {
      setActiveChatId(id);
      setMessages([]);
      setLoadError("Чат не найден. Возможно, он был удалён.");
    }
  }

  function selectChat(id: string) {
    router.replace(`/coach?chat=${id}`);
    loadChat(id);
  }

  function handleDeleted(id: string) {
    if (activeChatId === id) {
      router.replace("/coach");
      setActiveChatId(null);
      setMessages([]);
      setLoadError(null);
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
      <ContextSidebar
        today={today}
        history={history?.chats ?? []}
        activeId={activeChatId}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        onNew={newChat}
        onSelect={selectChat}
        onDeleted={handleDeleted}
        mutateHistory={mutateHistory}
      />

      <section className="flex h-[calc(100vh-180px)] min-h-[420px] min-w-0 flex-col rounded-card border border-surface-border bg-surface shadow-card">
        <div ref={scroller} className="flex-1 space-y-3 overflow-y-auto p-4">
          {loadError ? (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <div className="text-3xl">🗂️</div>
              <p className="mt-2 max-w-xs text-sm text-ink-faint">{loadError}</p>
            </div>
          ) : messages.length === 0 && !streaming ? (
            <EmptyState />
          ) : null}

          {messages.map((m, i) => (
            <Bubble key={i} role={m.role} content={m.content} />
          ))}

          {tools.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {tools.map((t, i) => (
                <span
                  key={i}
                  className="rounded-full bg-tone-neutral/10 px-2.5 py-1 text-xs text-tone-neutral"
                >
                  🔧 {t.name}
                </span>
              ))}
            </div>
          ) : null}

          {proposal ? (
            <ProposalCard
              proposalId={proposal.proposal_id}
              action={proposal.action}
              status={proposal.status}
              params={proposal.params}
              preview={proposal.preview}
              onConfirmed={(message) => {
                setMessages((m) => [...m, { role: "assistant", content: message }]);
                setProposal(null);
                scrollDown();
              }}
              onCancelled={(message) => {
                if (message) {
                  setMessages((m) => [...m, { role: "assistant", content: message }]);
                }
                setProposal(null);
                scrollDown();
              }}
            />
          ) : null}

          {partial ? <Bubble role="assistant" content={partial} streaming /> : null}
          {streaming && !partial ? (
            <div className="flex items-center gap-2 text-sm text-ink-faint">
              <span className="inline-flex gap-1">
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-ink-faint [animation-delay:-0.2s]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-ink-faint [animation-delay:-0.1s]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-ink-faint" />
              </span>
              🤖 Тренер анализирует данные… (DeepSeek, обычно 10–30с)
            </div>
          ) : null}
        </div>

        {messages.length === 0 ? (
          <div className="flex flex-wrap gap-2 px-4">
            <button
              type="button"
              onClick={() => send("Дай ежедневный брифинг: моё текущее состояние, план на сегодня и главный акцент недели. Коротко.")}
              className="rounded-full border border-tone-neutral/40 bg-tone-neutral/10 px-3 py-1.5 text-xs font-medium text-tone-neutral transition hover:bg-tone-neutral/20"
            >
              📋 Ежедневный брифинг
            </button>
            {suggestions.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => send(s)}
                className="rounded-full border border-surface-border px-3 py-1.5 text-xs text-ink-soft transition hover:bg-surface-muted"
              >
                {s}
              </button>
            ))}
          </div>
        ) : null}

        <InputBar
          value={draft}
          disabled={streaming}
          onChange={setDraft}
          onSend={() => send(draft)}
        />
      </section>
    </div>
  );
}

export default function CoachPage() {
  return (
    <Suspense
      fallback={
        <div className="h-40 animate-pulse rounded-card bg-surface" />
      }
    >
      <CoachContent />
    </Suspense>
  );
}

function ContextSidebar({
  today,
  history,
  activeId,
  searchQuery,
  onSearchChange,
  onNew,
  onSelect,
  onDeleted,
  mutateHistory,
}: {
  today?: TodayState;
  history: ChatSummary[];
  activeId: string | null;
  searchQuery: string;
  onSearchChange: (value: string) => void;
  onNew: () => void;
  onSelect: (id: string) => void;
  onDeleted: (id: string) => void;
  mutateHistory: () => Promise<unknown>;
}) {
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renameError, setRenameError] = useState<string | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const activeChats = history.filter((chat) => !chat.archived);
  const archivedChats = history.filter((chat) => chat.archived);

  function startRename(chat: ChatSummary) {
    setRenamingId(chat.id);
    setRenameValue(chat.title);
    setRenameError(null);
  }
  function cancelRename() {
    setRenamingId(null);
    setRenameValue("");
    setRenameError(null);
  }
  async function rename(chat: ChatSummary) {
    const title = renameValue.trim();
    if (!title || busyId) return;
    setBusyId(chat.id);
    setRenameError(null);
    try {
      await postJSON(`/api/coach/chats/${chat.id}/rename`, { title });
      cancelRename();
      await mutateHistory();
    } catch (e) {
      setRenameError(e instanceof ApiError ? e.message : "Не удалось переименовать чат");
    } finally {
      setBusyId(null);
    }
  }
  async function toggleArchive(chat: ChatSummary) {
    if (busyId) return;
    setBusyId(chat.id);
    try {
      await postJSON(`/api/coach/chats/${chat.id}/${chat.archived ? "restore" : "archive"}`, {});
      await mutateHistory();
    } catch {
      /* сохраняем текущее состояние списка */
    } finally {
      setBusyId(null);
    }
  }
  async function remove(chat: ChatSummary) {
    if (busyId) return;
    setBusyId(chat.id);
    try {
      await deleteJSON(`/api/coach/chats/${chat.id}`);
      setDeleteConfirmId(null);
      await mutateHistory();
      onDeleted(chat.id);
    } catch {
      /* сохраняем текущее состояние списка */
    } finally {
      setBusyId(null);
    }
  }

  return (
    <aside className="min-w-0 space-y-4">
      <div className="rounded-card border border-surface-border bg-surface p-4 shadow-card">
        <div className="text-xs font-medium uppercase tracking-wide text-ink-faint">
          Сигналы
        </div>
        <dl className="mt-2 space-y-1 text-sm">
          <Signal label="Состояние" value={today?.state_label ?? "—"} />
          <Signal label="Readiness" value={today ? `${today.readiness}` : "—"} />
          <Signal label="TSB" value={today ? `${today.tsb}` : "—"} />
          <Signal label="CTL" value={today ? `${today.ctl}` : "—"} />
          <Signal label="HRV" value={today?.hrv != null ? `${today.hrv}` : "—"} />
        </dl>
      </div>

      <div className="rounded-card border border-surface-border bg-surface p-4 shadow-card">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium uppercase tracking-wide text-ink-faint">
            История
          </span>
          <button
            type="button"
            onClick={onNew}
            className="text-xs font-medium text-tone-neutral hover:underline"
          >
            + Новый
          </button>
        </div>
        <input
          type="search"
          value={searchQuery}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="Поиск по чатам…"
          aria-label="Поиск по чатам"
          className="mt-2 w-full rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm outline-none focus:border-tone-neutral"
        />
        {renameError ? (
          <p className="mt-2 text-xs text-tone-danger">{renameError}</p>
        ) : null}
        {history.length === 0 ? (
          <p className="mt-3 text-sm text-ink-faint">
            {searchQuery.trim() ? "Ничего не найдено" : "Пока нет сохранённых чатов"}
          </p>
        ) : (
          <div className="mt-3 max-h-[calc(100vh-320px)] space-y-4 overflow-y-auto pr-1">
            <HistoryGroup
              title="Активные"
              defaultOpen
              chats={activeChats}
              activeId={activeId}
              busyId={busyId}
              renamingId={renamingId}
              renameValue={renameValue}
              deleteConfirmId={deleteConfirmId}
              onSelect={onSelect}
              onStartRename={startRename}
              onRenameValueChange={setRenameValue}
              onRename={rename}
              onCancelRename={cancelRename}
              onToggleArchive={toggleArchive}
              onAskDelete={setDeleteConfirmId}
              onDelete={remove}
            />
            <HistoryGroup
              title="Архив"
              defaultOpen={false}
              chats={archivedChats}
              activeId={activeId}
              busyId={busyId}
              renamingId={renamingId}
              renameValue={renameValue}
              deleteConfirmId={deleteConfirmId}
              onSelect={onSelect}
              onStartRename={startRename}
              onRenameValueChange={setRenameValue}
              onRename={rename}
              onCancelRename={cancelRename}
              onToggleArchive={toggleArchive}
              onAskDelete={setDeleteConfirmId}
              onDelete={remove}
            />
          </div>
        )}
      </div>
    </aside>
  );
}

function HistoryGroup({
  title,
  defaultOpen = true,
  chats,
  activeId,
  busyId,
  renamingId,
  renameValue,
  deleteConfirmId,
  onSelect,
  onStartRename,
  onRenameValueChange,
  onRename,
  onCancelRename,
  onToggleArchive,
  onAskDelete,
  onDelete,
}: {
  title: string;
  defaultOpen?: boolean;
  chats: ChatSummary[];
  activeId: string | null;
  busyId: string | null;
  renamingId: string | null;
  renameValue: string;
  deleteConfirmId: string | null;
  onSelect: (id: string) => void;
  onStartRename: (chat: ChatSummary) => void;
  onRenameValueChange: (value: string) => void;
  onRename: (chat: ChatSummary) => void;
  onCancelRename: () => void;
  onToggleArchive: (chat: ChatSummary) => void;
  onAskDelete: (id: string | null) => void;
  onDelete: (chat: ChatSummary) => void;
}) {
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [open, setOpen] = useState(defaultOpen);
  if (chats.length === 0) return null;
  const groups = new Map<string, ChatSummary[]>();
  for (const chat of chats) {
    const key = dayGroup(chat.date);
    const bucket = groups.get(key) ?? [];
    bucket.push(chat);
    groups.set(key, bucket);
  }

  return (
    <section>
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        aria-controls={`history-group-${title}`}
        className="flex w-full items-center justify-between text-left text-[11px] font-medium uppercase tracking-wide text-ink-faint transition hover:text-ink"
      >
        {title}
        <span aria-hidden="true">{open ? "▾" : "▸"}</span>
      </button>
      {open ? (
        <div id={`history-group-${title}`}>
          {[...groups.entries()].map(([label, items]) => (
            <div key={label} className="mt-2">
              <div className="text-[10px] uppercase tracking-wide text-ink-faint/70">{label}</div>
              <ul className="mt-1 space-y-1.5">
                {items.map((chat) => (
                  <li key={chat.id} className="rounded-lg border border-surface-border p-2">
                <button
                  type="button"
                  onClick={() => onSelect(chat.id)}
                  className={`w-full text-left transition ${
                    activeId === chat.id ? "" : "hover:opacity-80"
                  }`}
                >
                  <span
                    className={`block truncate text-sm ${
                      activeId === chat.id ? "font-semibold text-accent" : "font-medium text-ink"
                    }`}
                  >
                    {chat.title}
                  </span>
                  <span className="mt-0.5 block truncate text-[11px] text-ink-faint">
                    {chat.message_count} сообщ.
                    {chat.preview ? ` · ${chat.preview}` : ""}
                  </span>
                </button>
                <div className="mt-1 flex items-center justify-end gap-1">
                  <button
                    type="button"
                    onClick={() => {
                      setMenuOpenId((current) => (current === chat.id ? null : chat.id));
                      onAskDelete(null);
                    }}
                    aria-expanded={menuOpenId === chat.id}
                    aria-label={`Действия: ${chat.title}`}
                    className="rounded-lg border border-surface-border px-1.5 py-0.5 text-xs text-ink-soft transition hover:bg-surface-muted"
                  >
                    ⋯
                  </button>
                </div>
                {menuOpenId === chat.id ? (
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    {renamingId === chat.id ? (
                    <>
                      <input
                        value={renameValue}
                        onChange={(event) => onRenameValueChange(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") {
                            event.preventDefault();
                            onRename(chat);
                          } else if (event.key === "Escape") {
                            onCancelRename();
                          }
                        }}
                        aria-label="Название чата"
                        className="w-full rounded-lg border border-surface-border bg-surface px-2 py-1 text-xs outline-none focus:border-tone-neutral"
                      />
                      <button
                        type="button"
                        onClick={() => onRename(chat)}
                        disabled={busyId === chat.id || !renameValue.trim()}
                        className="rounded-lg bg-accent px-2.5 py-1 text-xs font-medium text-accent-foreground disabled:opacity-40"
                      >
                        Сохранить
                      </button>
                      <button
                        type="button"
                        onClick={onCancelRename}
                        disabled={busyId === chat.id}
                        className="rounded-lg border border-surface-border px-2.5 py-1 text-xs text-ink-soft"
                      >
                        Отмена
                      </button>
                    </>
                    ) : deleteConfirmId === chat.id ? (
                      <>
                        <span className="text-xs text-ink-soft">Удалить чат?</span>
                        <button
                          type="button"
                          onClick={() => onDelete(chat)}
                          disabled={busyId === chat.id}
                          className="rounded-lg bg-tone-danger px-2.5 py-1 text-xs font-medium text-white disabled:opacity-40"
                        >
                          {busyId === chat.id ? "Удаляю…" : "Да, удалить"}
                        </button>
                        <button
                          type="button"
                          onClick={() => onAskDelete(null)}
                          disabled={busyId === chat.id}
                          className="rounded-lg border border-surface-border px-2.5 py-1 text-xs text-ink-soft"
                        >
                          Отмена
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => {
                            onStartRename(chat);
                          }}
                          disabled={busyId === chat.id}
                          className="rounded-lg border border-surface-border px-2 py-1 text-[11px] text-ink-soft transition hover:bg-surface-muted"
                        >
                          Переименовать
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            onToggleArchive(chat);
                            setMenuOpenId(null);
                          }}
                          disabled={busyId === chat.id}
                          className="rounded-lg border border-surface-border px-2 py-1 text-[11px] text-ink-soft transition hover:bg-surface-muted"
                        >
                          {chat.archived ? "Вернуть" : "В архив"}
                        </button>
                        <button
                          type="button"
                          onClick={() => onAskDelete(chat.id)}
                          disabled={busyId === chat.id}
                          className="rounded-lg border border-surface-border px-2 py-1 text-[11px] text-tone-danger transition hover:bg-tone-danger/10"
                        >
                          Удалить
                        </button>
                      </>
                    )}
                  </div>
                ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function dayGroup(iso?: string | null): string {
  if (!iso) return "Ранее";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "Ранее";
  const startOfDay = (value: Date) =>
    new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime();
  const diffDays = Math.round((startOfDay(new Date()) - startOfDay(date)) / 86400000);
  if (diffDays <= 0) return "Сегодня";
  if (diffDays === 1) return "Вчера";
  return "Ранее";
}

function Signal({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <dt className="text-ink-faint">{label}</dt>
      <dd className="font-medium text-ink">{value}</dd>
    </div>
  );
}

function Bubble({
  role,
  content,
  streaming,
}: {
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
}) {
  const isUser = role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm ${
          isUser
            ? "whitespace-pre-wrap bg-accent text-accent-foreground"
            : "border border-surface-border bg-surface-muted text-ink"
        }`}
      >
        {isUser ? content : <Markdown>{content}</Markdown>}
        {streaming ? <span className="ml-0.5 animate-pulse">▍</span> : null}
      </div>
    </div>
  );
}

function InputBar({
  value,
  disabled,
  onChange,
  onSend,
}: {
  value: string;
  disabled: boolean;
  onChange: (v: string) => void;
  onSend: () => void;
}) {
  return (
    <div className="border-t border-surface-border p-3">
      <div className="flex items-end gap-2">
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSend();
            }
          }}
          rows={1}
          placeholder="Спросите тренера…  (Enter — отправить, Shift+Enter — перенос)"
          className="max-h-32 flex-1 resize-none rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm outline-none focus:border-tone-neutral"
        />
        <button
          type="button"
          onClick={onSend}
          disabled={disabled || !value.trim()}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-foreground transition hover:bg-accent/90 disabled:opacity-40"
        >
          Отправить
        </button>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center text-center text-ink-faint">
      <div className="text-3xl">🤖</div>
      <p className="mt-2 max-w-xs text-sm">
        Тренер видит ваши данные за последние 30 дней. Спросите о нагрузке,
        восстановлении или ближайших тренировках.
      </p>
    </div>
  );
}

function buildSuggestions(today?: { tsb: number; state_label: string }): string[] {
  if (!today) {
    return [
      "Как я сегодня по нагрузке?",
      "Когда можно тренироваться интенсивно?",
      "Что с моим восстановлением?",
    ];
  }
  if (today.tsb < -20) {
    return [
      "Мне нужна разгрузка?",
      "Сколько дней восстанавливаться?",
      "Что делать сегодня при такой усталости?",
    ];
  }
  return [
    "Когда лучшее окно для интервалов?",
    "Как выглядит моя форма к старту?",
    "Дай план на ближайшие 3 дня",
  ];
}
