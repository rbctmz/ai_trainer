"use client";

import type { WorkoutStep, WorkoutTarget } from "@/lib/types";

// #413: визуальная сегментная полоса плановой структуры тренировки.
// Ширина сегмента = длительность, высота = интенсивность (профиль нагрузки),
// цвет — по segment_kind/intensity, подпись/тултип — длительность + цель.
// Переиспользуется на «Сегодня», в планировании и (Фаза 2) в карточке.

const SEGMENT_TONES: Record<string, string> = {
  warmup: "bg-ink-faint/25",
  cooldown: "bg-ink-faint/25",
  recovery: "bg-tone-success/30",
  easy: "bg-tone-success/30",
  steady: "bg-tone-warning/40",
  work: "bg-tone-danger/40",
};

function segmentTone(step: WorkoutStep): string {
  const kind = String(step.segment_kind || "").toLowerCase();
  if (kind === "warmup" || kind === "cooldown") return SEGMENT_TONES.warmup;
  if (kind === "recovery") return SEGMENT_TONES.recovery;
  if (kind === "work") return SEGMENT_TONES.work;
  // Generic `stage` (recovery/endurance prescriptions use intensity "steady"):
  // color by intensity — a stage is NOT automatically hard work (review P2).
  const intensity = String(step.intensity || "").toLowerCase();
  return SEGMENT_TONES[intensity] ?? "bg-ink-faint/10";
}

// Высота сегмента кодирует интенсивность (профиль нагрузки): разминка и
// восстановление — низкие, work — полный рост.
const SEGMENT_HEIGHTS: Record<string, number> = {
  warmup: 32,
  cooldown: 32,
  recovery: 32,
  easy: 52,
  steady: 72,
  work: 100,
};

function segmentHeight(step: WorkoutStep): number {
  const kind = String(step.segment_kind || "").toLowerCase();
  if (kind === "warmup" || kind === "cooldown" || kind === "recovery") {
    return SEGMENT_HEIGHTS.warmup;
  }
  if (kind === "work") return SEGMENT_HEIGHTS.work;
  const intensity = String(step.intensity || "").toLowerCase();
  return SEGMENT_HEIGHTS[intensity] ?? 42;
}

function shortLabel(step: WorkoutStep, index: number): string {
  const name = String(step.name || "").trim();
  return name || `Шаг ${index + 1}`;
}

function formatDuration(seconds: number | null): string {
  if (!seconds || seconds <= 0) return "—";
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return rest ? `${minutes}:${String(rest).padStart(2, "0")}` : `${minutes} мин`;
}

function formatPace(secondsPerUnit: number): string {
  const total = Math.max(0, Math.round(secondsPerUnit));
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

function formatTarget(target: WorkoutTarget | null): string {
  if (!target) return "";
  const type = String(target.type || "");
  const low = target.low;
  const high = target.high;
  if (type === "power" && low != null && high != null) return `${low}–${high} Вт`;
  if (type === "heart_rate" && low != null && high != null) {
    return `${low}–${high} уд/мин`;
  }
  if (type === "relative_rpe" && low != null && high != null) {
    return `RPE ${low}–${high}`;
  }
  if (
    type.includes("pace") &&
    target.fast != null &&
    target.slow != null
  ) {
    return `${formatPace(target.fast)}–${formatPace(target.slow)}`;
  }
  if (type === "distance" && low != null) return `${low} м`;
  return type;
}

export function WorkoutStrip({
  steps,
  ariaLabel,
}: {
  steps: WorkoutStep[];
  ariaLabel?: string;
}) {
  if (!steps.length) return null;
  const total = steps.reduce(
    (sum, step) => sum + Math.max(0, Number(step.duration_seconds) || 0),
    0,
  );
  if (total <= 0) return null;

  const summary =
    ariaLabel ??
    steps
      .map((step, index) => {
        const target = formatTarget(step.target);
        return `${shortLabel(step, index)} ${formatDuration(step.duration_seconds)}${
          target ? ` · ${target}` : ""
        }`;
      })
      .join(", ");

  return (
    <div
      role="img"
      aria-label={summary}
      className="mt-2 flex h-14 w-full items-end overflow-hidden rounded border border-surface-border"
    >
      {steps.map((step, index) => {
        const seconds = Math.max(0, Number(step.duration_seconds) || 0);
        if (seconds <= 0) return null;
        const pct = (seconds / total) * 100;
        const heightPct = segmentHeight(step);
        const target = formatTarget(step.target);
        const title = `${shortLabel(step, index)} · ${formatDuration(seconds)}${
          target ? ` · ${target}` : ""
        }`;
        return (
          <div
            key={`${step.name}-${index}`}
            title={title}
            className={`flex flex-none items-start justify-center overflow-hidden px-0.5 pt-1 text-[9px] font-medium text-ink ${segmentTone(step)}`}
            style={{ width: `${pct}%`, height: `${heightPct}%` }}
          >
            {pct >= 9 && heightPct >= 50 ? (
              <span className="truncate">{shortLabel(step, index)}</span>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
