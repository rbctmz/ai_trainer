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
      <p className="mb-2 text-xs font-semibold text-ink">Тренировочное состояние</p>
      <div className="space-y-1.5">
        {[
          { color: "text-tone-success",  label: "Суперкомпенсация", desc: "TSB > +10 — пик готовности. Время для гонки или личного рекорда." },
          { color: "text-tone-success",  label: "Оптимально",        desc: "TSB 0..+10 — хорошо для качественных тренировок." },
          { color: "text-tone-warning",  label: "Контролируемая нагрузка", desc: "TSB −10..0 — умеренная усталость, беречь интенсивность." },
          { color: "text-tone-danger",   label: "Глубокая усталость", desc: "TSB < −10 — приоритет: восстановление." },
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

function TsbContent() {
  return (
    <>
      <p className="mb-1.5 text-xs font-semibold text-ink">TSB — Training Stress Balance</p>
      <p className="mb-2 text-ink-soft">Свежесть = долгосрочная форма (CTL) − краткосрочная усталость (ATL).</p>
      <div className="space-y-0.5">
        {[
          ["< −10",  "text-tone-danger",  "высокая усталость"],
          ["−10..+5","text-tone-warning", "тренировочный блок"],
          ["+5..+15","text-tone-success", "идеал перед гонкой"],
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
      <p className="mb-2 text-ink-soft">Garmin рассчитывает из общей длительности, доли глубокого и REM сна, числа пробуждений и ЧСС во сне.</p>
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
