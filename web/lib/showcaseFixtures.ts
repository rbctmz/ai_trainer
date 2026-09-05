import type {
  DailyOutlookData,
  NextDay,
  TodayState,
  TrainingScoreData,
} from "@/lib/types";

// Static presentation fixtures only. Keep them shaped by product DTOs and do
// not reproduce server-owned calculations in the showcase.
export const showcaseToday = {
  date: "2026-09-07",
  state_label: "Контролируемая нагрузка",
  tone: "success",
  readiness: 78,
  tsb: 6,
  ctl: 52,
  hrv: 48,
} satisfies TodayState;

export const showcaseOutlook = {
  text: "Готовность стабильна: сегодня подходит ровная аэробная работа без добавления незапланированной интенсивности.",
  tone: "success",
} satisfies DailyOutlookData;

export const showcaseTrainingScore = {
  total: 76,
  label: "устойчиво",
  fitness: { score: 82, label: "форма растёт", detail: "CTL 52" },
  progression: { score: 74, label: "по плану", detail: "+4 за 4 нед." },
  consistency: { score: 79, label: "стабильно", detail: "5 из 6" },
  load_mgmt: { score: 68, label: "контроль", detail: "TSB +6" },
} satisfies TrainingScoreData;

export const showcaseWeek = [
  {
    date: "2026-09-07",
    label: "Пн",
    status: "today",
    status_label: "Сегодня",
    sport: "Бег",
    tss: 48,
  },
  {
    date: "2026-09-08",
    label: "Вт",
    status: "planned",
    status_label: "Запланировано",
    sport: "Вело",
    tss: 62,
  },
  {
    date: "2026-09-09",
    label: "Ср",
    status: "rest",
    status_label: "Отдых",
    sport: "Отдых",
    tss: 0,
  },
  {
    date: "2026-09-10",
    label: "Чт",
    status: "planned",
    status_label: "Запланировано",
    sport: "Плавание",
    tss: 45,
  },
  {
    date: "2026-09-11",
    label: "Пт",
    status: "done",
    status_label: "Выполнено",
    sport: "Бег",
    tss: 36,
  },
  {
    date: "2026-09-12",
    label: "Сб",
    status: "planned",
    status_label: "Запланировано",
    sport: "Вело",
    tss: 88,
  },
  {
    date: "2026-09-13",
    label: "Вс",
    status: "empty",
    status_label: "Нет сессии",
    sport: "—",
    tss: 0,
  },
] satisfies NextDay[];
