# ADR-0010: Граница автономии коуча и DDA для мутаций

- Status: Accepted
- Date: 2026-08-20
- Related: ADR-0004, ADR-0006, ASR-REL-1, ASR-REL-3, ASR-MOD-2,
  ASR-MOD-3, issue #466, follow-up #483

## Context

ADR-0004 ввёл для мутаций плана контракт `Propose → Confirm → Append +
rollback`, но не дал общего способа классифицировать новые действия коуча.
Из-за этого prompt может называть фразу пользователя «явной», хотя runtime не
умеет отличить прямое намерение пользователя от интерпретации LLM.

Нужна воспроизводимая граница автономии по трём осям из Protocol 13:
**Reversibility**, **Blast radius**, **Agency creep**. Для мутаций дополнительно
нужно правило DDA (Direct, Deliberate Action): что именно считается явным
действием пользователя, а что остаётся только согласием с рассуждением.

## Decision

Каждое новое действие коуча оценивается независимо по трём осям. Итоговый gate
задаёт самая рискованная ось; высокая обратимость не компенсирует широкий blast
radius или рост agency.

| Ось | Низкий риск | Повышение gate |
|-----|-------------|----------------|
| Reversibility | чтение, preview, обратимая append-only заметка/evidence node с audit trail | перезапись, удаление без точного восстановления, внешний побочный эффект |
| Blast radius | одна локальная заметка/node, не влияющая на исполнимый план | одна дисциплина → день → горизонт/весь план → профиль или external write |
| Agency creep | вычислить/объяснить → подготовить preview | выбрать за пользователя → изменить исполнимый план → записать во внешний provider |

### Уровни действий

| Уровень | Примеры | Разрешение |
|---------|---------|------------|
| A0 — observe | чтение данных, расчёт readiness, объяснение, in-memory preview | autonomous |
| A1 — reversible local append | обратимая заметка или non-executable evidence node, явно помеченные как AI-generated и не меняющие план, профиль или provider | autonomous; append-only audit и доступный retract обязательны |
| A2 — local executable mutation | constraint, перенос/удаление сессии, repair дня, изменение горизонта плана | proposal с точным scope/base, затем DDA-confirm; append-only checkpoint и rollback по ADR-0004/0006 |
| A3 — sensitive local mutation | необратимое удаление, изменение FTP/порогов или других параметров, влияющих на множество назначений | отдельный preview и явное подтверждение; fail-closed при stale/ошибке |
| A4 — external effect | external write в Intervals.icu/Garmin или другой provider | отдельное явное действие на delivery surface, точный scope, read-back/audit; LLM tool call не авторизует отправку |

Узкая A1-автономия не отменяет ADR-0004: заметка/node не может менять
исполняемый план. Например, фразу «я болею завтра» можно учесть в ответе и
сохранить как обратимый пользовательский факт, но применение constraint к
плану относится к A2 и требует proposal/confirm.

### Правило DDA

DDA — детерминированно проверяемое действие пользователя на bounded action
surface. Для текстового подтверждения нужны:

1. явный глагол действия, например «примени» или «подтверди»;
2. однозначная ссылка на текущий preview или точный объект и scope;
3. неизменный `base_checkpoint_id`/fingerprint между preview и apply.

Нажатие отдельной кнопки подтверждения для конкретного preview также является
DDA. Вызов инструмента, выбранный LLM, DDA **не является**: это интерпретация
модели, а не пользовательская авторизация.

Фразы «согласен», «ок», «звучит неплохо» и аналогичное неопределённое согласие
не авторизуют мутацию. Сообщение факта («я болею завтра») меняет safety-контекст
ответа, но без отдельного DDA не применяет изменение плана. Императив вроде
«удали тренировку в пятницу» задаёт объект для preview; из-за уровня A2/A3 он
не обходит preview и bounded confirmation.

### Runtime invariants

- DDA и gate проверяются кодом, а не только system prompt.
- До confirm A2–A4 дают zero durable writes, кроме самого pending proposal и
  его audit metadata.
- Stale base, validation error, missing donor и provider failure оставляют
  constraint/profile/checkpoint/provider в исходном состоянии.
- Повторный confirm идемпотентен.
- Повышение по любой из трёх осей повышает gate; оно не может быть скрыто под
  названием «repair», «sync» или «служебная операция».

## Audit result for #466

`propose_plan_build` и `propose_plan_adjustment` возвращают preview с
`is_proposal`; `api/routers/coach.py` сохраняет такой результат как pending
proposal. Но `create_plan_constraint`, `retract_plan_constraint` и
`repair_plan_day` в `models/ai_tools.py` выполняют durable mutation сразу и не
возвращают `is_proposal`. Native и marker runtimes исполняют выбранный моделью
tool до обработки результата роутером. Следовательно, prompt-only требование
«явной фразы» не обеспечивает DDA.

Дополнительно retract-пути деактивируют constraint до попытки восстановить
день. Ошибка stale/missing donor может оставить частичную мутацию. Трассировка
Coach call paths и evidence-классификация mutation routes из
`api/routers/planning.py` зафиксированы в
`docs/coach_autonomy_boundary_execplan.md`. Исправление вынесено в отдельный
issue #483, чтобы #466 оставался архитектурным решением и аудитом.

## Consequences

- Новые инструменты получают единый review-чеклист вместо эвристики «кажется
  обратимым».
- Безопасные note/node действия сохраняют узкую полезную автономию.
- Любая мутация исполнимого плана остаётся в proposal/confirm контуре.
- FTP, удаление и external write явно попадают под усиленный gate.
- Подтверждённый runtime gap не скрывается изменением ADR задним числом; его
  закрывает отдельный RED→GREEN трек #483.
