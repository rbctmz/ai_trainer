import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { DailyOutlook } from "@/components/dashboard/DailyOutlook";
import { StatusRow } from "@/components/dashboard/StatusRow";
import { TrainingScore } from "@/components/dashboard/TrainingScore";
import { WeekStrip } from "@/components/dashboard/WeekStrip";
import { ShowcaseStateCard } from "@/components/showcase/ShowcaseStateCard";
import { showDevTools } from "@/lib/flags";
import {
  showcaseOutlook,
  showcaseToday,
  showcaseTrainingScore,
  showcaseWeek,
} from "@/lib/showcaseFixtures";

export const metadata: Metadata = {
  title: "Компоненты · AI Trainer",
  description: "Изолированный dev-only showcase компонентов AI Trainer",
};

export default function ComponentShowcasePage() {
  if (!showDevTools) redirect("/today");

  return (
    <main className="space-y-8" data-testid="component-showcase">
      <header className="rounded-card border border-dashed border-tone-warning/40 bg-tone-warning/5 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-bold text-ink">Showcase компонентов</h1>
          <span className="rounded-full bg-tone-warning/15 px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-tone-warning">
            dev-only
          </span>
        </div>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-ink-soft">
          Статические fixtures показывают визуальные состояния без API, SQLite, credentials и
          персональных данных. Они повторяют форму продуктовых DTO, но не вычисляют тренировочную
          семантику в браузере.
        </p>
      </header>

      <section aria-labelledby="dashboard-components" className="space-y-4">
        <div>
          <h2 id="dashboard-components" className="text-lg font-semibold text-ink">
            Dashboard-композиция
          </h2>
          <p className="mt-1 text-sm text-ink-soft">
            Реальные presentational-компоненты на детерминированных типизированных данных.
          </p>
        </div>
        <StatusRow today={showcaseToday} />
        <div className="grid gap-4 md:grid-cols-2">
          <TrainingScore data={showcaseTrainingScore} />
          <DailyOutlook data={showcaseOutlook} />
        </div>
        <WeekStrip days={showcaseWeek} />
      </section>

      <section aria-labelledby="component-states" className="space-y-4">
        <div>
          <h2 id="component-states" className="text-lg font-semibold text-ink">
            Состояния поверхности
          </h2>
          <p className="mt-1 text-sm text-ink-soft">
            Сетка складывается в одну колонку на узком экране и раскрывается до четырёх на широком.
          </p>
        </div>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <ShowcaseStateCard state="normal" title="Карточка прогноза">
            <DailyOutlook data={showcaseOutlook} />
          </ShowcaseStateCard>
          <ShowcaseStateCard state="loading" title="Карточка прогноза" />
          <ShowcaseStateCard state="empty" title="Карточка прогноза" />
          <ShowcaseStateCard state="error" title="Карточка прогноза" />
        </div>
      </section>

      <aside className="rounded-card border border-surface-border bg-surface p-4 text-sm text-ink-soft shadow-card">
        Нужен новый DTO или другая бизнес-семантика? Остановите UI-slice и передайте точный
        contract handoff роли Spec / Architecture Owner или Domain / API Implementer.
      </aside>
    </main>
  );
}
