const DATA_SOURCE_LABELS: Record<string, string> = {
  intervals: "Intervals.icu",
  intervals_icu: "Intervals.icu",
  garmin: "Garmin Connect",
  demo: "демо",
  mixed: "смешанные источники",
  derived: "расчётная",
  derived_awake_time: "по времени бодрствования",
  derived_sleep_window: "по окну сна",
  unavailable: "нет исходных данных",
  legacy_unknown: "источник не сохранён",
};

export function dataSourceLabel(source?: string | null): string {
  if (!source) return "источник не сохранён";
  return DATA_SOURCE_LABELS[source.trim().toLowerCase()] ?? "источник не сохранён";
}

export function syncSourceLabel(source?: string | null): string {
  if (source === "intervals") return "Intervals.icu";
  if (source === "garmin") return "Garmin Connect";
  return "данных";
}
