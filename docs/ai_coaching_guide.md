# 🤖 Руководство по AI Коучингу

## Обзор

AI коучинг в AI Trainer позволяет получать персонализированные рекомендации по тренировкам от различных AI провайдеров. Система поддерживает множество провайдеров и автоматически выбирает доступный.

## Поддерживаемые провайдеры

### 1. OpenAI (GPT)
- **Модели**: GPT-3.5-turbo, GPT-4, GPT-4-turbo
- **Требования**: API ключ от OpenAI
- **Получить ключ**: https://platform.openai.com/api-keys

### 2. Anthropic (Claude)
- **Модели**: Claude-3-haiku, Claude-3-sonnet, Claude-3-opus
- **Требования**: API ключ от Anthropic
- **Получить ключ**: https://console.anthropic.com/

### 3. Google (Gemini)
- **Модели**: Gemini-pro, Gemini-pro-vision
- **Требования**: API ключ от Google AI Studio
- **Получить ключ**: https://makersuite.google.com/app/apikey

### 4. Ollama (Локальные модели)
- **Модели**: Llama2, Mistral, CodeLlama и др.
- **Требования**: Установленный Ollama локально
- **Установка**: https://ollama.ai/

## Настройка

### Шаг 1: Создайте файл .env

```bash
cp .env.example .env
```

### Шаг 2: Добавьте API ключи

Откройте `.env` и добавьте ключи для нужных провайдеров:

```env
# OpenAI
OPENAI_API_KEY=sk-...your-key...
OPENAI_MODEL=gpt-3.5-turbo

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...your-key...
ANTHROPIC_MODEL=claude-3-haiku-20240307

# Google
GOOGLE_API_KEY=...your-key...
GOOGLE_MODEL=gemini-pro

# Ollama (локально)
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama2

# Провайдер по умолчанию
DEFAULT_AI_PROVIDER=openai
```

### Шаг 3: Установка Ollama (опционально)

Для использования локальных моделей:

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.ai/install.sh | sh

# Запуск
ollama serve

# Загрузка модели
ollama pull llama2
```

## Использование в приложении

### 1. Запустите приложение

```bash
streamlit run app.py
```

### 2. Подключитесь к Garmin Connect

В боковой панели введите учетные данные Garmin и синхронизируйте данные.

### 3. Перейдите в раздел AI Коучинг

Выберите "🤖 AI Коучинг" в главном меню.

### 4. Настройте провайдера

В боковой панели:
1. Выберите провайдера из списка
2. Введите API ключ (если требуется)
3. Нажмите "🔌 Подключить AI"

### 5. Используйте функции коучинга

#### 📊 Анализ состояния
Получите оценку вашей текущей формы на основе метрик CTL/ATL/TSB.

#### 📅 Недельный план
Создайте персонализированный план тренировок на неделю с учётом ваших целей.

#### 🏃 Анализ тренировки
Получите детальный разбор выполненной тренировки с рекомендациями.

#### ❓ Вопрос коучу
Задайте любой вопрос о тренировках, восстановлении, питании.

#### 📚 Объяснение метрик
Узнайте, что означают различные тренировочные метрики простым языком.

## Тестирование

### Быстрый тест через скрипт

```bash
python test_ai_coach.py
```

Скрипт автоматически:
- Проверит доступные провайдеры
- Подключится к первому доступному
- Протестирует основные функции

### Тестирование с конкретным провайдером

```python
from models.ai_providers import AIProviderFactory
from models.ai_coach_universal import UniversalAICoach

# Создание провайдера
provider = AIProviderFactory.create_provider(
    "openai",
    api_key="your-key",
    model="gpt-3.5-turbo"
)

# Создание коуча
coach = UniversalAICoach(provider)

# Тестовые метрики
metrics = {
    'ctl': 42.5,
    'atl': 38.2,
    'tsb': 4.3,
    'form': 'Хорошая форма'
}

# Получение анализа
analysis = coach.analyze_current_state(metrics)
print(analysis)
```

## Решение проблем

### Провайдер недоступен

**Проблема**: "❌ OpenAI" в списке провайдеров

**Решение**:
1. Проверьте наличие API ключа в `.env`
2. Убедитесь, что ключ действителен
3. Проверьте баланс аккаунта

### Ошибка подключения

**Проблема**: "Не удалось подключиться к провайдеру"

**Решение**:
1. Проверьте интернет-соединение
2. Для Ollama - убедитесь, что сервер запущен
3. Проверьте правильность URL/хоста

### Медленные ответы

**Проблема**: AI отвечает очень долго

**Решение**:
1. Используйте более быструю модель (GPT-3.5 вместо GPT-4)
2. Попробуйте локальные модели через Ollama
3. Проверьте загруженность системы

### Ошибка protobuf (Google)

**Проблема**: Конфликт версий protobuf

**Решение**:
```bash
pip uninstall protobuf
pip install protobuf==4.24.0
```

## Рекомендации по выбору провайдера

### Для быстрых ответов
- **OpenAI GPT-3.5-turbo** - быстрый и недорогой
- **Claude-3-haiku** - очень быстрый, хорошее качество
- **Ollama Llama2** - локально, без затрат

### Для качественного анализа
- **GPT-4** - лучшее качество анализа
- **Claude-3-opus** - отличное понимание контекста
- **Gemini-pro** - хороший баланс качества/скорости

### Для конфиденциальности
- **Ollama** - все данные остаются локально
- Никакая информация не отправляется в облако

## Примеры промптов

### Анализ формы
"Моя CTL 45, ATL 52, TSB -7. Готов ли я к интенсивной тренировке?"

### План восстановления
"Вчера был марафон. Как восстанавливаться в ближайшую неделю?"

### Подготовка к старту
"Через 3 недели полумарафон. Как подвестись к старту?"

### Объяснение метрик
"Что такое TSB и как его использовать?"

## API для разработчиков

### Создание своего провайдера

```python
from models.ai_providers import AIProvider

class CustomProvider(AIProvider):
    def __init__(self, **kwargs):
        super().__init__()
        # Инициализация
    
    def generate_response(self, prompt: str, system_prompt: str = "") -> str:
        # Ваша логика генерации
        return response
    
    def is_available(self) -> bool:
        # Проверка доступности
        return True
    
    def get_model_name(self) -> str:
        return "Custom Model"
```

### Регистрация провайдера

```python
AIProviderFactory.register_provider("custom", CustomProvider)
```

## Безопасность

- **Никогда** не коммитьте API ключи в репозиторий
- Используйте `.env` файл для хранения ключей
- Регулярно ротируйте ключи
- Следите за использованием API

## Поддержка

- **Issues**: https://github.com/yourusername/ai_trainer/issues
- **Документация**: `/docs`
- **Примеры**: `/examples`

## Лицензия

MIT License - см. LICENSE файл