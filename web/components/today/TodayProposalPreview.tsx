import { decisionText, workoutLabel } from "./displayText";

type Row = Record<string, unknown>;
type Kind = "keep" | "downgrade_today" | "transfer_1_3d";
const record = (value: unknown): Row => value && typeof value === "object" ? value as Row : {};
const rows = (value: unknown): Row[] => Array.isArray(value) ? value.map(record) : [];
const text = (value: unknown) => value == null ? "" : String(value);
function dateLabel(value: unknown) {
  const raw = text(value);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw || "Дата не указана";
  const date = new Date(`${raw}T12:00:00`);
  return Number.isNaN(date.getTime()) ? raw : date.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
}
function sessionLabel(session: Row) {
  return workoutLabel(text(session.name || session.template_name || session.sport_label) || "Тренировка");
}
function Session({ session }: { session: Row }) {
  return <div>
    <div className="font-semibold text-ink">{sessionLabel(session)}</div>
    <div className="mt-1 flex flex-wrap gap-x-3 text-sm text-ink-soft">
      {session.duration_minutes != null ? <span>{text(session.duration_minutes)} мин</span> : null}
      {session.tss != null || session.total_tss != null ? <span>{text(session.tss ?? session.total_tss)} TSS</span> : null}
    </div>
  </div>;
}
function Day({ sessions }: { sessions: unknown }) {
  const items = rows(sessions);
  return items.length ? <div className="space-y-3">{items.map((s, i) => <Session key={i} session={s} />)}</div> : <span className="text-ink-soft">Нет тренировки</span>;
}
function delta(value: unknown, unit: string) {
  return typeof value === "number" && Number.isFinite(value) ? `${value > 0 ? "+" : ""}${value} ${unit}` : "Не указано";
}

// Presentation of server-provided options only. Selection and approval stay in ProposalCard.
export function TodayProposalPreview({ variants, selectedKind, recommendedKind, currentSession, recommendedSession, selectedVariant, protection, dayChanges, reason, evidence, candidates, onSelect }: {
  variants: Row[]; selectedKind: Kind; recommendedKind: Kind;
  currentSession: Row; recommendedSession: Row; selectedVariant: Row; protection: Row;
  dayChanges: Row[]; reason: string; evidence: string[]; candidates: string[];
  onSelect: (kind: Kind) => void;
}) {
  const labels: Record<Kind, string> = { keep: "Оставить как есть", downgrade_today: "Снизить нагрузку", transfer_1_3d: "Перенести тренировку" };
  return <div className="mt-4 space-y-4">
    <div className="grid gap-3 md:grid-cols-3" role="group" aria-label="Варианты изменения плана">
      {variants.map((variant) => {
        const kind = variant.kind as Kind;
        return <button key={kind} type="button" aria-pressed={kind === selectedKind} onClick={() => onSelect(kind)}
          className={`rounded-lg border p-4 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent ${kind === selectedKind ? "border-accent bg-accent/10" : "border-surface-border bg-surface"}`}>
          <span className="block text-base font-semibold text-ink">{kind === selectedKind ? "● " : "○ "}{labels[kind]}</span>
          <span className="mt-2 block text-sm text-ink-soft">{kind === "transfer_1_3d" ? `${dateLabel(variant.source_date)} → ${dateLabel(variant.target_date)}` : sessionLabel(record(variant.session || (kind === "keep" ? currentSession : recommendedSession)))}</span>
          {kind === recommendedKind ? <span className="mt-2 block text-xs font-medium text-accent">Рекомендовано</span> : null}
        </button>;
      })}
    </div>
    {selectedKind === "keep" ? <p className="text-sm text-ink">Текущий план сохраняется.</p> : dayChanges.length ? dayChanges.map((change, index) => <section key={index} className="rounded-lg bg-surface p-4">
      <h3 className="mb-3 text-sm font-medium text-ink">{dateLabel(change.date)}</h3>
      <div className="grid gap-4 sm:grid-cols-2">
        <div><div className="mb-2 text-xs uppercase text-ink-soft">Сейчас</div><Day sessions={change.before_sessions} /></div>
        <div><div className="mb-2 text-xs uppercase text-accent">После подтверждения</div><Day sessions={change.after_sessions} /></div>
      </div>
    </section>) : selectedKind === "transfer_1_3d" ? <div className="rounded-lg bg-surface p-4 text-lg font-semibold text-ink">
      {dateLabel(selectedVariant.source_date)} → {dateLabel(selectedVariant.target_date)}
    </div> : <div className="grid gap-4 rounded-lg bg-surface p-4 sm:grid-cols-2">
      <div><div className="mb-2 text-xs uppercase text-ink-soft">Сейчас</div><Session session={currentSession} /></div>
      <div><div className="mb-2 text-xs uppercase text-accent">После подтверждения</div><Session session={record(selectedVariant.session || recommendedSession)} /></div>
    </div>}
    <div className="grid grid-cols-2 gap-3">
      <div className="rounded-lg bg-surface p-3"><div className="text-xs text-ink-soft">Время за неделю</div><div className="mt-1 text-lg font-semibold text-ink">{delta(protection.weekly_duration_delta_minutes, "мин")}</div></div>
      <div className="rounded-lg bg-surface p-3"><div className="text-xs text-ink-soft">Нагрузка за неделю</div><div className="mt-1 text-lg font-semibold text-ink">{delta(protection.weekly_tss_delta, "TSS")}</div></div>
    </div>
    <details className="border-t border-surface-border pt-3">
      <summary className="cursor-pointer text-sm font-medium text-accent">Почему предложено изменение</summary>
      <div className="mt-3 space-y-2 text-sm text-ink-soft">
        <p>{decisionText(reason)}</p>
        {evidence.map((item, index) => <p key={index}>{decisionText(item)}</p>)}
        {candidates.length ? <div><p className="font-medium">Проверенные даты</p>{candidates.map((item, index) => <p key={index}>{item}</p>)}</div> : null}
        <p>TSS — оценка тренировочной нагрузки. Здесь показано изменение суммарной нагрузки недели.</p>
      </div>
    </details>
  </div>;
}
