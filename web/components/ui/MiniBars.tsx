export function MiniBars({
  values,
  labels,
  unit = "",
  height = "h-16",
}: {
  values: number[];
  labels?: string[];
  unit?: string;
  height?: string;
}) {
  if (values.length < 2) {
    return <div className="text-xs text-ink-faint">Недостаточно точек.</div>;
  }
  const max = Math.max(...values, 1);
  return (
    <div className={`flex items-end gap-1 ${height}`}>
      {values.map((v, i) => (
        <div
          key={i}
          className="flex-1 rounded-t bg-tone-neutral/80"
          style={{ height: `${Math.max(4, (v / max) * 100)}%` }}
          title={labels ? `${labels[i]}: ${v}${unit}` : `${v}${unit}`}
        />
      ))}
    </div>
  );
}
