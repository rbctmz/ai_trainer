# Wizard-of-Oz tracking schema

`docs/woz_tracking.csv` is intentionally ignored by git because it contains personal health and training observations. This document is the committed schema contract; the CSV itself stays local.

Issue D adds `качество_сессии_1_5` as a distinct post-session observation. It must not replace `реакция_1_5`: the former measures how well the planned stimulus felt executable, while the latter measures the athlete's response to a recommendation.

The canonical column order is:

    дата,атлет,план_сессия,приоритет,readiness_балл,readiness_band,факторы,конфликт,severity,прогноз_качества_pct,рекомендация,действие_атлета,факт_исход,прогноз_попал,качество_сессии_1_5,реакция_1_5,заметка

For historical rows, insert an empty field before the existing `реакция_1_5` value. Do not infer a quality rating from TSS, Training Effect, adherence, or the recommendation reaction. New ratings use the pre-registered Issue D meaning: 1–2 failure, 3 ambiguous/unscored, 4–5 success.

The local migration is complete when every row parses to the same number of fields as the header and the existing `реакция_1_5` and `заметка` values are unchanged.
