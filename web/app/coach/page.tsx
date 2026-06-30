"use client";

import { useRef, useState } from "react";
import useSWR from "swr";
import { Markdown } from "@/components/Markdown";
import { ProposalCard } from "@/components/ui/ProposalCard";
import { fetcher, streamCoachChat } from "@/lib/api";
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
  messages: ChatMessage[];
}

interface ToolFlash {
  name: string;
}

export default function CoachPage() {
  const { data: dash } = useSWR<DashboardResponse>(
    "/api/dashboard/summary",
    fetcher,
  );
  const { data: history, mutate: mutateHistory } = useSWR<{ chats: ChatSummary[] }>(
    "/api/coach/history",
    fetcher,
  );

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [partial, setPartial] = useState("");
  const [tools, setTools] = useState<ToolFlash[]>([]);
  const [proposal, setProposal] = useState<{
    action: CoachProposalAction;
    params: Record<string, unknown>;
    preview: Record<string, unknown>;
  } | null>(null);
  const chatId = useRef<string | null>(null);
  const scroller = useRef<HTMLDivElement>(null);

  const today = dash?.summary?.today;
  const suggestions = buildSuggestions(today);

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
        { message, chat_id: chatId.current },
        (e) => {
          if (e.type === "meta") chatId.current = e.chat_id;
          else if (e.type === "tool_call")
            setTools((t) => [...t, { name: e.name }]);
          else if (e.type === "proposal") {
            setProposal({
              action: e.action,
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
    chatId.current = null;
    setMessages([]);
    setPartial("");
    setTools([]);
    setProposal(null);
  }

  async function loadChat(id: string) {
    if (streaming) return;
    try {
      const detail = await fetcher<ChatDetail>(`/api/coach/history/${id}`);
      chatId.current = detail.id;
      setMessages(
        detail.messages.map((m) => ({ role: m.role, content: m.content })),
      );
      setPartial("");
      setTools([]);
      setProposal(null);
      scrollDown();
    } catch {
      // ignore load failure; keep current view
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
      <ContextSidebar
        today={today}
        history={history?.chats ?? []}
        activeId={chatId.current}
        onNew={newChat}
        onSelect={loadChat}
      />

      <section className="flex h-[calc(100vh-180px)] min-h-[420px] flex-col rounded-card border border-surface-border bg-surface shadow-card">
        <div ref={scroller} className="flex-1 space-y-3 overflow-y-auto p-4">
          {messages.length === 0 && !streaming ? (
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
              action={proposal.action}
              params={proposal.params}
              preview={proposal.preview}
              onConfirmed={(message) => {
                setMessages((m) => [...m, { role: "assistant", content: message }]);
                setProposal(null);
                scrollDown();
              }}
              onCancelled={() => setProposal(null)}
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

function ContextSidebar({
  today,
  history,
  activeId,
  onNew,
  onSelect,
}: {
  today?: TodayState;
  history: ChatSummary[];
  activeId: string | null;
  onNew: () => void;
  onSelect: (id: string) => void;
}) {
  return (
    <aside className="space-y-4">
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
        <ul className="mt-2 space-y-0.5 text-sm">
          {history.length === 0 ? (
            <li className="text-ink-faint">Пока нет сохранённых чатов</li>
          ) : (
            history.slice(0, 10).map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => onSelect(c.id)}
                  className={`w-full truncate rounded-lg px-2 py-1.5 text-left transition hover:bg-surface-muted ${
                    activeId === c.id
                      ? "bg-surface-muted font-medium text-ink"
                      : "text-ink-soft"
                  }`}
                  title={c.title}
                >
                  {c.title}
                </button>
              </li>
            ))
          )}
        </ul>
      </div>
    </aside>
  );
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
            ? "whitespace-pre-wrap bg-ink text-white"
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
          className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-white transition hover:bg-ink/90 disabled:opacity-40"
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
