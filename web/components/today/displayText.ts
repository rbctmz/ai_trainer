// Presentation-only translations. Server action, eligibility and measurements stay unchanged.
const names: Record<string, string> = {
  run: "Бег", bike: "Вело", swim: "Плавание",
  "Recovery Run": "Восстановительный бег",
  "Aerobic Endurance Run": "Бег на выносливость",
  "Progression Run": "Бег с постепенным ускорением",
  "Tempo / Threshold Run": "Темповый / пороговый бег",
  "VO2 / Neuromuscular Run": "Бег: аэробная мощность и ускорения",
  "Race Pace Run": "Бег в соревновательном темпе",
  "Race Strides Run": "Предстартовые ускорения",
  "Recovery Spin": "Восстановительная велотренировка",
  "Aerobic Endurance Ride": "Велотренировка на выносливость",
  "Aerobic Progression Ride": "Велотренировка с ростом интенсивности",
  "Tempo / Sweet Spot": "Темповая велотренировка",
  "Threshold Intervals": "Пороговые интервалы",
  "VO2max Intervals": "Интервалы на аэробную мощность",
  "Neuromuscular Sprints": "Короткие спринты",
  "Race Pace Ride": "Вело в соревновательном темпе",
  "Race Openers Ride": "Предстартовая велотренировка",
  "Recovery Technique Swim": "Восстановительное плавание с техникой",
  "Technique + Aerobic Swim": "Плавание: техника и выносливость",
  "Endurance Brick": "Связка вело и бега на выносливость",
  "Race Pace Brick": "Связка вело и бега в соревновательном темпе",
  "Warm-up": "Разминка", "Easy warm-up": "Лёгкая разминка",
  "Cool-down": "Заминка", "Easy cool-down": "Лёгкая заминка",
  "Recovery": "Восстановительная часть", "Recoveries": "Восстановление",
  "Full recoveries": "Полное восстановление", "Easy reset": "Лёгкий участок",
  "Aerobic endurance": "Работа на выносливость", "Aerobic": "Аэробная часть",
  "Controlled aerobic": "Умеренная аэробная работа", "Progression": "Постепенное ускорение",
  "Moderate": "Умеренный участок", "Strong finish": "Ускорение в конце",
  "Steady finish": "Ровный заключительный участок", "Tempo blocks": "Темповые отрезки",
  "Threshold intervals": "Пороговые интервалы", "VO2 intervals": "Интервалы на аэробную мощность",
  "Technique drills": "Упражнения на технику", "Aerobic swim": "Плавание на выносливость",
  "Race-pace blocks": "Отрезки в соревновательном темпе", "Sprints": "Спринты",
  "Tempo": "Темповый отрезок", "Threshold": "Пороговый отрезок",
  "Sprint": "Спринт", "Race pace": "Соревновательный темп",
  "Opener": "Предстартовый отрезок", "Stride": "Ускорение",
};

export function workoutLabel(name: string): string {
  if (names[name]) return names[name];
  // Numbered catalog repeats keep their original numbering.
  const match = name.match(/^(.*?)( \d+)$/);
  return match && names[match[1]] ? names[match[1]] + match[2] : name;
}

export function decisionText(text: string): string {
  // Translate enum words inside an existing explanation; never generate a reason.
  return text.replace(
    /Готовность (\w+) \(([\d.]+)\/100\) не противоречит сессиям ближайших (\d+) дн\. — вмешательство не требуется\./g,
    "Оценка восстановления: $1 — $2 из 100. По этим данным план на ближайшие $3 дн. не требует изменений.",
  ).replace(/\b(ready|optimal|reduced|critical|low|unknown|data_gap)\b/g,
    (value) => ({ ready: "нормальная", optimal: "оптимальная", reduced: "сниженная",
      critical: "критически низкая", low: "низкая", unknown: "неизвестна",
      data_gap: "недостаточно данных" } as Record<string, string>)[value] ?? value);
}
