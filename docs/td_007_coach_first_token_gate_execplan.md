# Закрыть TD-007: детерминированный first-token latency-гейт Коуча

Живой документ по `.agent/PLANS.md`; самодостаточен.

## Purpose / Big Picture

ASR-PERF-2: `done`-событие SSE отдаёт `first_token_ms`, но бюджет 5 секунд был
наблюдением, а не гейтом — внутренний overhead (контекст, инструменты, промпт)
мог деградировать без сигнала CI. После TD-007 бюджет становится именованной
константой и детерминированно проверяется на локальном runtime без сети.

## Progress

- [x] (2026-08-03) Найден офлайн-путь: `provider="mock"` + временная БД, без
      live API; существующий тест уже проверяет наличие `first_token_ms`.
- [x] (2026-08-03) RED: `test_coach_first_token_gate.py` — замер до первого
      token-события < `COACH_FIRST_TOKEN_BUDGET_MS` (константы нет → RED).
- [x] (2026-08-03) GREEN: константа `COACH_FIRST_TOKEN_BUDGET_MS = 5000` в
      `api/coach_service.py`; focused 10 passed, smoke 1446 passed, ruff чист.

## Surprises & Discoveries

- Observation: в репозитории уже есть локальный mock-провайдер
  (`provider="mock"`), поэтому гейт не требует новых моков — только замер.
  Evidence: `api/coach_service.py::resolve_provider` и
  `tests/smoke/test_api_phase1.py::test_coach_chat_done_event_reports_first_token_ms`.

## Decision Log

- Decision: бюджет — константа `COACH_FIRST_TOKEN_BUDGET_MS = 5000` в
  `api/coach_service.py`, импортируемая тестом.
  Rationale: порог становится контрактом, а не магическим числом в тесте.
  Date/Author: 2026-08-03 / Codex.
- Decision: гейт только на `provider="mock"` (без сети); live-провайдеры
  остаются наблюдаемой метрикой.
  Rationale: внешняя сеть недетерминирована; гейт ловит регрессии нашего
  внутреннего overhead, как и требует граница из реестра.
  Date/Author: 2026-08-03 / Codex.

## Outcomes & Retrospective

TD-007 закрыт: детерминированный first-token гейт на локальном mock-runtime.
`done.first_token_ms` по-прежнему наблюдается для live, но внутренний overhead
теперь гейтится CI.

## Context and Orientation

`api/routers/coach.py::coach_chat` возвращает `StreamingResponse`; первый
`token`-событие ставит `first_token_ms`. Тест гоняет этот поток с
`provider="mock"` на временной БД и замеряет время до первого token.

## Concrete Steps

    source ai_trainer_env/bin/activate
    python -m pytest tests/smoke/test_coach_first_token_gate.py tests/smoke/test_api_phase1.py -q
    python -m pytest tests/smoke -q
    git diff --check

## Validation and Acceptance

Гейт проходит на локальном mock-пути (elapsed < 5000 мс) и не обращается к
внешней сети. Live-метрика не меняется. Полный smoke зелёный; CI
ready-to-merge; после мержа TD-007 закрывается в реестре.

## Idempotence and Recovery

Тест идемпотентен (временная БД, мок-провайдер). Откат = убрать константу и
тест.
