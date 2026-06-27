# Руководство по AI Coaching

## Обзор

AI Coaching в AI Trainer работает поверх локального тренировочного контекста: активности, HRV, сон, readiness, planning checkpoints, execution feedback и история чатов. UI провайдера живёт в `ui/components/ai_coach_provider.py`, сами провайдеры — в `models/ai_providers.py`.

Демо-режим не требует внешнего API: он автоматически использует `Mock AI (Demo)` и детерминированный локальный dataset.

## Поддерживаемые провайдеры

| Провайдер | Тип | Основные настройки |
|---|---|---|
| OpenAI | cloud | `OPENAI_API_KEY`, `OPENAI_MODEL` |
| Anthropic | cloud | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` |
| DeepSeek | cloud/OpenAI-compatible | `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`, `DEEPSEEK_BASE_URL` |
| Google Gemini | cloud | `GOOGLE_API_KEY`, `GOOGLE_MODEL` |
| Ollama | local | `OLLAMA_HOST`, `OLLAMA_MODEL` |
| Mock AI | local demo | no secrets required |

Current defaults are centralized in `config/settings.py`. Do not hard-code model names in page code; use `Settings` or provider model discovery.

## Environment Setup

Create `.env` from the example and add only the providers you need:

```bash
cp .env.example .env
```

```env
OPENAI_API_KEY=your_openai_key
OPENAI_MODEL=gpt-3.5-turbo

ANTHROPIC_API_KEY=your_anthropic_key
ANTHROPIC_MODEL=claude-3-haiku-20240307

DEEPSEEK_API_KEY=your_deepseek_key
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com

GOOGLE_API_KEY=your_google_key
GOOGLE_MODEL=models/gemini-1.5-flash-latest

OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=gemma3:4b

DEFAULT_AI_PROVIDER=deepseek
```

Secrets from `.env` must not be rendered back into the UI. The provider setup form intentionally leaves password fields empty; when the user does not type an override, the hidden `.env` value is used automatically.

## Using AI Coaching

1. Start the app:

```bash
./run.sh
```

2. Enter demo mode or authenticate with Garmin and sync real data.
3. Open `AI Коучинг`.
4. If a real provider is configured, the page attempts to auto-connect it. In demo mode, Mock AI is connected automatically.
5. If needed, choose another provider in the sidebar and connect it manually.

The AI page uses the current local context. A useful answer depends more on synced/planned data quality than on the provider alone.

## Ollama

For local private answers:

```bash
ollama serve
ollama pull gemma3:4b
```

Set `OLLAMA_HOST` and `OLLAMA_MODEL` in `.env`. Ollama keeps prompts local, but response quality and latency depend on the installed model and machine resources.

## Testing

```bash
# Contributor-safe coverage for provider and AI UI contracts
python -m pytest tests/smoke/test_ai_provider_probes.py -q
python -m pytest tests/smoke/test_ai_coaching_demo_flow.py -q
python -m pytest tests/smoke/test_ai_coaching_real_flow.py -q

# Broader local pass without live external systems
python -m pytest -m "not live and not debug" tests/
```

Avoid using live provider tests as the default loop; they may require secrets, network access, account balance, or local Ollama.

## Troubleshooting

### Provider is unavailable

- Check the relevant API key in `.env`.
- Check provider account balance/quota.
- For Ollama, verify `ollama serve` and `ollama list`.
- For DeepSeek, verify `DEEPSEEK_BASE_URL` if using a proxy.

### Gemini protobuf/runtime problems

Use the app launcher or runtime doctor instead of ad-hoc package edits:

```bash
./run.sh
python scripts/doctor_env.py check --runtime
python scripts/doctor_env.py repair --runtime
```

### The UI shows one provider but answers like another

This should be covered by smoke tests. Manual provider changes must clear stale `state.ai_coach` when the provider type changes. The relevant contract is in `ui/components/ai_coach_provider.py`.

### Answers are generic

Check that local context exists:

- Garmin sync or demo mode has activities.
- HRV/sleep/training status data exists where expected.
- A planning checkpoint exists if asking about a plan.
- Execution feedback has been saved if asking about deviations.

## Safety Notes

- Do not log API keys or Garmin credentials.
- Do not pre-fill secret fields from `.env`.
- Keep demo/acceptance mode isolated from real Garmin sync.
- Prefer Mock AI for screenshots, acceptance checks, and docs examples.
