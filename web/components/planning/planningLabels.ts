export const GOAL_TYPES = [
  { value: "triathlon", label: "Триатлон" },
  { value: "run", label: "Бег" },
  { value: "bike", label: "Вело" },
];

export const DISTANCES: Record<string, { value: string; label: string }[]> = {
  triathlon: [
    { value: "sprint", label: "Спринт" },
    { value: "olympic", label: "Олимпийка" },
    { value: "half", label: "Half (70.3)" },
    { value: "ironman", label: "Ironman" },
  ],
  run: [
    { value: "5k", label: "5 км" },
    { value: "10k", label: "10 км" },
    { value: "half_marathon", label: "Полумарафон" },
    { value: "marathon", label: "Марафон" },
    { value: "ultra", label: "Ультра" },
  ],
  bike: [
    { value: "40k_tt", label: "40 км TT" },
    { value: "100k", label: "100 км" },
    { value: "100mi", label: "100 миль" },
    { value: "brevet", label: "200 км (бревет)" },
    { value: "stage_race", label: "Этапная гонка" },
  ],
};

export const DAYS = [
  { value: "mon", label: "Пн" },
  { value: "tue", label: "Вт" },
  { value: "wed", label: "Ср" },
  { value: "thu", label: "Чт" },
  { value: "fri", label: "Пт" },
  { value: "sat", label: "Сб" },
  { value: "sun", label: "Вс" },
];

export function phaseLabel(value: string): string {
  return ({ Base: "Базовая подготовка", Build: "Развитие", Peak: "Пиковая подготовка", Taper: "Снижение нагрузки", Recovery: "Восстановление", "Race Week": "Стартовая неделя" } as Record<string, string>)[value] ?? "Фаза не указана";
}
