"use client";

import type { EntryDoseAdjustment, EntryLoadAssessment, EntrySport, HistoryCoverage, InitialDoseLimits } from "@/lib/types";

export const ENTRY_SPORT_LABELS: Record<EntrySport, string> = { bike: "вело", run: "бег", swim: "плавание" };
export type EntryDraft = Partial<Record<EntrySport, { weekly: string; sessions: string; longest: string }>>;
const inputClass = "mt-1 w-full min-w-0 rounded-lg border border-surface-border bg-surface px-3 py-2 text-ink";

// Form serialization only. Reference windows, observed limits and feasibility
// are owned by Python; the browser supplies no inferred dose or history claim.
export function entryFieldsValid(coverage: HistoryCoverage | null, draft: EntryDraft, sports: EntrySport[]): boolean {
  if (coverage && coverage.status !== "unknown" && (!coverage.start_date || !coverage.end_date_exclusive || coverage.start_date >= coverage.end_date_exclusive)) return false;
  return sports.every(sport => {
    const row = draft[sport];
    if (!row) return true;
    return [row.weekly, row.sessions, row.longest].every(value => value.trim() !== "" && Number.isFinite(Number(value)) && Number(value) > 0)
      && Number.isInteger(Number(row.sessions)) && Number(row.longest) <= Number(row.weekly);
  });
}

export function declaredEntryPayload(draft: EntryDraft, sports: EntrySport[]): InitialDoseLimits | undefined {
  const entries = sports.flatMap(sport => draft[sport] ? [[sport, {
    source: "athlete_declared", weekly_minutes: Number(draft[sport]!.weekly),
    weekly_sessions: Number(draft[sport]!.sessions), max_session_minutes: Number(draft[sport]!.longest),
  }]] : []);
  return entries.length ? Object.fromEntries(entries) as InitialDoseLimits : undefined;
}

export function EntryDoseFields({ coverage, draft, sports, editing, onCoverage, onDraft }: {
  coverage: HistoryCoverage | null; draft: EntryDraft; sports: EntrySport[]; editing: boolean;
  onCoverage: (value: HistoryCoverage) => void; onDraft: (value: EntryDraft) => void;
}) {
  return <section aria-labelledby="entry-input-heading" className="mt-5 border-t border-surface-border pt-4">
    <h3 id="entry-input-heading" className="text-sm font-semibold text-ink">История и начальная нагрузка</h3>
    <p className="mt-1 text-sm text-ink-soft">Начальный объём проверяется отдельно для каждой дисциплины. Если истории недостаточно, задайте стартовые ограничения самостоятельно или вместе с тренером.</p>
    {editing ? <p className="mt-2 text-sm text-ink-soft">Если не менять эти сведения, сервер проверит сохранённые ограничения выбранного цикла. Новые значения требуют нового предпросмотра.</p> : null}
    <label className="mt-3 block text-sm text-ink-soft">Полнота записанной истории
      <select aria-label="Полнота записанной истории" value={coverage?.status ?? "unknown"} className={inputClass}
        onChange={e => onCoverage({ status: e.target.value as HistoryCoverage["status"],
          ...(e.target.value !== "unknown" ? { start_date: coverage?.start_date ?? "", end_date_exclusive: coverage?.end_date_exclusive ?? "" } : {}) })}>
        <option value="unknown">Полнота не подтверждена</option>
        <option value="partial">Записана часть занятий</option>
        <option value="user_reported_complete">Все занятия за указанный период записаны</option>
      </select>
    </label>
    {coverage && coverage.status !== "unknown" ? <div className="mt-3 grid gap-3 sm:grid-cols-2">
      <label className="min-w-0 text-sm text-ink-soft">История: с
        <input aria-label="История: с" type="date" className={inputClass} value={coverage.start_date ?? ""} onChange={e => onCoverage({ ...coverage, start_date: e.target.value })} />
      </label>
      <label className="min-w-0 text-sm text-ink-soft">История: по (не включая)
        <input aria-label="История: по (не включая)" type="date" className={inputClass} value={coverage.end_date_exclusive ?? ""} onChange={e => onCoverage({ ...coverage, end_date_exclusive: e.target.value })} />
      </label>
    </div> : null}
    <p className="mt-2 text-sm text-ink-soft">Полнота — ваше подтверждение записей, а не результат синхронизации. Сервис проверит достаточность указанного периода.</p>
    <div className="mt-4 space-y-3">
      {sports.map(sport => {
        const row = draft[sport], label = ENTRY_SPORT_LABELS[sport];
        return <fieldset key={sport} className="rounded-lg border border-surface-border p-3">
          <legend className="px-1 text-sm text-ink">
            <label className="flex items-center gap-2"><input type="checkbox" aria-label={`Указать ограничения: ${label}`} checked={!!row}
              onChange={e => { const next = { ...draft }; if (e.target.checked) next[sport] = { weekly: "", sessions: "", longest: "" }; else delete next[sport]; onDraft(next); }} />Указать ограничения: {label}</label>
          </legend>
          {row ? <div className="grid gap-3 sm:grid-cols-3">
            {([{ key: "weekly", name: "минут за 7 дней" }, { key: "sessions", name: "занятий за 7 дней" }, { key: "longest", name: "максимум минут за занятие" }] as const).map(field =>
              <label key={field.key} className="min-w-0 text-sm text-ink-soft">{field.name}
                <input type="number" aria-label={`${label}: ${field.name}`} min={field.key === "sessions" ? "1" : "0"} step={field.key === "sessions" ? "1" : "any"}
                  value={row[field.key]} className={inputClass} onChange={e => onDraft({ ...draft, [sport]: { ...row, [field.key]: e.target.value } })} />
              </label>)}
          </div> : <p className="text-sm text-ink-soft">По записанной истории, если её достаточно. Положительный объём по умолчанию не подставляется.</p>}
        </fieldset>;
      })}
    </div>
    <p className="mt-3 text-sm text-ink-soft">Это верхние ограничения начальной нагрузки, не цель заполнить всё время. Они не подтверждают медицинскую безопасность плана.</p>
    {!entryFieldsValid(coverage, draft, sports) ? <p role="status" className="mt-2 text-sm text-tone-warning">Укажите период истории и заполните выбранные ограничения положительными числами. Число занятий должно быть целым, максимум за занятие — не больше общего времени.</p> : null}
  </section>;
}

const reasonText: Record<string, string> = {
  entry_dose_required: "Укажите стартовые ограничения или подтвердите полноту записанной истории, если в ней есть эти занятия.",
  entry_window_exceeded: "Объём или число занятий превышает стартовое ограничение.",
  entry_session_exceeded: "Длительность занятия превышает заданный максимум.",
  entry_sport_missing: "В допустимых пределах не удалось назначить занятия этой дисциплины.",
  execution_identity_ambiguous: "Уточните связь выполненных занятий с планом во вкладке «Выполнение».",
  execution_partition_ambiguous: "Уточните связь выполненных занятий с планом во вкладке «Выполнение».",
  entry_dose_unverified: "Назначение не удалось проверить. Уточните сведения и пересоберите план.",
};
const roleText: Record<string, string> = { off: "отдых", recovery: "восстановление", easy: "лёгкая", quality: "интенсивная", long: "длительная", activation: "активация", race: "старт" };
const minutes = (value: number) => `${value.toLocaleString("ru-RU", { maximumFractionDigits: 1 })} мин`;

export function EntryLoadSummary({ assessment, adjustments = [], onEdit }: { assessment: EntryLoadAssessment; adjustments?: EntryDoseAdjustment[] | null; onEdit?: () => void }) {
  const supported = assessment.status === "supported" && assessment.can_publish;
  const heading = supported ? "Начальная нагрузка согласована с ограничениями" : assessment.status === "needs_baseline" ? "Нужны данные для начальной нагрузки" : assessment.status === "blocked" ? "План не укладывается в ограничения" : "Начальная нагрузка не проверена";
  const profile = assessment.profile;
  return <section aria-label="Проверка начальной нагрузки" className={`mt-4 rounded-card border p-4 ${supported ? "border-surface-border bg-surface" : "border-tone-warning/40 bg-tone-warning/5"}`}>
    <h3 className="text-sm font-semibold text-ink">{heading}</h3>
    {assessment.scope ? <p className="mt-1 text-sm text-ink-soft">Начальный период: {assessment.scope.start_date} — {assessment.scope.end_date}.</p> : null}
    <p className="mt-1 text-sm text-ink-soft">Проверка ограничений не оценивает медицинскую безопасность и достижение тренировочной цели.</p>
    {assessment.blockers.length ? <ul className="mt-3 space-y-2 text-sm text-ink">{assessment.blockers.map((reason, index) => <li key={index}>
      {reason.sport ? `${ENTRY_SPORT_LABELS[reason.sport]}: ` : ""}{reason.date ? `${reason.date} · ` : ""}{reasonText[reason.code] ?? "Не удалось согласовать назначение. Проверьте сведения и ограничения, затем пересоберите план."}
    </li>)}</ul> : null}
    {profile ? <details className="mt-3 text-sm text-ink-soft"><summary className="cursor-pointer py-1">Записанная история и источники ограничений</summary>
      <p className="mt-2">Записи за {profile.window_start} — {profile.window_end_exclusive} (последняя дата не включается).</p>
      <p>{profile.completeness.status === "user_reported_complete" ? "Полнота подтверждена вами." : profile.completeness.status === "partial" ? "Вы указали, что история неполная." : "Полнота истории не подтверждена: отсутствие записей не доказывает отсутствие занятий."}</p>
      <dl className="mt-3 space-y-3">{(Object.keys(ENTRY_SPORT_LABELS) as EntrySport[]).map(sport => {
        const observed = profile.sports[sport], cap = assessment.limits[sport];
        return <div key={sport}><dt className="font-medium text-ink">{ENTRY_SPORT_LABELS[sport]}</dt>
          <dd>В записи: {observed.session_count} занятий · {minutes(observed.observed_minutes)} с известной длительностью.</dd>
          {cap ? <dd>{cap.source === "observed_reference" ? "По записанной истории" : "Задано вами"}: до {minutes(cap.weekly_minutes)} за 7 дней, до {cap.weekly_sessions} занятий; максимум {minutes(cap.max_session_minutes)} за занятие.
            {cap.source_window ? <span className="block">Источник: {cap.source_window.start_date} — {cap.source_window.end_date_exclusive} (последняя дата не включается).</span> : null}
            {cap.declared_ceiling ? <span className="block">Также учтён заданный вами верхний предел.</span> : null}
          </dd> : <dd>Начальный объём не задан.</dd>}
        </div>;
      })}</dl>
      {profile.quality_limits.length ? <p className="mt-2">Есть ограничения качества записей ({profile.quality_limits.length}); они учтены при проверке.</p> : null}
    </details> : null}
    {assessment.warnings.some(w => w.code === "entry_limits_retained") ? <p className="mt-2 text-sm text-ink-soft">Сохранены стартовые ограничения выбранного цикла; новая история показана отдельно.</p> : null}
    {adjustments?.length ? <details className="mt-3 text-sm text-ink-soft"><summary className="cursor-pointer py-1">Изменения назначений: {adjustments.length}</summary>
      <ul className="mt-2 space-y-2">{adjustments.map((change, index) => <li key={`${change.date}-${index}`}>
        {change.date} · {change.sport === "brick" ? "вело → бег" : change.sport ? ENTRY_SPORT_LABELS[change.sport] : "занятие"}: {change.kind === "completed_assignment_retired" ? "выполнение учтено, назначение убрано" : change.kind === "removed_at_entry_limit" ? "убрано из расписания из-за ограничения" : "длительность изменена"}
        {change.from_minutes != null && change.to_minutes != null ? ` · ${minutes(change.from_minutes)} → ${minutes(change.to_minutes)}` : ""}
        {change.from_role && change.to_role && change.from_role !== change.to_role ? ` · ${roleText[change.from_role] ?? "другое назначение"} → ${roleText[change.to_role] ?? "другое назначение"}` : ""}
      </li>)}</ul>
    </details> : null}
    {onEdit ? <button type="button" onClick={onEdit} className="mt-3 rounded-lg border border-surface-border px-3 py-2 text-sm text-ink">Уточнить историю и ограничения</button> : null}
  </section>;
}
