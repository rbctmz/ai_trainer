import { Suspense } from "react";
import { SwimCalendarWorkspace } from "@/components/planning/SwimCalendarWorkspace";

export default function SwimCalendarPage() {
  return <Suspense fallback={<p className="text-sm text-ink-soft">Загружаем календарь…</p>}>
    <SwimCalendarWorkspace />
  </Suspense>;
}
