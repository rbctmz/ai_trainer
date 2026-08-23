# DeepSeek Responses API adapter — ExecPlan (#441, Class A pilot)

This ExecPlan is a living document. Sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` are maintained as work proceeds, per `.agent/PLANS.md`. Working slice spec: `docs/deepseek_responses_slice_spec.md` (kept separate per the slice-spec template rule).

## Purpose / Big Picture

Сегодня `DeepSeekProvider` ходит через OpenAI-совместимый `chat.completions`. DeepSeek завёз Responses API (формат Codex): он работает, но формат ответа структурно другой (spike #441, вердикт PARTIAL): текст в `output[type=message].content[0].text`, вызовы инструментов — `output[type=function_call]` с `call_id` и уже распарсенными `arguments` (dict, не JSON-строка), reasoning — отдельный item, `output_text` может быть None на финальном шаге. Слепая подмена `base_url` ломает парсинг — нужен отдельный адаптер.

После этого изменения пользователь может включить `DEFAULT_AI_PROVIDER=deepseek_responses` (или выбрать «DeepSeek (Responses API)» в настройках коуча) и получить тот же нативный цикл инструментов (`generate_with_tools` → `{text, tool_calls}`) поверх Responses API — включая явный reasoning DeepSeek — без изменения рантайма коуча.

How to see it working: `python -m pytest tests/smoke/test_deepseek_responses_provider.py -q` (адаптер на стабе клиента, без сети); живой прогон — только вручную, по желанию (paid-вызов), не в CI.

## Progress

- [x] (2026-08-23) Spike #441: вердикт PARTIAL, формат зафиксирован таблицей отличий; решение «отдельный адаптер, не подмена base_url».
- [x] (2026-08-23) M0: ExecPlan + slice-spec созданы; класс A подтверждён триггерами live-provider write + новый public contract.
- [x] (2026-08-23) M1 RED: 14/15 новых сценариев падали до реализации (ImportError/AttributeError).
- [x] (2026-08-23) M2 GREEN: парсер + mixin + провайдер + реестр + пикер; focused 15/15, регрессия #190 без правок.
- [ ] (pending) M3: verification bundle (готов: ruff green, smoke 2003 passed, contract-артефакт актуален) + PR + запись метрик Class A pilot.

## Surprises & Discoveries

- Observation: рантайм коуча (`models/ai_coach_runtime.py::resolve_turn_tool_results` / нативный цикл) передаёт провайдеру OpenAI-стиль истории: assistant-ходы с `tool_calls`, tool-ходы с `tool_call_id`/`name`/`content`. Responses API требует другие input-элементы: `function_call` (с `call_id`) и `function_call_output`. Значит адаптер обязан переводить историю, а не только парсить ответ.
  Evidence: `models/ai_coach_runtime.py:398-433`, `models/ai_providers.py::OpenAICompatibleToolsMixin.generate_with_tools`.
- Observation: контракт возврата `{text, tool_calls:[{id,name,arguments(dict)}]}` закреплён тестами #190 (`tests/smoke/test_coach_native_tools.py`) и менять его нельзя — адаптер должен нормализовать `call_id` → `id`, `arguments` оставить dict.
  Evidence: `test_coach_native_tools.py` (contract tests), `_native_tool_calls_from_openai_message`.

## Decision Log

- Decision: новый класс `DeepSeekResponsesProvider` + mixin `DeepSeekResponsesToolsMixin`; существующий `DeepSeekProvider` (chat.completions) НЕ трогаем и оставляем дефолтом для `provider_type='deepseek'`. Новый тип регистрируется как `'deepseek_responses'`.
  Rationale: spike прямо запретил «молчаливую подмену base_url»; аддитивность соответствует ASR-MOD-1 (новый провайдер без правки основного кода); chat-путь остаётся регрессионно защищённым существующими тестами.
  Date/Author: 2026-08-23, opencode.
- Decision: парсер работает по дискриминатору `type` и принимает и SDK-объекты, и dict-элементы (duck typing через `Mapping`/getattr) — это нужно и для живого SDK, и для стабов в тестах.
  Rationale: тесты обязаны гоняться без сети (contributor-safe); SDK-объекты неудобно строить вручную.
  Date/Author: 2026-08-23, opencode.
- Decision: system-промпт передаётся параметром `instructions` в `responses.create`, НЕ инлайнится в input. Tools-схемы мапятся в `{"type":"function","name","description","parameters"}` без обёртки `function` (формат Responses).
  Rationale: это канонический формат Responses API (spike #441).
  Date/Author: 2026-08-23, opencode.
- Decision: историю переводим так: user/assistant без вызовов → `{role, content}`; assistant с `tool_calls` → assistant-item + по одному `{"type":"function_call", call_id, name, arguments}` на вызов; tool-сообщение → `{"type":"function_call_output", call_id, output}`.
  Rationale: минимальная проекция OpenAI-истории рантайма на Responses input; lossless для цикла инструментов.
  Date/Author: 2026-08-23, opencode.
- Decision: ошибки/недоступность возвращают ту же форму `{"text": "Ошибка/не настроен ...", "tool_calls": []}`, что и остальные провайдеры; пустой список вызовов включает существующий grounding-fallback (#189) без изменений.
  Rationale: контракт рантайма и ASR-REL-2 (data gap вместо выдумывания).
  Date/Author: 2026-08-23, opencode.

## Outcomes & Retrospective

(заполняется по завершении)

## Context and Orientation

Ключевые файлы (пути от корня репо):

- `models/ai_providers.py` — `AIProvider` ABC (базовые методы), `OpenAICompatibleToolsMixin` (chat.completions + `_native_tool_calls_from_openai_message`), `DeepSeekProvider` (~439, client = `OpenAI(api_key, base_url)` с `DEEPSEEK_BASE_URL`), `AIProviderFactory.create_provider` (~763, реестр 'openai'/'anthropic'/'deepseek'/'google'/'ollama'), `get_available_providers` (~801).
- `config/settings.py` — `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL` (default deepseek-v4-flash), `DEEPSEEK_BASE_URL` (default https://api.deepseek.com). Переиспользуются без новых переменных.
- `models/ai_coach_runtime.py` — нативный цикл инструментов (~380): история в OpenAI-стиле, вызов `provider.generate_with_tools(messages, schemas, system_prompt=...)`, ожидание `{text, tool_calls}`.
- `ui/components/ai_coach_provider.py` — `REAL_PROVIDER_TYPES`, `PROVIDER_CLASS_NAMES`, `_build_provider_options` (опции пикера).
- `tests/smoke/test_coach_native_tools.py` — контракт capability-матрицы и формы возврата (регрессия не должна пострадать).
- Новые: `tests/smoke/test_deepseek_responses_provider.py`.

Terminology: «адаптер» — код, который переводит (1) OpenAI-стиль истории рантайма в input-элементы Responses и (2) `output`-элементы Responses в нормализованный `{text, tool_calls}`. «Парсер» — функция, разбирающая `output`-список по дискриминатору `type`.

## Plan of Work

M1 (RED), M2 (GREEN), M3 (verification) — срезы ниже в Delivery Slices слайс-спеки. Команды из корня, venv активирован.

## Concrete Steps

- RED: `python -m pytest tests/smoke/test_deepseek_responses_provider.py -q` — ожидаем падения (класс ещё не существует).
- GREEN: там же зелёный; затем `python -m ruff check models/ai_providers.py tests/smoke/test_deepseek_responses_provider.py ui/components/ai_coach_provider.py`.
- Broad: `python -m pytest tests/smoke -q` (не затронут ли старые контракты #190).
- Contract: изменения только в provider-слое и legacy-пикере; api/web контракт и `ts_contract.json` не трогаются — проверить `git diff --stat` и `npm --prefix web run contract:extract -- --check` (должно остаться зелёным без регенерации).
- Live probe (по желанию, вне CI): `DEEPSEEK_API_KEY` из .env, один вызов `max_tokens` минимумом на `deepseek_responses`, проверить `{text, tool_calls}` на реальном ответе. Paid-вызов — только с явного согласия пользователя.

## Validation and Acceptance

BDD-сценарии и RED-матрица — в `docs/deepseek_responses_slice_spec.md`. Приёмка: слайс-спека DoD закрыт, RED→GREEN пройден, focused+broad smoke зелёные, ruff green, существующий `test_coach_native_tools.py` без изменений проходит, PR связан с #441.

## Idempotence and Recovery

- Адаптер stateless: нет persistent state, курсоров или миграций. Повторный вызов идемпотентен.
- Откат: удаление строки `'deepseek_responses'` из реестра возвращает ровно прежнее поведение; `DeepSeekProvider` не изменяется.
- Частичный сбой: исключение SDK → `{"text": "Ошибка ...", "tool_calls": []}`; рантайм уходит в grounding-fallback (#189), а не падает.

## Artifacts and Notes

- Spike: `spikes/002-deepseek-responses-api/README.md` (переносится из локального прогона отдельно, если потребуется).
- Метрики процесса: запись prospective Class A в `docs/engineering_process_metrics.md` после merge.

## Interfaces and Dependencies

- `models.ai_providers.DeepSeekResponsesProvider(DeepSeekResponsesToolsMixin, AIProvider)` — конструктор как у `DeepSeekProvider` (api_key/model/base_url/settings).
- `models.ai_providers.responses_output_to_result(output_items) -> Dict` — парсер.
- `models.ai_providers._messages_to_responses_input(messages) -> List[Dict]` — перевод истории.
- Реестр: `AIProviderFactory.create_provider('deepseek_responses')`; `get_available_providers` добавляет `'DeepSeek (Responses API)'`; пикер: `REAL_PROVIDER_TYPES`, `PROVIDER_CLASS_NAMES`, `_build_provider_options` дополнены.
- Зависимости: только существующий `openai` SDK (уже в требованиях); новых библиотек нет.

---

Изменение документа от 2026-08-23 (opencode): первая ревизия — собрана из spike #441 и чтения рантайма/провайдеров. Решение об аддитивном провайдере вместо флага зафиксировано в Decision Log.
