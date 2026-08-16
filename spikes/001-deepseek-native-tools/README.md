# 001-deepseek-native-tools

## Вопрос

`DeepSeekProvider` наследует `OpenAICompatibleToolsMixin` и декларирует
`supports_native_tools() → True`. Существующий `test_deepseek_provider.py`
проверяет только проводку (что `base_url` пробрасывается в клиент), но НЕ
подтверждает, что DeepSeek реально возвращает `tool_calls` при нативном
function calling через `chat.completions`.

Given ключ DeepSeek и tools-схема, when вызов `chat.completions.create(tools=...)`,
then в ответе есть валидный `tool_calls[].function.name` и распарсиваемый `arguments`.

## Риск

- DeepSeek мог не поддерживать нативный function calling → миксин молча бы
  падал на маркерный путь, и коуч терял бы инструменты на этом провайдере.
- Неверный `base_url` (с `/v1` или без) → 401/404.
- `temperature=0.7` для tool calling может давать шум в аргументах.

## Результат

| Параметр | Результат |
|----------|-----------|
| `https://api.deepseek.com/chat/completions` | ✅ 200, валидный tool_call |
| `https://api.deepseek.com/v1/chat/completions` | ✅ 200, валидный tool_call |
| `content` при наличии tool_calls | `''` (модель отдаёт только вызов) |
| `arguments` | JSON-строка `{"city": "Санкт-Петербург"}` |

Ответ:

```json
{
  "tool_calls": [{
    "index": 0,
    "id": "call_00_NFgLNyd0D2nVAt2ICysQ2664",
    "type": "function",
    "function": {
      "name": "get_weather",
      "arguments": "{\"city\": \"Санкт-Петербург\"}"
    }
  }]
}
```

## Вердикт: VALIDATED

### Что работает
- Нативный function calling DeepSeek (`deepseek-v4-flash`) работает штатно.
- Оба `base_url` валидны: `https://api.deepseek.com` (дефолт в settings) и с `/v1`.
  OpenAI SDK сам дописывает `/chat/completions`, так что дефолт корректен.
- `_native_tool_calls_from_openai_message` корректно нормализует ответ
  (аргументы парсятся из JSON-строки).

### Что неожиданно
- `content` пустой при tool_calls — важно, что миксин использует
  `getattr(message, "content", None) or ""` (не падает на None).

### Рекомендация для реальной сборки
- Держать дефолт `DEEPSEEK_BASE_URL="https://api.deepseek.com"` (без `/v1`) — уже верно.
- Для tool calling рассмотреть `temperature=0` — сейчас миксин шлёт `0.7`,
  что для детерминированных вызовов может вносить шум (не подтверждено, наблюдение).
- Закрепить live-подтверждение лёгким smoke-тестом с mock-прогоном на реальном
  контракте tool_calls (не требует сети — реплей фикстуры выше).
