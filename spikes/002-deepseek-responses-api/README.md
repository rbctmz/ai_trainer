# 002-deepseek-responses-api

## Вопрос

DeepSeek завёз OpenAI-совместимый **Responses API** (тот же, что использует Codex).
Сейчас `DeepSeekProvider` ходит через `chat.completions` (миксин
`OpenAICompatibleToolsMixin`). Вопрос: Responses API — drop-in замена или
требует отдельного адаптера? Работает ли в нём нативный function calling
полным циклом (запрос → tool_call → результат → финальный текст)?

## Риск

- Формат ответа иной → слепая подмена base_url ломает парсинг tool_calls.
- Multi-turn цикл коуча может не работать без явной сборки `input`-истории.
- `output_text` может быть `None`, а текст лежать глубже в `message.content`.

## Результат

| Проверка | Результат |
|----------|-----------|
| `POST /responses` с tools | ✅ 200, `function_call` в `output` |
| `arguments` | уже `dict` (не JSON-строка, как в chat.completions) |
| `call_id` | `call_00_...` (аналог `tool_calls[].id`) |
| Multi-turn (результат обратно) | ✅ работает, `status: completed` |
| Финальный текст | в `output[type=message].content[0].text`, НЕ `output_text` |
| `output_text` на финальном шаге | `None` |
| Отдельный `reasoning` item | есть (chain-of-thought как отдельный блок) |

Финальный message item:

```json
{
  "type": "message",
  "content": [{"type": "output_text", "text": "В Питере +18°C и солнечно ☀️"}],
  "phase": "final_answer",
  "role": "assistant"
}
```

## Вердикт: PARTIAL

### Что работает
- Responses API полностью функционален: tool calling + multi-turn + финальный ответ.
- Формат строже и чище: `arguments` сразу dict, есть `phase` и `status`.

### Что НЕ drop-in
- `output_text` ≠ `choices[0].message.content`. Текст — в `output[].content[]`.
- `tool_calls[].function.arguments` (JSON-строка) → `output[].arguments` (dict).
- `tool_calls[].id` → `output[].call_id`.
- Появился `reasoning` item, который текущий нормализатор не знает.

### Рекомендация
1. **Не подменять base_url молча** — Responses API требует отдельный адаптер
   (новый `ResponsesProviderMixin` или метод), не переиспользование
   `OpenAICompatibleToolsMixin` как есть.
2. Писать парсер `output[]` с дискриминатором `type`: `message` → текст,
   `function_call` → вызовы, `reasoning` → пропускать/логировать.
3. Приоритет низкий: `chat.completions` для DeepSeek работает (спайк 001),
   Responses API — будущая оптимизация под Codex-совместимость и reasoning.
