import { Suspense } from "react";
import { SwimWorkspace } from "@/components/swim/SwimWorkspace";

export default function SwimProgramsPage() {
  return <Suspense fallback={<p className="text-sm text-ink-soft">Загружаем программы…</p>}><SwimWorkspace /></Suspense>;
}
