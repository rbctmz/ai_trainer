# Плавание: программа тренера, исполнение и учёт

Owner: Greg. Решение о реализации: 16.11.2026. Epic [#760](https://github.com/rbctmz/ai_trainer/issues/760).
Исследование выполнено на main `59c5435`: 144 existing tests и 4 synthetic probes.

## Пользовательский результат

Спортсмен вставляет программу своего тренера, проверяет структуру, выбирает среду
и дни, подтверждает сохранение и доставку, затем видит разбор выполнения по тем же
сериям. Исходник и версии сохраняются. Изменения предлагает AI, принимает человек.
Часы — FR255; сейчас бассейн 25м, возможен 50м, открытая вода — отдельная среда.
Отдых «три выдоха» остаётся инструкцией и open/Lap, субъективные 50–90% не CSS.

## Последовательность доставки

| Срез | Задача | Проверяемый результат | Зависимость |
| --- | --- | --- | --- |
| M1 | [#761](https://github.com/rbctmz/ai_trainer/issues/761) | Versioned Python document, библиотека/API, preview/confirm и история | Нет |
| M2A | [#767](https://github.com/rbctmz/ai_trainer/issues/767) | Личный справочник упражнений, версии и API; точный вариант → копия шага | M1 |
| M2B | [#769](https://github.com/rbctmz/ai_trainer/issues/769) | Сохранённый исходник, rich V2, точные версии упражнений, один редактируемый draft/API | M2A |
| M2 | [#762](https://github.com/rbctmz/ai_trainer/issues/762) | Текст → редактируемая структура рядом с оригиналом → сохранение через web | M1 |
| M2C | [#771](https://github.com/rbctmz/ai_trainer/issues/771) | Коуч читает/разбирает/правит один draft без authority save/send | M2B |
| M2D | [#772](https://github.com/rbctmz/ai_trainer/issues/772) | Полный web-сценарий, прямые/диалоговые правки, save/reload | M2B/M2C |
| M3 | [#763](https://github.com/rbctmz/ai_trainer/issues/763) | Даты/current cycle, защищённый оригинал, предложения/подтверждение/rollback | M1/M2 |
| M4 | [#764](https://github.com/rbctmz/ai_trainer/issues/764) | Preview, capability-aware serializer/readback, отдельная live-приёмка FR255 | M1/M3 |
| M5 | [#765](https://github.com/rbctmz/ai_trainer/issues/765) | Точные метры и active/rest, CSS handoff, разбор исходных серий | M1/M3 |

Это три продуктовых этапа: ввод (M1/M2), календарь/часы (M3/M4), учёт (M5).
M1 — backend/API foundation: пользовательского web-импорта до M2 ещё нет.
Каждый PR имеет bounded independent review, current CI и human merge decision.

## Инварианты и приёмка истории

Контрольные анонимные документы дают 2200/2000/1900м, всего6100м. Исходные серии,
вложенность, оборудование, инструкции и смысл отдыха переживают roundtrip. Ни
бюджет TSS, ни Recovery/Replan не переписывают оригинал. Duration/TSS без исходных
данных — unknown. 25м в факте остаются25м. Изменение pool25→pool50/OW требует
проверки совместимости и предложения, а не молчаливого изменения серии.

Живой rollout/запись на часы, личная БД и исторический пересчёт требуют отдельного
конкретного preview и решения владельца. Контрактная приёмка на stubs не равна
живому принятию. Сроки заранее не оцениваются до соответствующего среза.

## Границы существующих задач

#668 — допустимые дисциплины по дням; #670 — защищённые пороговые тесты;
#735 — per-sport LTHR; #702 — provider conflict preflight. Переиспользовать, не
дублировать и не включать их полностью в M1. Personal API runtime #736 отдельно.

## Текущее состояние

M1 завершён: #766 merged5042102. M2A завершён: #768 merged d2e1cf3 после
принятия review владельцем17.11.2026. M2B #769 / #770 merged ee8279b после
owner acceptance и clean review. M2C #771 / #773 merged8ba8e49 после
явного принятия review владельцем, зелёного CI и scoped native round2.
Сейчас [#772](https://github.com/rbctmz/ai_trainer/issues/772): web-сценарий.
В draft PR774 проверены source/reload, whole-program Coach→уточнение→preview→save,
ручные/точечные правки и каталог с exact-version bindings.19браузерных сценариев
прошли, последовательная очистка проверена. В полном локальном Python-наборе
4709успешных и4ранее наблюдавшихся DSH timeout; CI/review, решение владельца и
live-provider evidence проверяются отдельно. M2 ещё не объявлен завершённым.
M3–M5 — backlog. Проверка Intervals→FR255:
[feasibility](swim_intervals_garmin_feasibility.md), exact/live acceptance ещё нет.
Полный план: [swimming_trainer_program_execplan.md](swimming_trainer_program_execplan.md).
Активный M2: [swim_coach_import_execplan.md](swim_coach_import_execplan.md).
M1 contract: [swim_program_library_slice_spec.md](swim_program_library_slice_spec.md).

17.11.2026: владелец одобрил переиспользование упражнений. M2A отделяет технику
от назначения метров/отдыха; исправление справочника не меняет старую программу.
Контракт: [swim_exercise_library_slice_spec.md](swim_exercise_library_slice_spec.md).
