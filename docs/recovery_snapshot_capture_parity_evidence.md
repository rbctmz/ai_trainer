# Evidence bundle — паритет post-sync capture readiness-снимка для Garmin и Intervals (#562)

Итоговый пакет доказательств по issue
[#562](https://github.com/rbctmz/ai_trainer/issues/562) (Change Class **A**).
Живой план — [`recovery_snapshot_capture_parity_execplan.md`](recovery_snapshot_capture_parity_execplan.md),
спека слайса — [`recovery_snapshot_capture_parity_slice_spec.md`](recovery_snapshot_capture_parity_slice_spec.md),
ASR-контур — [`architecture/asr_catalog.md`](architecture/asr_catalog.md#post-sync-recovery-snapshot-capture-parity-562).

Документ намеренно **разделяет** проверенное и непроверенное: ниже отдельно идут
локальные прогоны, браузерная приёмка через перехват маршрутов, отсутствие
live-provider E2E, эфемерность терминального readback, граница публичной
проекции и подтверждённые non-goals. Ни одна секция не заявляет больше, чем было
исполнено.

## 1. Идентичность изменения

| Параметр | Значение |
|----------|----------|
| Issue | #562 «надёжный предтренировочный readiness-снимок для Garmin и Intervals» |
| Class | A — Full (SpecDD → BDD → TDD → Contract First → Self-Review) |
| Base | `facc2b4` — merge плана (PR #571), `main` на момент старта реализации |
| Ветка | `codex/issue-562-recovery-capture-parity` (отдельный review budget, решение D8) |
| Head финального прогона | `294aeda` |
| Diff | 33 файла, +4069 / −60 (`facc2b4..294aeda`); из них код и контракт — 9 файлов (+938 / −37), тесты — 19 файлов (+2889 / −4), остальное — docs, фикстуры и ассеты |
| Схема БД | не менялась (никаких DDL и миграций) |
| Milestone SHA | M1 `3992c5c` · M2 RED `22fda6b` / GREEN `e18b279` · safety RED `6dbe415` / GREEN `edfcfca` · F1–F3 `45976af` · M3 `20e8594` · M4 `ead8f05` · M5 `e66266c` · M6a `d8226be` + фикстуры `faff6aa` + docs `9919be5` · M6b `cbf86cd` · M6a-коррекция `a9f6790` · M6b re-acceptance `661dee6` · M6b-cleanup `294aeda` |

Правки M6c (этот документ, `docs/architecture/asr_catalog.md`, запись в плане) не
меняют продуктовый код и тесты. Полный набор прогнан на `294aeda`; после
документационных правок дополнительно перепрогнаны док-пины, focused-контур,
Ruff и contract-гейты — результаты в §2 и §3 отмечены как «после docs-правок».

## 2. Проверено локально (verified locally)

| Проверка | Команда | Результат на `294aeda` |
|----------|---------|------------------------|
| Contributor-safe набор | `python -m pytest -m "not live and not debug and not e2e" tests/ -q` | **2598 passed, 15 skipped, 36 deselected**, 65.49 s, 3 warnings (пропуски — отсутствие `garth` и HRV-данных в локальной базе) |
| Focused M1–M6 (#562) | `python -m pytest tests/smoke/test_recovery_capture_contract.py tests/smoke/test_garmin_sync_service.py tests/smoke/test_recovery_capture_intervals.py tests/smoke/test_recovery_capture_api_contract.py tests/smoke/test_issue_562_acceptance.py tests/smoke/test_m3_sync_ui_contract.py tests/smoke/test_m3_sync_provider_api.py tests/smoke/test_sync_job_api.py -q` | **132 passed, 10 skipped** (skip — явная регенерация фикстур под `CAPTURE_FIXTURE_REGEN=1`) |
| Линтер Python | `python -m ruff check .` | **All checks passed!** |
| Web lint | `npm --prefix web run lint` | exit 0, «No ESLint warnings or errors» |
| Web build | `npm --prefix web run build` | exit 0, `✓ Compiled successfully` (16/16 статических страниц) |
| Свежесть api↔web контракта | `npm --prefix web run contract:extract -- --check` | «артефакт актуален (`tests/contracts/ts_contract.json`)» |
| Инвентарь вызовов API | `npm --prefix web run contract:inventory` | 40 просканированных файлов, 64 записи, **0 с `unresolved`** |

Что именно доказывает focused-контур: пять состояний вердикта и приоритет
предикатов, паритет обоих провайдеров, идемпотентность `capture_run_id` и
монотонность ревизий, fail-open при отказе capture, согласованность статуса с
дневным anchor, отсутствие служебных полей в публичном ответе, читаемость
истории без мутации, а также приёмку M6a по десяти запиненным JSON-фикстурам
терминального API.

После docs-правок перепрогнаны: `python -m pytest tests/smoke -q` (док-пины,
включая `test_architecture_docs.py`) — **2555 passed, 10 skipped**; focused-контур
#562 — **132 passed, 10 skipped**; `python -m ruff check .` — **All checks
passed!**; `npm --prefix web run contract:extract -- --check` — артефакт актуален.
Изменения затронули только Markdown и ассеты, поэтому полный contributor-safe и
E2E-контур заново не перезапускались: их результат выше относится к тому же
продуктовому коду (`294aeda`).

## 3. Browser contract/UX acceptance через route interception

Это **не** provider E2E: сценарий перехватывает три маршрута и проверяет, что
пользователь видит честный readback. Продуктовые переключатели и инъекции
провайдеров для этого не добавлялись (решение D5).

| Проверка | Команда | Результат на `294aeda` |
|----------|---------|------------------------|
| Браузерный модуль #562 | `python -m pytest -m e2e tests/e2e/test_recovery_capture_readback.py -q` | **10 passed** (5 состояний × 2 провайдера), ~30 s |
| Полный E2E | `python -m pytest -m e2e tests/e2e -q` | **12 passed**, 36.85 s |

Перехват и что он утверждает:

- `/api/sync/providers` — выбранный провайдер `configured: true`, кнопка синка
  активна (иначе проверялся бы мёртвый контрол);
- `POST /api/sync` — `running`, ровно один вызов;
- `GET /api/sync` — первый ответ `running`, далее терминальная фикстура M6a,
  поэтому реально пройден polling-путь (`GET ≥ 2`), а не завершение после POST.

Утверждается видимый текст строки синхронизации: человеко-читаемый статус,
локальное время атлета `23.07 08:00` или честное «время не определено»,
безопасная причина для проблемных состояний, терминальный `partial` и
единственное объяснение сбоя при `capture_failed`, а также отсутствие
идентификаторов (`capture_run_id`, `job_id`, `snapshot_id`), машинных кодов
состояний и причин, сырого `error`, путей вида `athlete.db` и новых
console/pageerror.

Evidence прогона (артефакты каталога, в git не коммитятся — `logs/` вне
репозитория, кроме двух репрезентативных снимков):

- каталог финального прогона `logs/e2e-recovery-capture/20260912T220250Z/` —
  10 `.txt` с точным видимым текстом и 10 `.png`;
- `docs/assets/issue_562_capture_readback_garmin.png` — счастливый путь с
  локальным временем;
- `docs/assets/issue_562_capture_readback_intervals.png` — терминальный `partial`
  при отказе capture: единственное объяснение сбоя в readback-блоке, посторонний
  notice сохранён (он инъектируется перехватом в тесте; файлы фикстур не меняются).

Снимки сделаны из того же прогона, что и таблица выше. Повторные прогоны
воспроизводимы: Garmin-снимок совпал с предыдущим **побитово**, Intervals
отличается только 37 пикселями внутри области 317×27 в верхней части кадра
(y 39–66) при идентичном тексте строки синхронизации (проверено попиксельным
сравнением, Pillow); источник этой разницы не изолирован — вероятнее всего
зависящий от настенных часов элемент вне строки синхронизации, но это
предположение, а не проверенный факт.

## 4. Не проверено: live-provider E2E

**Не проверено.** Ни один прогон в этом пакете не обращался к Garmin Connect или
Intervals.icu: клиенты провайдеров подменяются в тестах, живой сети и кредов нет
(`GARMIN_EMAIL`, `GARMIN_PASSWORD`, `INTERVALS_ICU_API_KEY` в e2e-стенде явно
пусты). Значит, пакет **не** подтверждает:

- поведение настоящего Garmin Connect / Intervals.icu на реальном окне данных;
- сквозную работу против production-БД с историей и реальной таймзоной атлета;
- поведение при сетевых обрывах и ретраях на стороне провайдера.

Сервисный и API-контур доказан локальными тестами с инъекцией клиентов, а
UI-контур — синтетической браузерной приёмкой (§3). Заявление о live-паритете
здесь не делается и требует отдельного прогона с реальными кредами.

## 5. Эфемерность терминального readback

**Ограничение, не проверенное свойство устойчивости.** `SyncJobManager` —
process-local: новый процесс инициализируется idle-снимком, поэтому терминальный
результат (а вместе с ним и `recovery_capture`) **не переживает рестарт API**.
Дурабельна только сама запись снимка — её строка в журнале и провенанс;
`capture_failed` не пишет ни одной строки, поэтому восстановить этот исход из
базы нельзя.

Персистенция исходов capture (включая провалы) — вне объёма #562 и не
заявляется как покрытая. В UI это не маскируется: readback показывает вердикт
той синхронизации, которую пользователь только что запустил.

## 6. Граница публичной проекции

**Проверено.** Наружу уходит только очищенный блок: `project_recovery_capture`
проецирует строго по белому списку `RECOVERY_CAPTURE_PUBLIC_FIELDS`
(`provider`, `capture_run_id`, `status`, `reason`, `eligibility_status`,
`eligibility_reasons`, `local_date`, `observed_at_utc`, `observed_at_local`,
`cutoff_at_utc`, `snapshot_id`, `revision`, `created`, `error`), а `job_id`
штампуется отдельно на границе `SyncJobManager`. Оба provider-builder'а
проецируют блок именно так.

**Внутренний `episode_refresh["error"]` (сырой `str(exc)`) в публичную проекцию
не входит.** Это не соглашение, а конструкция: возврат обёртки наружу не
проецируется никогда, поэтому утечка текста исключения или локального пути
невозможна по построению. Проверяется тестами приёмки (`EXPECTED_KEYS` для
обоих провайдеров и запрет служебных ключей) и API-контрактом: публичный блок
несёт только стабильные коды (`snapshot_capture_failed`,
`activity_lookup_failed`), а не текст исключения.

## 7. Подтверждённые non-goals

**Не реализовано и не проверялось, потому что вне объёма задачи:**

- **нет backfill** исторических снимков — capture работает только в
  prospective-режиме, прошлые дни не пересобираются;
- **нет polling-надстроек** — capture запускается синхронно в рамках
  существующего job'а синхронизации, отдельного расписания/cron не появилось;
- **нет автоматической коррекции плана** — производная запись только фиксирует
  состояние готовности; план, сессии и delivery-записи capture не мутирует;
- правило pre-anchor не ослаблялось, исторические `missing_pre_anchor` не
  переклассифицируются; provider writeback отсутствует.

## 8. Как воспроизвести

```bash
source ai_trainer_env/bin/activate
python -m ruff check .
python -m pytest -m "not live and not debug and not e2e" tests/ -q
python -m pytest tests/smoke/test_recovery_capture_contract.py \
  tests/smoke/test_garmin_sync_service.py \
  tests/smoke/test_recovery_capture_intervals.py \
  tests/smoke/test_recovery_capture_api_contract.py \
  tests/smoke/test_issue_562_acceptance.py \
  tests/smoke/test_m3_sync_ui_contract.py \
  tests/smoke/test_m3_sync_provider_api.py \
  tests/smoke/test_sync_job_api.py -q
npm --prefix web run lint && npm --prefix web run build
npm --prefix web run contract:extract -- --check
npm --prefix web run contract:inventory
python -m pytest -m e2e tests/e2e -q
```

Браузерная приёмка требует chromium (Playwright); каталог evidence можно задать
через `E2E_CAPTURE_EVIDENCE_DIR`, иначе он создаётся как
`logs/e2e-recovery-capture/<UTC-штамп>/`. Регенерация десяти JSON-фикстур —
только явно: `CAPTURE_FIXTURE_REGEN=1 python -m pytest tests/smoke/test_issue_562_acceptance.py -k regenerate`.

## 9. Что осталось за границей этого пакета

- Native-review раунд по PR реализации и ответы на находки — отдельный шаг после
  открытия PR (`Closes #562`).
- Live-provider проверка (§4) и персистенция исходов capture (§5) — не входят в
  #562; при необходимости оформляются отдельными issue.
- Рекомендация по серверному тексту предупреждения `⚠️ Recovery snapshot
  capture: <код>` закрыта решением владельца: warning остаётся сигналом D4, а
  дублирование снято в UI (см. `M6b-cleanup` в плане).
