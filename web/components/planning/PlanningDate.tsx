const dateFormat = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });

export function PlanningDate({ value }: { value: string }) {
  const date = new Date(`${value}T00:00:00Z`);
  // Display valid date-only values without timezone shifts or normalization.
  const valid = /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
  return valid ? <time dateTime={value}>{dateFormat.format(date)}</time> : <span>Дата не указана</span>;
}

