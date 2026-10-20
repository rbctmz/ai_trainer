# Planning S3 M1: готовность плана к публикации

Parent: [#677](https://github.com/rbctmz/ai_trainer/issues/677). Дата: 2026-10-20.
Автор: Spec / Architecture Owner. Merge owner: человек. Независимый checker —
отдельная read-only проверка M1; результат записывается в evidence report.
Baseline: `5f3b738a8b890d1d69ce7793f684277fb00b40dd`.
[ExecPlan](planning_build_readiness_execplan.md).
[Class A audit/review record](planning_build_readiness_m1_review_record.md).

## Change Class и граница M1

Class A: будущий контракт меняет допуск к публикации замороженного плана,
проверку перед транзакционной записью и совместимость pending previews.
M1 поставляет только спецификацию, синтетические эксперименты и acceptance
RED. Он не меняет runtime, HTTP/TS-модели, формулы, каталог или интерфейс.
Review mode: manual; specification budget 1/2: независимый round 1 READY на
`b279178`, zero open blocking P1/P2; см. evidence report.
Native PR review и human acceptance учитываются отдельно, не подразумеваются.

## Короткое правило

План можно опубликовать как текущий только если каждое назначенное занятие
имеет проверенное задание, а его время, цели интенсивности и нагрузка согласованы
с итогами плана. Числа недель и успешная сериализация этого не доказывают.
`ready` означает техническую готовность предписаний; это не медицинский допуск,
не доказательство развития формы и не гарантия переносимости нагрузки.

## Модель состояния

| Состояние assessment | Значение | Новый preview / confirm |
| --- | --- | --- |
| `ready` | Все обязательные проверки завершены, blockers пуст | 200 pending; confirm после обычных freshness/CAS проверок |
| `blocked` | Есть воспроизводимое нарушение или отсутствует обязательное задание/семантика | Prepare 422 `plan_not_ready`, без usable token; pending confirm 409 `plan_not_ready` |
| `unassessed` | У исторического плана либо старого pending нет проверяемого assessment текущей версии | История читается; старый pending 409 `preview_required`; новый build обязан пройти assessment |

Нельзя заменить blocked на ready пользовательской галочкой или origin=coach.
Applied receipt — историческое подтверждение, а не новый publish: его повтор
возвращается как прежде, без переоценки и повторной активации, даже для старого
плана. Историю нельзя задним числом переименовать в проверенную или переписать.

## Обязательные проверки

**AC1 — полное задание.** В окончательном candidate после календарных границ,
ограничений и identity stamping проверяется каждый назначенный exercise parent
в изменяемой будущей части: date >= max(athlete_day, cycle.start_date), до конца
цикла включительно. В edit_current сохранённые прошлые назначения не являются
новыми заданиями. Single требует materialized status, непустых materialized_steps
и определённых целей для каждого этапа. Composite требует готовности всех legs;
проверка только parent недостаточна. Явные rest days без exercise session допустимы
с нулевой нагрузкой; нулевой TSS у exercise не превращает его в отдых. Прогнозные
race_forecast_loads не являются экспортируемым заданием и не считаются дважды.
Missing, legacy_role_fallback, infeasible, unknown status, непустой failed_bounds
либо противоречие этих признаков дают blocker с адресом занятия.

**AC2 — согласованная нагрузка.** Сравниваются total_tss, parameter_snapshot,
planned_tss_evidence (если метод определён), шаги/legs, день, discipline buckets,
weekly_tss_plan, weekly_summary, response totals и вход прогноза. Для bike
power-prescription применим текущий именованный метод расчёта по ступеням;
различие с requested_tss само по себе допустимо, если все производные используют
один effective_tss. Нельзя подменять ожидаемый эффект точным фактическим TSS.
Для run/swim оценка может оставаться оценкой с явным методом/провенансом, без
притворного пересчёта всех дисциплин велосипедной формулой. Точный перечень полей
и нормализацию конечных агрегатов фиксирует M3 до GREEN AC2.
На каждом уровне суммируются исходные значения один раз; отображаемое округление
не становится входом следующего расчёта. Сравнение использует квант поля: 0.1 TSS
для leaf, целое для существующего weekly display. Проверяется round(sum(raw)),
а не sum(round(children)); допуск нельзя умножать на число дочерних записей.
Законное округление discipline columns отдельно не является ошибкой.

**AC3 — согласованное время.** Step seconds равны длительности single, длительность
composite равна legs плюс явно записанный transition_minutes. Переход учитывается
один раз. Проверяются утверждённые weekly/day availability ограничения, не
произвольная плотность ради заполнения доступных часов. Рост длительности при
подборе шаблона требует нового preview, а не скрытой замены во время confirm.

**AC4 — понятные цели.** Числа конечны, единицы, диапазоны и threshold provenance
соответствуют типу цели; low <= high либо fast <= slow в seconds-per-distance.
Fallback RPE допустим при наличии явной versioned catalog policy по шаблону и
этапу на шкале 1–10. Простое fraction_of_threshold * 10 не считается такой
политикой. До определения этой политики target получает blocker
`target_semantics_unverified`; числовую «правильную» замену M1 не придумывает.
Recovery/easy обещание и заданное усилие проверяются по этой политике, а не только
по имени фазы. Отсутствие CSS не запрещает RPE как метод само по себе.

**AC5 — серверная граница.** Ассessor — чистая функция Python над final candidate,
его public response и замороженным input context. Она не обращается к provider,
LLM, рабочей БД или часам. Готовность проверяется после всех преобразований, а не
у промежуточного черновика. Подготовка blocked не создаёт pending row и не меняет
цикл, checkpoint, profile, demand, facts, delivery/feedback/matching ledgers.
Общий prepare/confirm guard обслуживает Planning UI и Coach build. Другие типы
мутаций — отдельный handoff, не объявляются защищёнными этим срезом.

**AC6 — confirm и совместимость.** Frozen assessment связывается с точным candidate
fingerprint и версией правил, включённой в dependency digest. Client flag ready
не принимается. Под writer lock до первой активной записи проверяются версия,
целостность и согласованность assessment с frozen artifact; допускается только
чистая bounded валидация, не пересборка плана/Banister и не provider I/O.
Старый pending без assessment требует нового preview. Ложный ready, неверный hash
или malformed assessment дают 500 preview_corrupt; честный blocked — 409
plan_not_ready. Все отказы сохраняют активное состояние байт-в-байт. Прежние
stale/closed/scope/CAS/replay/expiry guards остаются обязательными. Replay applied
проверяет сохранённый receipt прежней схемы раньше проверки допуска нового publish.
При обновлении policy старый applied receipt остаётся читаемым.

**AC7 — честная научная граница.** Отдельное поле `training_suitability` имеет
`not_assessed` в этом срезе. Недавняя sport-specific частота, длительность,
перерывы, переносимость и полнота истории — вход будущего M4, а не основание
сейчас изобрести обязательные 10%, 3+1, ACWR safe zone или норму 420/600 TSS.
Отсутствие совпадений plan/fact у будущего цикла не является blocker готовности
заданий. Science audit и TSB badge не заменяют assessment и не разрешают blocked.

## Предлагаемый public contract для следующей реализации

Новые успешные build/confirm ответы и соответствующий goal_plan_snapshot получают
`build_readiness`: policy_version=`plan-build-readiness-v1`, status=`ready`,
can_confirm=true, scope={start_date,end_date}, assessed_session_count,
candidate_fingerprint, blockers=[], warnings=[], training_suitability=`not_assessed`.
Fingerprint исключает само assessment, receipt и назначаемый checkpoint ID, но
покрывает назначения и связанные агрегаты/forecast inputs. Время/версия входов
приходят из snapshot, новый источник часов не вводится.
Каждая причина: code, date, session_id, nullable leg_index, field, expected,
observed; для aggregate используется nullable session_id и конкретный field path.
Числа expected/observed допустимы в локальном ответе, не в публичных логах.
Стабильные blocker codes: prescription_missing, prescription_infeasible,
target_semantics_unverified, load_inconsistent, duration_inconsistent,
availability_exceeded. Порядок причин детерминирован; нет усечения подсчёта.

Prepare rejection расширяет существующий error envelope полем `build_readiness`
со status=blocked, can_confirm=false и причинами; preview_id/confirmation/token
отсутствуют. Confirm request остаётся {preview_id,confirm:true}; никаких force,
ignore_warnings, исправленных client-side totals. Текущий web сможет показать
safe detail ошибки; полноценный просмотр причины/занятия принадлежит S4 и не
пишется в M1. API/TS модели и registry/extractor обновляются вместе при реализации.
Existing applied v1/v2 receipts сохраняют исходную форму. Historical reads без
assessment явно трактуются как unassessed без GET-записей; schema migration,
backfill и новая таблица не нужны. Snapshot/preview/receipt используют существующую
retention/reset/backup ownership; добавочное поле не создаёт второй журнал.

## Non-goals и следующие владельцы

M1 не чинит каталог, не добавляет Recovery во все интенсивные шаблоны, не ослабляет
границы и не удлиняет спринты ради TSS. Не меняет научные диапазоны RPE, формулы
периодизации, возврат после перерыва, пользовательские power zones (#703), ограничения
дисциплин по дням (#668), послегоночный recovery (#680), клинические ограничения
(#679) или Recovery Mode (#669). Не редактирует CSS/interaction и не отправляет
тренировки провайдеру. Не сертифицирует медицинскую безопасность готового задания.
Domain/API получает M2 catalog/semantics и M3 consistency/guard; Spec получает M4
обоснование входной нагрузки. UI/Design получает S4 только по готовому DTO.
Включать publish guard в поставляемый runtime следует вместе с покрытием
допустимых планов: один запрет без исправленной генерации заблокирует типовые циклы.

## RED matrix и Definition of Done M1

| Проверка | Исполняемая evidence M1 | Ожидаемый результат будущей реализации |
| --- | --- | --- |
| Полный новый / замещающий цикл | 2 HTTP RED: success обязан содержать только готовые назначения либо prepare явно blocked без записи | GREEN после M2/M3 |
| Защита publish независимо от UI | 2 HTTP RED invalid-publication: оба pending содержат 23 invalid prescriptions; assertion падает до ветки готового control/replay, которая остаётся M2/M3 | GREEN после M3 |
| Recovery vs Base | Pure probe: одинаковые easy параметры в трёх дисциплинах | Recovery получает подходящий recovery prescription либо явный blocker |
| Спринты | Pure probe requested 25 vs derived 16.3, failed bounds | Отказ понятен; неверное задание не публикуется |
| RPE fallback | Pure probe easy swim содержит RPE 6–8 без semantic policy | Явная корректная policy либо target_semantics_unverified |
| Composite transition | Pure probe parent = legs + transition | Не ложный duration blocker |
| Округление / future facts | Только spec в M1; исполняемые проверки остаются M3 | Не ложные blockers |

M1 завершён после независимой проверки спецификации, сохранения фактических
результатов и публикации reviewable checkpoint. XFAIL/characterization не являются
runtime GREEN. M2/M3 обязаны дополнить behavioral suite: bad composite leg,
missing transition, finite/unit/range errors, last-day inclusivity, unchanged past
legacy, zero/rest, legitimate rounding, every aggregate mismatch, stale/new-policy
pending, applied old replay, both origins, all-table rollback/reset, valid plan и
16-week bounded check. Отсутствие этих тестов в M1 явно остаётся work remaining,
а не скрывается заявлением о полном покрытии.

## ASR / ADR и review

ASR-REL-1/2: не публиковать неподтверждённую структуру, не терять историю;
ASR-MOD-2/3: Python-owned assessment, additive payload и совместимость receipt;
ASR-PERF-4: bounded validation; ASR-DEP-2: прежний reset/backup ownership.
Переиспользуется ADR-0001; новый UI-owned policy или отдельное хранилище не вводится.
Независимая проверка: exact candidate diff, allowed focused tests, без личной БД,
.env, provider calls и изменения кода. Findings фиксируются как fixed-in /
follow-up / disputed. Нативный review не запрашивается автоматически; merge и
переход к runtime остаются решениями владельца в рамках выданного scope.
