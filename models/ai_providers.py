"""
Универсальная система AI провайдеров для коучинга
Поддерживает: OpenAI, Anthropic, Google Gemini, Ollama, Mock (для тестирования)
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, List, Type
import os
from config.settings import Settings

# Консервативный runtime default для Google/gRPC stack в локальном окружении.
os.environ.setdefault('PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION', 'python')


class AIProvider(ABC):
    """Базовый класс для всех AI провайдеров"""
    
    @abstractmethod
    def generate_response(self, prompt: str, system_prompt: str = "") -> str:
        """Генерация ответа от AI"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Проверка доступности провайдера"""
        pass
    
    @abstractmethod
    def get_model_name(self) -> str:
        """Получить название используемой модели"""
        pass
    
    def test_connection(self) -> Dict[str, any]:
        """
        Тестирование подключения к провайдеру
        Возвращает словарь с результатами теста
        """
        return {
            'success': False,
            'error': 'Метод test_connection не реализован'
        }
    
    def get_available_models(self) -> List[str]:
        """
        Получить список доступных моделей
        Возвращает список строк с названиями моделей
        """
        return []


class OpenAIProvider(AIProvider):
    """Провайдер OpenAI (GPT-3.5/GPT-4)"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        settings: Type[Settings] = Settings,
    ) -> None:
        self.settings = settings
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model or settings.OPENAI_MODEL
        self.client = None
        
        if self.api_key:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=self.api_key)
            except ImportError:
                print("OpenAI библиотека не установлена")
            except Exception as e:
                print(f"Ошибка инициализации OpenAI: {e}")
    
    def generate_response(self, prompt: str, system_prompt: str = "") -> str:
        if not self.client:
            return "OpenAI провайдер не настроен"
        
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.settings.AI_RESPONSE_MAX_TOKENS,
                temperature=0.7
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            return f"Ошибка OpenAI: {e}"
    
    def is_available(self) -> bool:
        return self.client is not None and self.api_key is not None
    
    def get_model_name(self) -> str:
        return f"OpenAI {self.model}"
    
    def test_connection(self) -> Dict[str, any]:
        """Тестирование подключения к OpenAI"""
        if not self.client:
            return {
                'success': False,
                'error': 'Клиент не инициализирован. Проверьте API ключ.'
            }
        
        try:
            # Простой тестовый запрос
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Test"}],
                max_tokens=5
            )
            return {
                'success': True,
                'message': 'Подключение успешно',
                'model': self.model,
                'response_length': len(response.choices[0].message.content)
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Ошибка подключения: {str(e)}'
            }
    
    def get_available_models(self) -> List[str]:
        """Получить список доступных моделей OpenAI"""
        if not self.client:
            return []
        
        try:
            models = self.client.models.list()
            # Фильтруем только GPT модели
            gpt_models = [
                model.id for model in models.data 
                if 'gpt' in model.id.lower() and 'instruct' not in model.id.lower()
            ]
            return sorted(gpt_models)
        except Exception as e:
            print(f"Ошибка получения моделей OpenAI: {e}")
            return ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo-preview"]  # Fallback список


class AnthropicProvider(AIProvider):
    """Провайдер Anthropic (Claude)"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        settings: Type[Settings] = Settings,
    ) -> None:
        self.settings = settings
        self.api_key = api_key or settings.ANTHROPIC_API_KEY
        self.model = model or settings.ANTHROPIC_MODEL
        self.client = None
        
        if self.api_key:
            try:
                from anthropic import Anthropic
                self.client = Anthropic(api_key=self.api_key)
            except ImportError:
                print("Anthropic библиотека не установлена")
            except Exception as e:
                print(f"Ошибка инициализации Anthropic: {e}")
    
    def generate_response(self, prompt: str, system_prompt: str = "") -> str:
        if not self.client:
            return "Anthropic провайдер не настроен"
        
        try:
            messages = [{"role": "user", "content": prompt}]
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.settings.AI_RESPONSE_MAX_TOKENS,
                temperature=0.7,
                system=system_prompt if system_prompt else None,
                messages=messages
            )
            
            # Claude возвращает список блоков контента
            return response.content[0].text if response.content else ""
            
        except Exception as e:
            return f"Ошибка Anthropic: {e}"
    
    def is_available(self) -> bool:
        return self.client is not None and self.api_key is not None
    
    def get_model_name(self) -> str:
        return f"Anthropic {self.model}"
    
    def test_connection(self) -> Dict[str, any]:
        """Тестирование подключения к Anthropic"""
        if not self.client:
            return {
                'success': False,
                'error': 'Клиент не инициализирован. Проверьте API ключ.'
            }
        
        try:
            # Простой тестовый запрос
            response = self.client.messages.create(
                model=self.model,
                max_tokens=5,
                messages=[{"role": "user", "content": "Test"}]
            )
            return {
                'success': True,
                'message': 'Подключение успешно',
                'model': self.model,
                'response_length': len(response.content[0].text) if response.content else 0
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Ошибка подключения: {str(e)}'
            }
    
    def get_available_models(self) -> List[str]:
        """Получить список доступных моделей Anthropic"""
        # Anthropic API не предоставляет список моделей, возвращаем известные
        return [
            "claude-3-haiku-20240307",
            "claude-3-sonnet-20240229", 
            "claude-3-opus-20240229",
            "claude-2.1",
            "claude-2.0"
        ]


class DeepSeekProvider(AIProvider):
    """Провайдер DeepSeek через OpenAI-совместимый API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        settings: Type[Settings] = Settings,
    ) -> None:
        self.settings = settings
        self.api_key = api_key or settings.DEEPSEEK_API_KEY
        self.model = model or settings.DEEPSEEK_MODEL
        self.base_url = base_url or settings.DEEPSEEK_BASE_URL
        self.client = None

        if self.api_key:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            except ImportError:
                print("OpenAI библиотека не установлена")
            except Exception as e:
                print(f"Ошибка инициализации DeepSeek: {e}")

    def generate_response(self, prompt: str, system_prompt: str = "") -> str:
        if not self.client:
            return "DeepSeek провайдер не настроен"

        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.settings.AI_RESPONSE_MAX_TOKENS,
                temperature=0.7,
            )

            return response.choices[0].message.content

        except Exception as e:
            return f"Ошибка DeepSeek: {e}"

    def is_available(self) -> bool:
        return self.client is not None and self.api_key is not None

    def get_model_name(self) -> str:
        return f"DeepSeek {self.model}"

    def test_connection(self) -> Dict[str, any]:
        if not self.client:
            return {
                'success': False,
                'error': 'Клиент не инициализирован. Проверьте API ключ.'
            }

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Test"}],
                max_tokens=5,
            )
            return {
                'success': True,
                'message': 'Подключение успешно',
                'model': self.model,
                'base_url': self.base_url,
                'response_length': len(response.choices[0].message.content),
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Ошибка подключения: {str(e)}'
            }

    def get_available_models(self) -> List[str]:
        return [
            "deepseek-v4-flash",
            "deepseek-v4-pro",
            "deepseek-chat",
            "deepseek-reasoner",
        ]


class GoogleGeminiProvider(AIProvider):
    """Провайдер Google Gemini через актуальный Google Gen AI SDK."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        settings: Type[Settings] = Settings,
        emit_warnings: bool = True,
    ) -> None:
        self.settings = settings
        self.api_key = api_key or settings.GOOGLE_API_KEY
        self.emit_warnings = emit_warnings
        self.init_error: Optional[str] = None
        self.model_name = model or settings.GOOGLE_MODEL
        self.sdk_model_name = self._normalize_model_name(self.model_name)
        self.client = None
        
        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except ImportError:
                self.init_error = "Google Gen AI SDK не установлен"
                self._emit_init_warning(self.init_error)
            except Exception as e:
                self.init_error = f"Ошибка инициализации Google Gemini: {e}"
                self._emit_init_warning(self.init_error)
                self.client = None

    def _emit_init_warning(self, message: str) -> None:
        if self.emit_warnings:
            print(message)

    @staticmethod
    def _normalize_model_name(model_name: str) -> str:
        """Google Gen AI SDK принимает model id без legacy `models/` prefix."""
        return model_name.removeprefix("models/")

    @staticmethod
    def _response_text(response: object) -> str:
        try:
            text = getattr(response, "text", "")
        except Exception:
            return ""
        return text or ""
    
    def generate_response(self, prompt: str, system_prompt: str = "") -> str:
        if not self.client:
            return self.init_error or "Google Gemini провайдер не настроен"
        
        try:
            config = {
                "temperature": 0.7,
                "max_output_tokens": self.settings.AI_RESPONSE_MAX_TOKENS,
            }
            if system_prompt:
                config["system_instruction"] = system_prompt

            response = self.client.models.generate_content(
                model=self.sdk_model_name,
                contents=prompt,
                config=config,
            )
            return self._response_text(response)
            
        except Exception as e:
            return f"Ошибка Google Gemini: {e}"
    
    def is_available(self) -> bool:
        return self.client is not None and self.api_key is not None
    
    def get_model_name(self) -> str:
        return f"Google {self.model_name}"
    
    def test_connection(self) -> Dict[str, any]:
        """Тестирование подключения к Google Gemini"""
        if not self.client:
            return {
                'success': False,
                'error': self.init_error or 'Клиент не инициализирован. Проверьте API ключ.'
            }
        
        try:
            # Простой тестовый запрос
            response = self.client.models.generate_content(
                model=self.sdk_model_name,
                contents="Test",
                config={"max_output_tokens": 5},
            )
            response_text = self._response_text(response)
            return {
                'success': True,
                'message': 'Подключение успешно',
                'model': self.model_name,
                'response_length': len(response_text)
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Ошибка подключения: {str(e)}'
            }
    
    def get_available_models(self) -> List[str]:
        """Получить список доступных моделей Google"""
        return [
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
        ]


class OllamaProvider(AIProvider):
    """Провайдер Ollama (локальные модели)"""
    
    def __init__(
        self,
        model: Optional[str] = None,
        host: Optional[str] = None,
        settings: Type[Settings] = Settings,
    ) -> None:
        self.settings = settings
        self.model = model or settings.OLLAMA_MODEL
        self.host = host or settings.OLLAMA_HOST
        self.client = None
        
        try:
            import ollama
            self.client = ollama.Client(host=host)
            # Проверяем доступность
            self.client.list()
        except ImportError:
            print("Ollama библиотека не установлена")
        except Exception as e:
            print(f"Ошибка подключения к Ollama: {e}")
            self.client = None
    
    def generate_response(self, prompt: str, system_prompt: str = "") -> str:
        if not self.client:
            return "Ollama не доступна. Убедитесь, что Ollama запущена локально."
        
        try:
            # Объединяем system и user промпты
            full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            
            response = self.client.chat(
                model=self.model,
                messages=[
                    {"role": "user", "content": full_prompt}
                ]
            )
            
            return response['message']['content']
            
        except Exception as e:
            return f"Ошибка Ollama: {e}"
    
    def is_available(self) -> bool:
        if not self.client:
            return False
        
        try:
            # Проверяем, что модель доступна
            models = self.client.list()
            
            # Ollama возвращает ListResponse с атрибутом models
            if hasattr(models, 'models'):
                model_names = [getattr(m, 'model', '') for m in models.models]
            else:
                model_names = [m.get('name', '') for m in models.get('models', [])]
            
            # Точное совпадение или содержание имени модели
            return any(self.model == name or self.model in name for name in model_names)
        except Exception as e:
            print(f"Ollama is_available error: {e}")
            return False
    
    def get_model_name(self) -> str:
        return f"Ollama {self.model}"
    
    def test_connection(self) -> Dict[str, any]:
        """Тестирование подключения к Ollama"""
        if not self.client:
            return {
                'success': False,
                'error': 'Клиент не инициализирован. Проверьте, что Ollama запущен.'
            }
        
        try:
            # Простой тестовый запрос
            response = self.client.chat(
                model=self.model,
                messages=[{"role": "user", "content": "Test"}]
            )
            return {
                'success': True,
                'message': 'Подключение успешно',
                'model': self.model,
                'host': self.host,
                'response_length': len(response['message']['content'])
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Ошибка подключения: {str(e)}'
            }
    
    def get_available_models(self) -> List[str]:
        """Получить список доступных моделей Ollama"""
        if not self.client:
            return []
        
        try:
            models = self.client.list()
            
            if hasattr(models, 'models'):
                model_names = [getattr(m, 'model', '') for m in models.models]
            else:
                model_names = [m.get('name', '') for m in models.get('models', [])]
            
            return sorted([name for name in model_names if name])
        except Exception as e:
            print(f"Ошибка получения моделей Ollama: {e}")
            return []


class AIProviderFactory:
    """Фабрика для создания AI провайдеров"""

    @staticmethod
    def _google_probe_provider() -> GoogleGeminiProvider:
        return GoogleGeminiProvider(emit_warnings=False)
    
    @staticmethod
    def create_provider(provider_type: str, **kwargs) -> Optional[AIProvider]:
        """
        Создать провайдер по типу
        
        Args:
            provider_type: 'openai', 'anthropic', 'deepseek', 'google', 'ollama'
            **kwargs: параметры для конкретного провайдера
        """
        # Динамический импорт Mock провайдера
        try:
            from models.mock_ai_provider import MockAIProvider
        except ImportError:
            MockAIProvider = None
        
        providers = {
            'openai': OpenAIProvider,
            'anthropic': AnthropicProvider,
            'deepseek': DeepSeekProvider,
            'google': GoogleGeminiProvider,
            'ollama': OllamaProvider
        }
        
        if MockAIProvider:
            providers['mock'] = MockAIProvider
        
        provider_class = providers.get(provider_type.lower())
        if provider_class:
            # Для Ollama добавляем значения по умолчанию из Settings если не переданы
            if provider_type.lower() == 'ollama':
                if 'host' not in kwargs:
                    kwargs['host'] = Settings.OLLAMA_HOST
                if 'model' not in kwargs:
                    kwargs['model'] = Settings.OLLAMA_MODEL
            return provider_class(**kwargs)
        
        raise ValueError(f"Неизвестный провайдер: {provider_type}")
    
    @staticmethod
    def get_available_providers() -> Dict[str, bool]:
        """Получить список доступных провайдеров"""
        # Динамический импорт Mock провайдера
        try:
            from models.mock_ai_provider import MockAIProvider
            mock_available = True
        except ImportError:
            mock_available = False
        
        providers = {
            'OpenAI': OpenAIProvider(),
            'Anthropic': AnthropicProvider(),
            'DeepSeek': DeepSeekProvider(),
            'Google Gemini': AIProviderFactory._google_probe_provider(),
            'Ollama': OllamaProvider(host=Settings.OLLAMA_HOST, model=Settings.OLLAMA_MODEL)
        }
        
        if mock_available:
            providers['Mock AI (Demo)'] = MockAIProvider()
        
        return {
            name: provider.is_available() 
            for name, provider in providers.items()
        }
    
    @staticmethod
    def get_first_available() -> Optional[AIProvider]:
        """Получить первый доступный провайдер"""
        # Динамический импорт Mock провайдера
        try:
            from models.mock_ai_provider import MockAIProvider
            mock_available = True
        except ImportError:
            mock_available = False
        
        # Приоритет: OpenAI -> Anthropic -> DeepSeek -> Google -> Ollama -> Mock
        providers = [
            OpenAIProvider(),
            AnthropicProvider(),
            DeepSeekProvider(),
            AIProviderFactory._google_probe_provider(),
            OllamaProvider(host=Settings.OLLAMA_HOST, model=Settings.OLLAMA_MODEL)
        ]
        
        # Добавляем Mock как fallback
        if mock_available:
            providers.append(MockAIProvider())
        
        for provider in providers:
            if provider.is_available():
                return provider
        
        return None
