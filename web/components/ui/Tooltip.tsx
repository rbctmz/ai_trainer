"use client";
import { useRef, useState } from "react";

function TooltipPopover({ content }: { content: React.ReactNode }) {
  return (
    <div className="text-left text-[11px] text-ink leading-relaxed">
      {content}
    </div>
  );
}

// ---- Per-metric tooltip content ----------------------------------------

function StateContent() {
  return (
    <>
      <p className="mb-1.5 text-xs font-semibold text-ink">Тренировочное состояние</p>
      <p className="mb-2 text-ink-soft">Комбинирует готовность (HRV/сон) и TSB — проверяется в этом порядке:</p>
      <div className="space-y-1.5">
        {[
          { color: "text-tone-danger",   label: "Критическое предупреждение", desc: "срабатывает специфический сигнал в данных (например, признаки перетренированности)." },
          { color: "text-tone-success",  label: "Готов к работе",        desc: "готовность ≥ 75 и TSB > −10." },
          { color: "text-tone-warning",  label: "Нужна разгрузка",       desc: "TSB < −20, независимо от готовности." },
          { color: "text-tone-neutral",  label: "Контролируемая нагрузка", desc: "ничего из перечисленного выше — промежуточное состояние." },
        ].map(({ color, label, desc }) => (
          <div key={label} className="flex gap-1.5">
            <span className={`mt-0.5 shrink-0 ${color}`}>●</span>
            <div><span className="font-medium">{label}</span> — {desc}</div>
          </div>
        ))}
      </div>
    </>
  );
}

function ReadinessContent() {
  return (
    <>
      <p className="mb-1.5 text-xs font-semibold text-ink">Готовность (0–100)</p>
      <p className="mb-2 text-ink-soft">Оценивает готовность организма на основе HRV, качества сна и баланса нагрузки (TSB).</p>
      <div className="space-y-0.5">
        {[
          ["< 40",  "text-tone-danger",  "нужен отдых"],
          ["40–70", "text-tone-warning", "умеренная нагрузка"],
          ["> 70",  "text-tone-success", "можно выкладываться"],
        ].map(([range, cls, label]) => (
          <div key={range} className="flex justify-between gap-4">
            <span className={cls}>{range}</span><span className="text-ink-soft">{label}</span>
          </div>
        ))}
      </div>
    </>
  );
}

// Mirrors api/routers/dashboard.py::_TSB_ZONES — keep boundaries/labels in
// sync by hand if that table changes.
function TsbContent() {
  return (
    <>
      <p className="mb-1.5 text-xs font-semibold text-ink">TSB — Training Stress Balance</p>
      <p className="mb-2 text-ink-soft">Свежесть = долгосрочная форма (CTL) − краткосрочная усталость (ATL).</p>
      <div className="space-y-0.5">
        {[
          ["< −20",   "text-tone-danger",  "высокая усталость"],
          ["−20..−10","text-tone-warning", "накопленная усталость"],
          ["−10..+10","text-tone-neutral", "стабильная нагрузка"],
          ["> +10",   "text-tone-success", "свежесть"],
        ].map(([range, cls, label]) => (
          <div key={range} className="flex justify-between gap-4">
            <span className={cls}>{range}</span><span className="text-ink-soft">{label}</span>
          </div>
        ))}
      </div>
    </>
  );
}

function CtlContent() {
  return (
    <>
      <p className="mb-1.5 text-xs font-semibold text-ink">CTL — Chronic Training Load</p>
      <p className="text-ink-soft">Долгосрочная «форма» — экспоненциальное среднее TSS за 42 дня. Растёт при регулярных тренировках, снижается при перерывах {'>'} 1–2 недель.</p>
    </>
  );
}

function HrvContent() {
  return (
    <>
      <p className="mb-1.5 text-xs font-semibold text-ink">HRV — Вариабельность сердечного ритма</p>
      <p className="text-ink-soft">Высокое HRV → хорошее восстановление нервной системы. Резкое снижение → стресс, болезнь или накопленная усталость.</p>
    </>
  );
}

function SleepScoreContent() {
  return (
    <>
      <p className="mb-1.5 text-xs font-semibold text-ink">Оценка сна (0–100)</p>
      <p className="mb-2 text-ink-soft">Источник данных рассчитывает оценку по доступным показателям сна; методика зависит от подключённого провайдера.</p>
      <div className="space-y-0.5">
        {[
          ["< 60", "text-tone-danger",  "плохой сон"],
          ["60–80","text-tone-warning", "нормально"],
          ["> 80", "text-tone-success", "хорошо"],
        ].map(([range, cls, label]) => (
          <div key={range} className="flex justify-between gap-4">
            <span className={cls}>{range}</span><span className="text-ink-soft">{label}</span>
          </div>
        ))}
      </div>
    </>
  );
}

function TrainingScoreContent() {
  return (
    <>
      <p className="mb-2 text-xs font-semibold text-ink">Как считается Training Score</p>
      <div className="mb-2 space-y-1">
        {[
          ["Форма (CTL)",              "30%"],
          ["Прогресс (ramp rate)",     "25%"],
          ["Регулярность (adherence)", "25%"],
          ["Нагрузка (TSB zone)",      "20%"],
        ].map(([label, weight]) => (
          <div key={label} className="flex justify-between gap-4">
            <span className="text-ink-soft">{label}</span>
            <span className="font-semibold text-ink">{weight}</span>
          </div>
        ))}
      </div>
      <p className="text-ink-faint">Итог 0–100. {'>'} 70 — отлично, 40–70 — нормально, {'<'} 40 — нужна работа.</p>
    </>
  );
}

// ---- Registry ----------------------------------------------------------

const TIPS: Record<string, React.ReactNode> = {
  state:          <StateContent />,
  readiness:      <ReadinessContent />,
  tsb:            <TsbContent />,
  ctl:            <CtlContent />,
  hrv:            <HrvContent />,
  sleep_score:    <SleepScoreContent />,
  training_score: <TrainingScoreContent />,
};

// ---- Base Tooltip component --------------------------------------------

export function Tooltip({
  content,
  children,
}: {
  content: React.ReactNode;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>();

  const show = () => { clearTimeout(timer.current); setOpen(true); };
  const hide = () => { timer.current = setTimeout(() => setOpen(false), 150); };

  return (
    <div className="relative inline-flex" onMouseEnter={show} onMouseLeave={hide}>
      <div onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }}>
        {children}
      </div>
      {open && (
        <div
          className="absolute bottom-full right-0 z-50 mb-2 w-60 rounded-xl border border-surface-border bg-surface p-3 shadow-xl"
          onMouseEnter={show}
          onMouseLeave={hide}
        >
          <TooltipPopover content={content} />
        </div>
      )}
    </div>
  );
}

// ---- Public API --------------------------------------------------------

/** Small ⓘ icon that shows a pre-defined metric tooltip on hover/tap. */
export function InfoTip({ metric }: { metric: keyof typeof TIPS }) {
  const content = TIPS[metric];
  if (!content) return null;
  return (
    <Tooltip content={content}>
      <span className="cursor-help select-none text-[11px] leading-none text-ink-faint transition-colors hover:text-ink-soft">
        ⓘ
      </span>
    </Tooltip>
  );
}
