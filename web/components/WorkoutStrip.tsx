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

// Высота сегмента кодирует относительную интенсивность (профиль нагрузки):
// target.relative_high (% FTP / % порогового темпа) — работает и для вело,
// и для бега; плавание (relative_rpe) — по RPE; фолбэк — уровни intensity.
const SEGMENT_HEIGHTS: Record<string, number> = {
  warmup: 32,
  cooldown: 32,
  recovery: 32,
  easy: 52,
  steady: 72,
  work: 100,
};
const RPE_SCALE_MAX = 10;

function clampHeight(value: number): number {
  return Math.max(28, Math.min(100, Math.round(value)));
}

function segmentHeight(step: WorkoutStep): number {
  const target = step.target;
  if (target) {
    const relative = target.relative_high;
    if (
      typeof relative === "number" &&
      Number.isFinite(relative) &&
      relative > 0
    ) {
      return clampHeight(relative * 100);
    }
    if (String(target.type || "") === "relative_rpe") {
      const low = Number(target.low);
      const high = Number(target.high);
      if (Number.isFinite(low) && Number.isFinite(high) && high > 0) {
        return clampHeight(((low + high) / 2 / RPE_SCALE_MAX) * 100);
      }
    }
  }
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

export interface StripSegment {
  seconds: number;
  label: string;
  title: string;
  tone: string;
  heightPct: number;
}

/** Низкоуровневая полоса сегментов с общей шкалой (ширина = доля от scaleSeconds). */
export function StripBar({
  segments,
  scaleSeconds,
  ariaLabel,
  label,
}: {
  segments: StripSegment[];
  scaleSeconds: number;
  ariaLabel?: string;
  label?: string;
}) {
  if (!segments.length || scaleSeconds <= 0) return null;

  return (
    <div>
      {label ? (
        <div className="mb-0.5 text-[10px] text-ink-faint">{label}</div>
      ) : null}
      <div
        role="img"
        aria-label={ariaLabel ?? segments.map((segment) => segment.title).join(", ")}
        className="flex h-14 w-full items-end overflow-hidden rounded border border-surface-border"
      >
        {segments.map((segment, index) => {
          const pct = (segment.seconds / scaleSeconds) * 100;
          // Краевые сегменты подписываем всегда; середина — только если
          // сегмент достаточно широкий и высокий.
          const isEdge = index === 0 || index === segments.length - 1;
          const showLabel = isEdge || (pct >= 9 && segment.heightPct >= 50);
          return (
            <div
              key={index}
              title={segment.title}
              className={`flex flex-none items-start justify-center overflow-hidden px-0.5 pt-1 text-[9px] font-medium text-ink ${segment.tone}`}
              style={{ width: `${pct}%`, height: `${segment.heightPct}%` }}
            >
              {showLabel ? <span className="truncate">{segment.label}</span> : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function WorkoutStrip({
  steps,
  ariaLabel,
}: {
  steps: WorkoutStep[];
  ariaLabel?: string;
}) {
  if (!steps.length) return null;
  const segments: StripSegment[] = [];
  let total = 0;
  steps.forEach((step, index) => {
    const seconds = Math.max(0, Number(step.duration_seconds) || 0);
    if (seconds <= 0) return;
    total += seconds;
    const label = shortLabel(step, index);
    const target = formatTarget(step.target);
    segments.push({
      seconds,
      label,
      title: `${label} · ${formatDuration(seconds)}${
        target ? ` · ${target}` : ""
      }`,
      tone: segmentTone(step),
      heightPct: segmentHeight(step),
    });
  });
  if (!segments.length || total <= 0) return null;
  return (
    <StripBar
      segments={segments}
      scaleSeconds={total}
      ariaLabel={
        ariaLabel ?? segments.map((segment) => segment.title).join(", ")
      }
    />
  );
}
