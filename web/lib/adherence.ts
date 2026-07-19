import type { AdherenceDayStatus } from "@/lib/types";

// Статусы приезжают ГОТОВЫМИ из /api/adherence (models/adherence_ribbon.py):
// web только раскрашивает и подписывает, никогда не пере-выводит их сам.
// Единый источник меток для страницы /adherence и строки на /today.
export const STATUS_META: Record<
  AdherenceDayStatus,
  { label: string; chip: string }
> = {
  exact: { label: "По плану", chip: "bg-tone-success/15 text-tone-success" },
  substituted: { label: "Заменено", chip: "bg-tone-success/10 text-ink-soft" },
  major_deviation: {
    label: "Сильное отклонение",
    chip: "bg-tone-warning/15 text-tone-warning",
  },
  missed: { label: "Пропущено", chip: "bg-tone-danger/15 text-tone-danger" },
  unknown: { label: "Матч без оценки", chip: "bg-surface-muted text-ink-soft" },
  unplanned: { label: "Вне плана", chip: "bg-tone-warning/10 text-tone-warning" },
  rest: { label: "Отдых", chip: "bg-surface-muted text-ink-faint" },
};

const WEEKDAY_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

export function adherenceDayLabel(iso: string): string {
  const parsed = new Date(`${iso}T00:00:00`);
  const weekday = WEEKDAY_SHORT[(parsed.getDay() + 6) % 7];
  return `${weekday} ${iso.slice(8, 10)}.${iso.slice(5, 7)}`;
}
