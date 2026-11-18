import Link from "next/link";
import { metres } from "@/components/swim/ProgramStructure";
import type { SwimCalendarRow } from "@/lib/types";

export function AuthoredSwimRow({ row, showDate = false }: { row: SwimCalendarRow; showDate?: boolean }) {
  const distance = row.distance_meters === null
    ? `Дистанция неизвестна · известно ${metres(row.known_distance_meters)}`
    : metres(row.distance_meters);
  return <div className="space-y-1 break-words text-sm">
    <p className="font-medium text-ink">
      {showDate ? <time dateTime={row.date} className="mr-2">{row.date}</time> : null}
      <Link href={`/coach/swim?program=${row.program_id}&revision=${row.program_revision}`} className="text-ink underline">
        {row.title}
      </Link>
    </p>
    <p className="text-ink-soft">
      Тренировка тренера · версия {row.program_revision} · {row.environment === "pool" ? `бассейн ${row.pool_length_meters} м` : "открытая вода"} · {distance}
    </p>
    {row.source_week_label ? <p className="text-ink-soft">Неделя тренера «{row.source_week_label}»</p> : null}
    <p className="text-ink-soft">Длительность и TSS неизвестны</p>
    {row.date_review_reason ? <p className="border-l-2 border-tone-warning pl-2 text-ink">
      {row.date_review_reason} Проверьте дату в календаре.
    </p> : null}
    {row.distance_compatibility === "incompatible" ? <p className="text-tone-warning">Проверьте длину отрезков для этого бассейна.</p> : null}
  </div>;
}
